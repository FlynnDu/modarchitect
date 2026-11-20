# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 18:38
# @Author  : Codex
# @File    : preparation.py
"""执行预检与实际启动共用准备规则；校验失败不创建版本、运行或调度任务。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from pydantic import ValidationError

from ..contracts.research.input_bindings import ResearchInputBindingError
from ..contracts.research.evaluation import DEFAULT_TRAINING_PERCENT
from ..contracts.research.plans import TRAINING_CUTOFF, ResearchPlan
from ..execution_contracts import compile_execution, external_input_codes
from ..study_templates import frozen_inputs, matches_template, template, validate_native_inputs, validate_template_parameters
from ..contracts.violations import ContractViolation
from ..contracts.research.execution import PURPOSE_OPERATIONS
from ..system_inputs import seal_input_sources
from ..validation import compile_plan
from .contracts import ObservationTable


RULES = {
    "plan_contract": ("方案结构", "补齐方案字段，确保变量、输入与输出引用一致。"),
    "template_identity": ("指定资料资格", "采用准确版本的研究方案；不能用上传数据替代指定资料。"),
    "template_edit": ("指定资料编辑范围", "仅修改本方案声明的参数；改变输入结构时另建采用相应来源的研究。"),
    "plan_dependencies": ("输入输出与连接", "核对必需输入、参数、因素、目标、科学单位以及组件连接。"),
    "operation": ("研究操作", "使用当前方案及全部组件共同支持的研究操作。"),
    "execution_artifact": ("计算制品", "检查准确组件版本及已登记的运行环境是否可用。"),
    "input_data": ("本次数据", "提供非空观测，保持完整对象、日期、数值和数据列一致。"),
    "input_source": ("输入来源资格", "从系统目录采用准确指标、单位和来源；合成演示不能当作真实地块研究。"),
    "input_bindings": ("节点变量与数据", "新增或删除变量后同步调整数据列和模型参数；训练目标必须有实测。"),
}
PURPOSES = {PURPOSE_OPERATIONS[purpose]: purpose for purpose in ("train", "explore", "simulate", "fit")}


class ExecutionRejected(ValueError):
    """保留旧错误正文，并给新调用方提供稳定规则与定位信息。"""

    def __init__(self, rule: str, error: ValueError | str, path: list | None = None):
        """不保存原始输入或凭据，只保留可公开的失败说明。"""
        super().__init__("Research contract validation failed" if isinstance(error, ValidationError) else str(error))
        location = path or []
        if isinstance(error, ResearchInputBindingError):
            location = error.path
        self.issues = [{"rule": rule, "path": location, "message": str(error)}]
        if isinstance(error, ContractViolation):
            self.issues = [{"rule": rule, "code": error.rule, "path": error.path,
                            "message": str(error), "node": error.node, "port": error.port}]
        if isinstance(error, ValidationError):
            self.issues = [{"rule": rule, "path": list(item["loc"]), "message": item["msg"]}
                           for item in error.errors(include_input=False, include_context=False, include_url=False)]


@dataclass(frozen=True)
class PreparedRun:
    """只有完成全部准备校验的输入才能交给启动流程封存入队。"""

    payload: dict


def _check(rule: str, action: Callable, path: list | None = None):
    """为已有权威校验补充规则身份，不在这里重写组件或来源判断。"""
    try:
        return action()
    except ExecutionRejected:
        raise
    except ValueError as exc:
        raise ExecutionRejected(rule, exc, path) from exc
    except OSError as exc:
        raise ExecutionRejected(rule, "Required research input or execution resource is unavailable", path) from exc


def _base(definition: dict, operation: str, select_profiles: Callable,
          *, strict_purpose: bool = True) -> tuple[ResearchPlan, dict]:
    """共用结构、连接、操作和准确制品检查。"""
    plan = _check("plan_contract", lambda: ResearchPlan.model_validate(definition))
    compiled = _check("plan_dependencies", lambda: compile_plan(plan, adopted=True))
    if strict_purpose and plan.purpose != PURPOSES[operation]:
        raise ExecutionRejected("operation", "Research purpose differs from the requested operation", ["purpose"])
    registered = _check("execution_artifact", lambda: select_profiles(definition))
    execution = _check("operation", lambda: compile_execution(plan.composition, operation, registered))
    return plan, {"kind": operation, "plan": definition, "order": compiled["order"],
                  "profiles": registered, "execution_contracts": execution,
                  "variable_usages": compiled.get("variable_usages", [])}


def prepare_observations(definition: dict, operation: str,
                         observations: ObservationTable | None, data_kind: str,
                         subject: str, select_profiles: Callable,
                         *, strict_purpose: bool = True,
                         source_snapshots: list[dict] = ()) -> PreparedRun:
    """准备普通观测执行，真实来源、变量绑定和标签资格使用现有权威规则。"""
    if any(recipe.get("kind") == "artifact" for recipe in definition.get("input_recipes", {}).values() if isinstance(recipe, dict)):
        raise ExecutionRejected("template_identity", "Approved artifact inputs require template execution", ["input_recipes"])
    plan, payload = _base(definition, operation, select_profiles, strict_purpose=strict_purpose)
    if observations is None:
        raise ExecutionRejected("input_data", "Research observations are required", ["observations"])
    table = observations.sealed()
    sources = _check("input_source", lambda: seal_input_sources(definition, table, data_kind, subject, source_snapshots=source_snapshots), ["observations"])

    def check_columns() -> None:
        """同一份表同时服务因素和标签时，按准确节点用途核验本次数据。"""
        columns = {column["code"]: column for column in table["columns"]}
        variables = {variable.code: variable for variable in plan.variables}
        observed_codes = {use["variable_code"] for use in payload["variable_usages"] if use["observed_required"]}
        needed_codes = external_input_codes(plan, operation)
        for recipe in plan.input_recipes.values():
            if recipe.kind != "observations":
                continue
            for code in recipe.variable_codes:
                if code not in needed_codes:
                    continue
                if code not in columns or columns[code]["unit"] != variables[code].unit:
                    raise ValueError("Observation variable or scientific unit differs: %s" % code)
                observed_required = code in observed_codes if plan.schema_version == "1.5" else variables[code].role in {"target", "validation"}
                if observed_required and columns[code]["value_kind"] != "observed":
                    raise ValueError("Training labels require observed measurements")
                for row in table["rows"]:
                    variables[code].validate_value(row["values"][code])

    _check("input_bindings", check_columns, ["observations"])
    if any(TRAINING_CUTOFF in recipe.runtime_fields.values() for recipe in plan.input_recipes.values()):
        cutoff = _check("input_data", lambda: _training_cutoff(plan, table), ["observations"])
        payload["training_cutoff"] = cutoff
    payload.pop("variable_usages")
    payload.update(observations=table, data_kind=data_kind, input_sources=sources)
    return PreparedRun(payload)


def _training_cutoff(plan: ResearchPlan, table: dict) -> str:
    """从本次观测业务日确定边界，优先遵循明确的评价窗口。"""
    days = sorted({row["business_date"] for row in table["rows"]})
    if len(days) < 2:
        raise ValueError("Automatic evaluation needs observations on at least two distinct dates")
    gate = plan.evaluation.numeric_gate
    if gate:
        cutoff = (gate.holdout_start - timedelta(days=1)).isoformat()
        window_start, window_end = gate.holdout_start.isoformat(), gate.holdout_end.isoformat()
        if days[0] > cutoff or not any(window_start <= day <= window_end for day in days):
            raise ValueError("The specified evaluation dates need both training and holdout observations")
        return cutoff
    percent = plan.evaluation.training_percent or DEFAULT_TRAINING_PERCENT
    return days[max(1, len(days) * percent // 100) - 1]


def prepare_template(definition: dict, template_id: str, checksum: str,
                     subject: str, select_profiles: Callable) -> PreparedRun:
    """准备指定资料执行；不允许以改参、增删输入或伪造模板标记替换来源。"""
    row = _check("template_identity", lambda: template(template_id, checksum))
    if row["sha256"] != checksum or "bundle_sha256" not in row:
        raise ExecutionRejected("template_identity", "Frozen study template identity differs")
    if not matches_template(row, definition):
        raise ExecutionRejected("template_edit", "Frozen study scientific definition has changed", ["input_recipes"])
    _check("input_bindings", lambda: validate_template_parameters(row, definition))
    inputs = _check("template_identity", lambda: frozen_inputs(row))
    _check("input_bindings", lambda: validate_native_inputs(definition, inputs), ["input_recipes"])
    _, payload = _base(definition, row["operation"], select_profiles)
    sources = {
        "format": "research_frozen_inputs_v1", "subject": subject,
        "template_id": row["id"], "template_sha256": row["sha256"],
        "inputs": [{"port": port, "sha256": digest, "channel": "synthetic_demo" if row["data_kind"] == "synthetic" else "frozen_archive", "variable": {"name": port}}
                   for port, digest in row["bundle_sha256"].items()],
    }
    from ..contracts.identifiers import identity_sha256

    sources["sha256"] = identity_sha256(sources)
    payload.pop("variable_usages")
    payload.update(artifact_inputs=inputs, data_kind=row["data_kind"], input_sources=sources,
                   template_id=row["id"], expected_outputs=row.get("expected_outputs", {}))
    return PreparedRun(payload)


def prepare_prediction(model: dict, observations: ObservationTable, data_kind: str,
                       subject: str, registered: dict, source_snapshots: list[dict]) -> PreparedRun:
    """准确模型的纯推理准备供私有、持续和发布入口共用，不读取训练标签。"""
    frozen = model["model_json"]["profiles"]
    if any(registered.get(code) != spec for code, spec in frozen.items()):
        raise ValueError("The model execution artifacts are no longer available")
    table = observations.sealed()
    plan = ResearchPlan.model_validate(model["model_json"]["plan"])
    needed = external_input_codes(plan, "predict")
    columns = {column["code"]: column for column in table["columns"]}
    for variable in plan.variables:
        if variable.code not in needed:
            continue
        if variable.code not in columns or columns[variable.code]["unit"] != variable.unit:
            raise ValueError("Prediction variable or scientific unit differs: %s" % variable.code)
        for row in table["rows"]:
            variable.validate_value(row["values"][variable.code])
    sources = seal_input_sources(model["model_json"]["plan"], table, data_kind, subject,
                                 allow_legacy=model["model_json"].get("input_sources") is None,
                                 source_snapshots=source_snapshots)
    return PreparedRun({"kind": "predict", "pipeline": model["model_json"], "observations": table,
                        "profiles": frozen, "model_id": str(model["model_id"]),
                        "model_sha256": model["model_sha256"], "data_kind": data_kind,
                        "input_sources": sources})


def rule_catalog() -> dict:
    """公开当前实现的规则范围，能力声明不能代替一次实际执行检查。"""
    return {"version": "1.0", "rules": [{"code": code, "name": name, "guidance": guidance}
                                          for code, (name, guidance) in RULES.items()]}
