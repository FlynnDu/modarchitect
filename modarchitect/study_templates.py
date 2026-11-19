# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 15:55
# @Author  : Codex
# @File    : study_templates.py
"""提供有来源的现成方案，核验原生案例输入而不公开受限业务档案。"""

from copy import deepcopy
from importlib.resources import files
import json
import os
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .catalog import catalog, research_request_schema
from .contracts.identifiers import identity_sha256
from .contracts.research.plans import ResearchPlan
from .contracts.research.input_bindings import ResearchInputBindingError
from .validation import compile_plan
from .system_inputs import input_readiness, validate_input_bindings
from .study_inputs import native_input_requirements


def _template_rows(filename: str) -> list[dict]:
    """当前与归档定义都必须保留准确摘要。"""
    source = files("modarchitect.contracts").joinpath(filename)
    rows = json.loads(source.read_text(encoding="utf-8"))
    for row in rows:
        body = {key: value for key, value in row.items() if key != "sha256"}
        if identity_sha256(body) != row["sha256"]:
            raise ValueError("Study template checksum differs")
    return rows


def templates() -> list[dict]:
    """目录只列当前可采用版本，历史版本继续按准确摘要解释。"""
    return [row for row in _template_rows("study-templates-v1.json") if row.get("listed", True)]


def template(template_id: str, checksum: str | None = None) -> dict:
    """稳定身份和准确摘要共同解析历史版本，不静默替换保存过的研究。"""
    for row in _template_rows("study-templates-v1.json"):
        if row["id"] == template_id and (checksum is None or row["sha256"] == checksum):
            return row
    for filename in ("study-templates-archive-v3.json", "study-templates-archive-v2.json", "study-templates-archive-v1.json"):
        for row in _template_rows(filename):
            if row["id"] == template_id and (checksum is None or row["sha256"] == checksum):
                return row
    raise LookupError("Study template was not found")


def scientific_definition(definition: dict) -> dict:
    """名称、负责人和展示说明不改变科学输入；冻结案例的依赖不得替换。"""
    return {key: value for key, value in definition.items() if key not in {"name", "question", "layout", "responsible_user_id"}}


def matches_template(row: dict, definition: dict) -> bool:
    """只放行登记的研究参数，不以改参数为由更换图结构或数据来源。"""
    actual, expected = deepcopy(scientific_definition(definition)), deepcopy(scientific_definition(row["definition"]))
    for port, fields in row.get("editable_parameters", {}).items():
        for value in (actual, expected):
            recipe = value.get("input_recipes", {}).get(port, {})
            if recipe.get("kind") != "configuration":
                return False
            if not isinstance(recipe.get("value"), dict):
                return False
            for field in fields:
                recipe["value"].pop(field, None)
    return actual == expected


def input_policy(row: dict) -> dict:
    """声明当前模板允许的数据调整及启动入口，不把目录定义当成取数成功。"""
    fixed = "bundle_sha256" in row
    user_data = False
    if not fixed:
        try:
            validate_input_bindings(row["definition"], require_catalog=True)
            readiness = input_readiness(row["definition"])
            user_data = bool(readiness) and all(
                item["execution"]["available"] for item in readiness
            )
        except ValueError:
            user_data = False
    selection = any("variables" in fields for fields in row.get("editable_parameters", {}).values())
    return {
        "mode": "approved_dataset" if fixed else (
            "user_observations" if user_data else "synthetic_demo_only"
        ),
        "editable": (["indicators"] if selection else []) if fixed else (
            ["records", "inputs", "factors", "targets"] if row["definition"]["purpose"] == "train" else ["records", "inputs"]),
    }


