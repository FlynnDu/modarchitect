# -*- coding: utf-8 -*-
# @Time    : 2026/11/19 17:01
# @Author  : Codex
# @File    : test_research_inspection.py
"""从真实 HTTP 和执行边界验证不同方法共用的资料与规则合同。"""

from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from modarchitect.api import create_app
from modarchitect.catalog import component
from modarchitect.contracts.research.drafts import draft_file
from modarchitect.contracts.research.plans import ResearchPlan
from modarchitect.execution_contracts import compile_execution
from modarchitect.inspection import inspect_definition
from modarchitect.study_templates import template, template_view
from test_research_runtime import BASE, WRITE
from test_research_runtime import runtime_clients as runtime_clients

ROOT = Path(__file__).parents[1]


def system_plan() -> dict:
    """采用已有准确目录输入，避免用私有变量绕过来源规则。"""
    return json.loads((ROOT / "modarchitect/web/designer/system-study.json").read_bytes())["definition"]


@pytest.mark.parametrize("method", ["multivariate_linear_training", "random_forest_training", "xgboost_training", "gaussian_process_training", "research_descriptive_statistics"])
def test_methods_share_http_response_and_never_claim_execution(method):
    """真实检查接口共用字段，分析仅含分析用途，设计通过不代表可执行。"""
    plan = system_plan()
    plan["schema_version"] = "1.5"
    model = component(method, 1).definition
    plan["composition"]["nodes"][0]["component"]["code"] = method
    request_type = next(port.data_type.model_dump(mode="json") for port in model.inputs if port.code == "request")
    plan["composition"]["inputs"][1]["data_type"] = request_type
    plan["composition"]["outputs"] = [{"code": port.code, "source": {"node": "regression", "port": port.code}} for port in model.outputs]
    if method == "research_descriptive_statistics":
        plan["purpose"] = "explore"
        plan["evaluation"]["target_codes"] = []
        plan["input_recipes"]["regression_config"]["value"] = {"variables": ["lai", "canopy_cover"]}
        for requirement in plan["collection_requirements"]:
            requirement["required_for"] = ["explore"]
    with TestClient(create_app(api_key="inspection-test")) as client:
        checked = client.post("/designer/validate", json=plan).raise_for_status().json()
        headers = {"X-Modarchitect-Api-Key": "inspection-test"}
        inspected = client.post("/api/v1/research/definitions/inspect", headers=headers, json=plan).raise_for_status().json()
        old = client.post("/api/v1/research/configurations/check", headers=headers, json=draft_file(plan)).raise_for_status().json()
    assert checked["check"]["valid"] and old["valid"]
    assert inspected == checked["inspection"] == old["inspection"]
    assert set(inspected) == {"schema_version", "operation", "materials", "nodes", "outputs", "prediction", "evaluation", "checks"}
    assert inspected["checks"]["configuration"]["status"] == "passed"
    assert inspected["checks"]["execution"] == {"status": "not_checked", "issues": []}
    assert inspected["materials"][0]["sources"][0]["data_available"] is None
    node = inspected["nodes"][0]
    assert node["parameters"] == plan["input_recipes"]["regression_config"]["value"]
    if method == "research_descriptive_statistics":
        assert inspected["operation"] == "analyze"
        assert inspected["prediction"] is None
        assert inspected["evaluation"] is None
        assert all(use["phases"] == ["analysis"] for use in node["input_usages"])
        assert "training_end" not in node["parameter_schema"]["properties"]
    else:
        assert inspected["operation"] == "train"
        assert any(use["role"] == "label" for use in node["input_usages"])
        assert set(inspected["prediction"]["input_codes"]) == {"canopy_cover", "tuber_dm_kg_ha"}
        assert inspected["prediction"]["target_codes"] == plan["evaluation"]["target_codes"]
        assert inspected["evaluation"]["strategy"] == "saved_policy"
        assert inspected["evaluation"]["training_percent"] is None
        assert {metric["code"] for metric in inspected["evaluation"]["metrics"]} == {"r2", "mae", "rmse", "bias"}


