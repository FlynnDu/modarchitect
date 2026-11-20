# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 16:03
# @Author  : Codex
# @File    : validation.py
"""编译设计合同，并校验当前科研适配能处理的请求与观测绑定。"""

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from .catalog import catalog, research_request_schema
from .contracts.model_center.components import Composition
from .contracts.model_center.composition import compile_composition
from .contracts.research.drafts import import_draft
from .contracts.research.input_bindings import (
    ResearchInputBindingError,
    validate_research_input_bindings,
)
from .contracts.research.plan_file import export_plan, import_plan
from .contracts.research.plans import TRAINING_CUTOFF, ResearchPlan
from .system_inputs import validate_input_bindings
from .execution_contracts import input_usages
from .contracts.violations import ContractViolation
from .research_methods import method_declarations

_RUNTIME_EXAMPLES = {
    "cutoff_date": "2000-01-01",
    "fit_cutoff_date": "2000-01-01",
    TRAINING_CUTOFF: "2000-01-01",
    "cutoff_timestamp": "2000-01-01T00:00:00+00:00",
    "object": {
        "field_ref": "validation",
        "crop_code": "validation",
        "season_ref": "validation",
    },
    "season_start": "2000-01-01",
    "season_end": "2000-12-31",
}


class DesignValidationError(ValueError):
    """正式保存失败保留与只读设计检查相同的问题定位。"""

    def __init__(self, issues: list[dict]) -> None:
        """仅携带公开规则问题，不包含数据库或运行凭据。"""
        self.issues = issues
        super().__init__("Research design validation failed")


def validate_submission(configuration: dict) -> dict:
    """保存边界重复执行设计检查，拒绝客户端伪造已通过标记。"""
    try:
        configuration = import_draft(configuration)
    except ValueError as exc:
        raise DesignValidationError([{"path": ["configuration"], "type": "invalid_configuration", "message": str(exc)}]) from exc
    result = check_definition(configuration["definition"])
    if not result["valid"]:
        raise DesignValidationError(result["issues"])
    return configuration


def compile_graph(composition: Composition, *, adopted: bool = False) -> dict:
    """先按准确版本编译，再检查新发布所需的采用资格。"""
    versions = catalog()
    result = compile_composition(
        composition, {key: item.definition for key, item in versions.items()}
    )
    for node in composition.nodes:
        version = versions[node.component.code, node.component.revision]
        if adopted and not version.available_for_new_design:
            raise ValueError(
                "Component version is available for historical designs only"
            )
        if not version.definition.composable:
            raise ValueError("Component version cannot be composed")
    return result


def _requests(plan: ResearchPlan, *, for_execution: bool = True) -> dict[str, tuple[str, dict, dict]]:
    """从准确组件的表单 Schema 验证显式配置配方。"""
    requests = {}
    for node in plan.composition.nodes:
        model = catalog()[node.component.code, node.component.revision].definition
        schema = research_request_schema(model)
        if schema is None:
            if for_execution and any(port.code == "request" for port in model.inputs):
                raise ValueError("Component has no research request adapter")
            continue
        binding = next((b for b in node.bindings if b.port == "request"), None)
        if binding is None or binding.source.node is not None:
            raise ValueError("Research request configuration must be explicit")
        recipe = plan.input_recipes[binding.source.port]
        if recipe.kind == "deferred" and not for_execution:
            raise ContractViolation(
                "Required model parameters are not configured",
                ["input_recipes", binding.source.port],
                "incomplete_configuration", node=node.code, port="request",
            )
        if recipe.kind == "artifact":
            # 原生请求由服务端批准的封存案例提供，启动时校验准确字节及请求 Schema。
            continue
        if recipe.kind != "configuration":
            raise ValueError("Research request requires a configuration recipe")
        value = dict(recipe.value or {})
        if TRAINING_CUTOFF in recipe.runtime_fields.values():
            method = method_declarations().get((node.component.code, node.component.revision))
            if (not method or plan.purpose != "train" or plan.evaluation.split_unit != "time"
                    or recipe.runtime_fields != {method.cutoff_field: TRAINING_CUTOFF}
                    or method.cutoff_field in value):
                raise ValueError("Automatic training cutoff requires the reviewed method and a time holdout rule")
            if any(b.source.node == node.code for consumer in plan.composition.nodes for b in consumer.bindings):
                raise ValueError("Automatic training cutoff is only supported for the final training step")
        # 形状检查使用占位值。科学时点由未来的可信运行上下文绑定。
        value.update(
            {
                key: _RUNTIME_EXAMPLES[slot]
                for key, slot in recipe.runtime_fields.items()
            }
        )
        if (
            plan.evaluation.numeric_gate is not None
            and value.get("operation") == "fit"
            and recipe.runtime_fields.get("cutoff") != "fit_cutoff_date"
        ):
            raise ValueError(
                "Fitting with a holdout requires the declared training cutoff"
            )
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        issue = next(validator.iter_errors(value), None)
        if issue is not None:
            missing = next(
                (key for key in schema.get("required", []) if key not in value),
                "request",
            )
            field = next(iter(issue.absolute_path), missing)
            raise ResearchInputBindingError(
                node.code,
                "request",
                binding.source.port,
                str(field),
                "Request parameters do not match the component schema",
            )
        requests[node.code] = (binding.source.port, value, schema)
    return requests


