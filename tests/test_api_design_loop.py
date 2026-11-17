# -*- coding: utf-8 -*-
# @Time    : 2026/11/16 21:14
# @Author  : Codex
# @File    : test_api_design_loop.py
"""按业务转接文档验证开放设计、正式检查保存及重新查询的完整链路。"""

from copy import deepcopy
import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from modarchitect.api import create_app
from modarchitect.catalog import component
from modarchitect.contracts.identifiers import identity_sha256
from modarchitect.contracts.research.plans import ResearchPlan
from modarchitect.system_inputs import seal_input_sources
from modarchitect.validation import check_definition, compile_plan

API = "/api/v1/research"
ROOT = Path(__file__).parents[1]


def all_indicator_design(client: TestClient) -> dict:
    """只通过公开目录和配置接口构造含65个固定指标的自定义方案。"""
    plan = json.loads((ROOT / "modarchitect/web/designer/system-study.json").read_bytes())["definition"]
    catalog = client.get("/api/v1/model-center/research-inputs").json()
    plan["schema_version"] = "1.5"
    plan["name"] = "多来源指标联合研究（设计验收）"
    plan["variables"], plan["collection_requirements"] = [], []
    for entry in catalog["items"]:
        selectors = {key: value["enum"][0] for key, value in entry["source"]["selection_schema"]["properties"].items()}
        result = client.post("/api/v1/model-center/research-inputs/configure", json={"key": entry["key"], "selectors": selectors, "role": "target" if entry["variable"]["code"] == "lai" else "covariate"})
        assert result.status_code == 200, result.text
        configured = result.json()
        plan["variables"].append(configured["variable"])
        plan["collection_requirements"].append(configured["requirement"])
    codes = [item["code"] for item in plan["variables"]]
    assert len(set(codes)) == len(codes) == 65
    for recipe in plan["input_recipes"].values():
        if recipe["kind"] == "observations":
            recipe["variable_codes"] = codes
        else:
            recipe["value"] = {"features": [code for code in codes if code != "lai"], "targets": ["lai"], "training_end": "2026-05-10"}
    plan["evaluation"]["target_codes"] = ["lai"]
    return plan


def deferred_model_design(plan: dict) -> dict:
    """保留真实时序端口，未来资料使用typed deferred引用，不伪装成普通表。"""
    draft = deepcopy(plan)
    model = component("lstm", 1).definition
    node = draft["composition"]["nodes"][0]
    node["component"] = {"code": model.code, "revision": 1}
    setting = next(binding["source"]["port"] for binding in node["bindings"] if binding["port"] == "request")
    dataset = next(port for port in model.inputs if port.code == "dataset")
    draft["composition"]["inputs"].append({"code": "sequence_data", "name": "时序资料（待接入）", "data_type": dataset.data_type.model_dump(mode="json"), "role": "context"})
    draft["input_recipes"]["sequence_data"] = {"kind": "deferred", "variable_codes": ["temperature_mean_daily", "lai"]}
    request = next(port for port in model.inputs if port.code == "request")
    next(port for port in draft["composition"]["inputs"] if port["code"] == setting)["data_type"] = request.data_type.model_dump(mode="json")
    draft["input_recipes"][setting]["value"] = {"features": ["temperature_mean_daily"], "target": "lai", "cutoff": "2026-05-10T23:59:59+08:00", "seed": 17}
    node["bindings"] = [{"port": "request", "source": {"node": None, "port": setting}}, {"port": "dataset", "source": {"node": None, "port": "sequence_data"}}]
    for port in list(draft["composition"]["inputs"]):
        if port["code"] not in {setting, "sequence_data"}:
            draft["composition"]["inputs"].remove(port)
            del draft["input_recipes"][port["code"]]
    draft["composition"]["outputs"] = [{"code": port.code, "source": {"node": node["code"], "port": port.code}} for port in model.outputs]
    return draft