def test_mixed_operations_locate_same_incompatibility_as_executor():
    """允许计划设计继续保存，同时准确指出永远无法共同执行的节点。"""
    plan = system_plan()
    analysis = component("research_descriptive_statistics", 1).definition
    request = deepcopy(plan["composition"]["inputs"][1])
    request.update(code="summary_request", data_type=analysis.inputs[1].data_type.model_dump(mode="json"))
    plan["composition"]["inputs"].append(request)
    plan["input_recipes"]["summary_request"] = {"kind": "configuration", "value": {"variables": ["lai"]}}
    plan["composition"]["nodes"].append({"code": "summary", "component": {"code": analysis.code, "revision": 1}, "bindings": [
        {"port": "observations", "source": {"node": None, "port": "observations"}},
        {"port": "request", "source": {"node": None, "port": "summary_request"}},
    ]})
    plan["composition"]["outputs"].append({"code": "summary", "source": {"node": "summary", "port": "summary"}})
    result = inspect_definition(plan).model_dump(mode="json")
    assert result["checks"]["configuration"]["status"] == "passed"
    issue = result["checks"]["operation"]["issues"][0]
    assert issue["code"] == "operation_incompatible" and issue["node"] == "summary"
    assert issue["path"] == ["composition", "nodes", 1]
    with pytest.raises(ValueError, match="research operation train: research_descriptive_statistics@1") as error:
        compile_execution(ResearchPlan.model_validate(plan).composition, "train", {})
    assert error.value.rule == issue["code"]


def test_invalid_drafts_return_same_check_shape_and_no_old_facts():
    """非法结构、参数与失效图引用均给出阻断，不泄漏上次通过状态。"""
    with TestClient(create_app()) as client:
        for plan in ({}, {**system_plan(), "name": " "}):
            result = client.post("/designer/validate", json=plan).raise_for_status().json()["inspection"]
            assert result["checks"]["configuration"]["status"] == "blocked"
            assert result["checks"]["configuration"]["issues"][0]["code"]
            assert result["checks"]["execution"]["status"] == "not_checked"
        plan = system_plan()
        plan["composition"]["nodes"][0]["bindings"][0]["source"]["port"] = "removed"
        result = client.post("/designer/validate", json=plan).raise_for_status().json()["inspection"]
        assert result["checks"]["configuration"]["status"] == "blocked"
        assert result["nodes"] == []
        assert result["prediction"] is None


def test_native_metadata_and_historical_contracts_keep_scientific_identity():
    """封存资料只公开字段元数据，旧合同不因统一显示被改写。"""
    row = template_view(template("growth-water-response"), include_definition=True)
    definition = deepcopy(row["definition"])
    values = definition["input_recipes"]["settings"]["value"]
    values["variables"] = values["variables"][:1]
    result = inspect_definition(definition).model_dump(mode="json")
    assert definition["layout"] == row["definition"]["layout"]
    indicators = [item for material in result["materials"] for item in material["indicators"]]
    assert {item["code"] for item in indicators} == set(values["variables"])
    assert "bundle_sha256" not in json.dumps(result)
    assert all("value" not in item for item in indicators)
    legacy = json.loads((ROOT / "modarchitect/web/designer/example.json").read_bytes())["definition"]
    assert inspect_definition(legacy).checks.operation.status == "unsupported"


def test_saved_readback_adds_inspection_without_changing_configuration(runtime_clients):
    """实际低权限数据库的保存重读保留准确正文及摘要，增加只读投影。"""
    client, _ = runtime_clients
    plan = system_plan()
    saved = client.post(BASE + "/plans", headers={**WRITE, "Idempotency-Key": str(uuid4())}, json={"definition": plan}).raise_for_status().json()
    read = client.get(BASE + "/plans/" + saved["design_id"]).raise_for_status().json()
    assert read["configuration"] == saved["configuration"]
    assert read["configuration_sha256"] == saved["configuration_sha256"]
    assert read["inspection"]["nodes"][0]["component"] == plan["composition"]["nodes"][0]["component"]
    check = client.post(BASE + "/check-execution", headers=WRITE, json={"definition": plan, "operation": "analyze"}).raise_for_status().json()
    assert not check["can_execute"]
    assert check["checks"]["execution"]["status"] == "blocked"
    assert check["checks"]["execution"]["issues"][0]["code"]
    assert set(check["checks"]["execution"]["issues"][0]) == {"code", "path", "node", "port", "message"}