def compile_plan(plan: ResearchPlan, *, adopted: bool = False, for_execution: bool = True) -> dict:
    """校验首批可执行语义所需的合同，不调用计算环境。"""
    compiled = compile_graph(plan.composition, adopted=adopted)
    validate_input_bindings(plan.model_dump(mode="json"))
    if for_execution and plan.report is not None:
        raise ValueError("Report adapter is outside the current catalog")
    variables = {v.code: v for v in plan.variables}
    for code, recipe in plan.input_recipes.items():
        port = next(p for p in plan.composition.inputs if p.code == code)
        if recipe.kind == "deferred" and not for_execution:
            continue
        if (
            recipe.kind not in {"observations", "configuration", "artifact"}
            or port.data_type.shape == "model"
        ):
            raise ValueError("Research input requires an unavailable adapter")
        if (recipe.kind == "observations") != (
            port.data_type.semantic == "research_observation_table"
        ):
            raise ValueError(
                "Research observations require an observation-table input and recipe"
            )
        if recipe.kind == "observations":
            if any(variables[v].value_type != "number" for v in recipe.variable_codes):
                raise ValueError(
                    "Current observation adapters require numeric variables"
                )
            if for_execution and any(
                r.variable_code in recipe.variable_codes
                and r.unit_kind != "field_season"
                for r in plan.collection_requirements
                if plan.purpose in r.required_for
            ):
                raise ValueError(
                    "Current numeric adapter requires field-season observations"
                )
    projections = {
        node.code: catalog()[node.component.code, node.component.revision]
        .definition.configuration.get("research_model", {})
        .get("table_outputs", {})
        for node in plan.composition.nodes
    }
    requests = _requests(plan, for_execution=for_execution)
    validate_research_input_bindings(plan, compiled["order"], requests, projections)
    if plan.schema_version == "1.5":
        usages = input_usages(plan.composition, requests)
        labels = {use["variable_code"] for use in usages if use["role"] == "label"}
        if for_execution and not set(plan.evaluation.target_codes) <= labels:
            raise ValueError("Evaluation targets require a declared node label binding")
        compiled["variable_usages"] = usages
    return compiled


def check_draft(configuration: dict) -> dict:
    """返回可定位的问题，格式无效时由 HTTP 层按输入错误处理。"""
    return check_definition(import_draft(configuration)["definition"])


def check_definition(definition: dict) -> dict:
    """检查待编辑定义，返回编译结果或可定位的问题。"""
    try:
        compiled = compile_plan(ResearchPlan.model_validate(definition), adopted=True, for_execution=False)
    except ValidationError as exc:
        issues = [
            {"path": list(err["loc"]), "type": err["type"], "message": err["msg"]}
            for err in exc.errors(
                include_input=False, include_context=False, include_url=False
            )
        ]
    except ResearchInputBindingError as exc:
        issues = [
            {
                "path": exc.path,
                "type": "incompatible_input_binding",
                "message": str(exc),
                "node": exc.node,
                "port": exc.port,
            }
        ]
    except ContractViolation as exc:
        issues = [exc.issue()]
    except ValueError as exc:
        issues = [
            {
                "path": ["composition"],
                "type": "unsupported_contract",
                "message": str(exc),
            }
        ]
    else:
        return {"valid": True, "compiled": compiled, "issues": []}
    return {"valid": False, "issues": issues}


def load_configuration(file: dict) -> dict:
    """校验方案或草稿摘要，按准确版本读入配置。"""
    if file.get("format") == "research_plan_draft":
        return import_draft(file)
    plan = import_plan(file)
    compile_plan(plan)
    return export_plan(plan)