def template_view(row: dict, *, include_definition: bool = False) -> dict:
    """目录只提供方案与来源说明，受限原始数据始终由服务器持有。"""
    result = {key: deepcopy(value) for key, value in row.items() if key not in {"definition", "observations", "prediction_observations", "bundles", "bundle_sha256", "expected_outputs", "input_file"}}
    if row.get("researcher"):
        info = row["researcher"]
        result.update(summary=info["question"], output_description=info["outcome"], limitations=deepcopy(info["limits"]), sources=deepcopy(info.get("references", [])))
        result.pop("source_lineage", None)
    result["execution_mode"] = "frozen_case" if "bundle_sha256" in row else "observations"
    result["input_policy"] = input_policy(row)
    if include_definition:
        if "bundle_sha256" in row:
            result["input_requirements"] = native_input_requirements(row)
            if result.get("researcher"):
                result["researcher"]["data_usage"] = "此版本使用指定示例资料，不能替换底层资料或启用每日任务；开展自有研究需采用指标与来源已明确的新版本。"
        result["definition"] = deepcopy(row["definition"])
        result["definition"]["layout"]["study_template"] = {"id": row["id"], "sha256": row["sha256"]}
        result["observations"] = deepcopy(row.get("observations"))
        result["prediction_observations"] = deepcopy(row.get("prediction_observations"))
    return result


def frozen_inputs(row: dict) -> dict:
    """仅加载模板登记的封存数据；实际内容必须逐份匹配批准摘要。"""
    values = row.get("bundles")
    if values is None:
        directory = os.getenv("MODARCHITECT_STUDY_BUNDLES")
        if not directory:
            raise ValueError("Approved frozen study inputs are not configured")
        root = Path(directory).resolve()
        path = (root / row.get("input_file", row["id"] + ".json")).resolve()
        if path.parent != root:
            raise ValueError("Frozen study input path is invalid")
        try:
            values = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Approved frozen study inputs are unavailable") from exc
    if not isinstance(values, dict) or set(values) != set(row["bundle_sha256"]):
        raise ValueError("Frozen study input ports differ")
    for port, value in values.items():
        if identity_sha256(value) != row["bundle_sha256"][port]:
            raise ValueError("Approved frozen study input checksum differs: %s" % port)
    return values


def validate_native_inputs(definition: dict, values: dict) -> None:
    """按真实端口核验原生请求；更深的科学约束继续由独立组件负责。"""
    plan = ResearchPlan.model_validate(definition)
    compile_plan(plan, adopted=True)
    if any(recipe.kind not in {"artifact", "configuration"} for recipe in plan.input_recipes.values()):
        raise ValueError("Template research requires approved data and declared parameters")
    if set(values) != {code for code, recipe in plan.input_recipes.items() if recipe.kind == "artifact"}:
        raise ValueError("Frozen study inputs differ from its composition")
    for node in plan.composition.nodes:
        entry = catalog()[node.component.code, node.component.revision]
        schema = research_request_schema(entry.definition)
        for binding in node.bindings:
            if binding.port == "request" and binding.source.node is None and schema:
                recipe = plan.input_recipes[binding.source.port]
                supplied = recipe.value if recipe.kind == "configuration" else values[binding.source.port]
                Draft202012Validator(schema, format_checker=FormatChecker()).validate(supplied)


def validate_template_parameters(row: dict, definition: dict) -> None:
    """按方案已登记的指标选项校验增选与删除，不能只依赖页面复选框。"""
    options = row.get("indicator_options")
    if options is None:
        return
    schema = {"type": "array", "items": {"enum": [item["code"] for item in options]}}
    for port, fields in row.get("editable_parameters", {}).items():
        if "variables" not in fields:
            continue
        value = definition["input_recipes"][port]["value"].get("variables")
        if next(Draft202012Validator(schema).iter_errors(value), None) is not None:
            node = next(item for item in definition["composition"]["nodes"] if any(
                binding["source"].get("node") is None and binding["source"]["port"] == port
                for binding in item["bindings"]
            ))
            raise ResearchInputBindingError(node["code"], "request", port, "variables",
                                            "Selected indicators are outside the approved input")