def test_design_accepts_all_indicators_and_future_typed_model_but_execution_refuses() -> None:
    """设计未要求取数和制品就绪；运行边界继续拒绝计划来源及待实现适配。"""
    with TestClient(create_app()) as client:
        plan = all_indicator_design(client)
    assert check_definition(plan)["valid"]
    future = deferred_model_design(plan)
    assert check_definition(future)["valid"], check_definition(future)
    with pytest.raises(ValueError, match="adapter|field-season"):
        compile_plan(ResearchPlan.model_validate(future))
    source = next(requirement for requirement in plan["collection_requirements"] if requirement["catalog_binding"]["kind"] == "planned_source" and requirement["catalog_binding"]["value_nature"] == "estimated")
    variable = next(item for item in plan["variables"] if item["code"] == source["variable_code"])
    table = {"columns": [{"code": variable["code"], "name": variable["name"], "unit": variable["unit"], "value_kind": "estimated"}], "rows": [{"object": {"field_ref": "test", "crop_code": "potato", "season_ref": "2026"}, "business_date": "2026-05-01", "values": {variable["code"]: 0.5}}], "source_sha256": ["0" * 64]}
    with pytest.raises(ValueError, match="unavailable"):
        seal_input_sources(plan, table, "user_supplied", "acceptance")


@pytest.fixture
def business_client():
    """复用已确认的隔离库，以业务Key访问独立的随机验收企业范围。"""
    database = os.getenv("MODARCHITECT_TEST_DATABASE_URL")
    if not database:
        pytest.skip("An isolated PostgreSQL database is required")
    scope = {"provider_name": "design-loop-" + uuid4().hex[:10], "company_id": 1}
    with TestClient(create_app(database_url=database, api_key="design-loop-only", authentication_mode="api_key")) as client:
        client.headers["X-Modarchitect-Api-Key"] = "design-loop-only"
        yield client, scope


@pytest.mark.parametrize("future_model", [False, True])
def test_check_save_query_and_graph_references_share_one_validated_definition(business_client, future_model: bool) -> None:
    """正式保存重验，错误不落库，成功回执可重放，查询可复原全部节点和连线。"""
    client, scope = business_client
    templates = client.get(API + "/study-templates", params=scope)
    assert templates.status_code == 200 and len(templates.json()["items"]) == 20
    assert client.get(API + "/study-templates/crop-growth-prediction", params=scope).status_code == 200
    plan = all_indicator_design(client)
    if future_model:
        plan = deferred_model_design(plan)
    configuration = client.post(API + "/configurations/draft", json=plan).json()
    checked = client.post(API + "/configurations/check", json=configuration)
    assert checked.status_code == 200 and checked.json()["valid"], checked.text
    invalid = deepcopy(plan)
    invalid["composition"]["nodes"][0]["bindings"] = []
    bad = client.post(API + "/configurations/draft", json=invalid).json()
    issues = client.post(API + "/configurations/check", json=bad).json()["issues"]
    assert issues[0]["node"] == plan["composition"]["nodes"][0]["code"] and issues[0]["port"]
    key = str(uuid4())
    rejected = client.post(API + "/design-saves", headers={"Idempotency-Key": key}, json={**scope, "configuration": bad})
    assert rejected.status_code == 422 and rejected.json()["issues"] == issues
    assert client.get(API + "/design-saves/" + key, params=scope).status_code == 404
    assert not client.get(API + "/design-drafts", params=scope).json()["items"]
    body = {**scope, "configuration": configuration}
    saved = client.post(API + "/design-saves", headers={"Idempotency-Key": key}, json=body)
    assert saved.status_code == 200, saved.text
    receipt = saved.json()
    assert set(receipt) == {"design_id", "revision", "configuration_sha256"}
    assert client.post(API + "/design-saves", headers={"Idempotency-Key": key}, json=body).json() == receipt
    reopened = client.get(API + "/design-drafts/" + receipt["design_id"], params=scope).json()
    assert reopened["configuration"] == configuration and reopened["configuration_sha256"] == identity_sha256(configuration)
    assert reopened["configuration"]["definition"]["composition"] == plan["composition"]
    assert client.get(API + "/design-drafts", params=scope).json()["items"][0]["design_id"] == receipt["design_id"]
    assert client.get(API + "/design-drafts/" + receipt["design_id"], params={**scope, "company_id": 2}).status_code == 404


def test_invalid_indicator_and_parameter_issues_locate_the_original_fields() -> None:
    """指标科学单位和方法参数错误分别定位，不能只返回笼统错误。"""
    with TestClient(create_app()) as client:
        plan = all_indicator_design(client)
    bad = deepcopy(plan)
    bad["variables"][0]["unit"] = "wrong_unit"
    issue = check_definition(bad)["issues"][0]
    assert issue["path"] == ["variables", 0, "unit"]
    bad = deepcopy(plan)
    config = next(recipe for recipe in bad["input_recipes"].values() if recipe["kind"] == "configuration")
    config["value"]["training_end"] = "invalid-date"
    issue = check_definition(bad)["issues"][0]
    assert issue["path"][-1] == "training_end" and issue["node"]
