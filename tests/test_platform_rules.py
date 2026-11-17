# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 18:42
# @Author  : Codex
# @File    : test_platform_rules.py
"""从正常 API 验证输入增删规则、只读预检和启动一致性及准确运行流程。"""

from copy import deepcopy
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from modarchitect.api import create_app
from test_research_runtime import BASE, WRITE, ScientificRunner, calculate_next
from test_research_runtime import runtime_clients as runtime_clients


def test_public_policies_distinguish_records_variables_and_fixed_sources(monkeypatch):
    """公开能力不能把改日期误写成可替换来源，也不授予演示真实数据资格。"""
    monkeypatch.setenv("MODARCHITECT_WORKSPACE_KEY", "flow-test-" * 8)
    with TestClient(create_app()) as client:
        listing = client.get(BASE + "/study-templates").json()["items"]
        policies = {row["id"]: row["input_policy"] for row in listing}
        assert sum(policy["mode"] == "approved_dataset" for policy in policies.values()) == 8
        assert sum(policy["mode"] == "user_observations" for policy in policies.values()) == 11
        assert policies["growth-trend-and-environment"]["mode"] == "synthetic_demo_only"
        fixed = policies["growth-water-response"]
        assert fixed["editable"] == ["indicators"]
        ordinary = policies["crop-growth-prediction"]
        assert ordinary["editable"] == ["records", "inputs", "factors", "targets"]
        assert all(set(policy) == {"mode", "editable"} for policy in policies.values())
        rules = client.get("/api/v1/model-center/research-rules").json()
        assert set(rules) == {"version", "rules"}
        assert len(rules["rules"]) == 9
        assert client.post(BASE + "/check-execution", headers=WRITE, json={}).status_code in {401, 503}
        client.get(BASE + "/session")
        for row in listing:
            detail = client.get(BASE + "/study-templates/" + row["id"]).json()
            assert detail["input_policy"] == row["input_policy"]
            assert "artifact_inputs" not in json.dumps(detail) and "bundle_sha256" not in json.dumps(detail)


def _changed(study: dict, change: str) -> dict:
    """只改变一个研究条件，让预检和启动面对同一候选方案及数据。"""
    body = deepcopy(study)
    plan, table = body["definition"], body["observations"]
    settings = plan["input_recipes"]["regression_config"]["value"]
    if change == "missing_factor_data":
        code = settings["features"][0]
        table["columns"] = [column for column in table["columns"] if column["code"] != code]
        for row in table["rows"]:
            del row["values"][code]
    elif change == "delete_targets":
        settings["targets"] = []
    elif change == "delete_required_input":
        plan["composition"]["inputs"] = [port for port in plan["composition"]["inputs"] if port["code"] != "observations"]
        del plan["input_recipes"]["observations"]
    elif change == "wrong_unit":
        table["columns"][0]["unit"] = "cm"
    elif change == "estimated_label":
        target = settings["targets"][0]
        next(column for column in table["columns"] if column["code"] == target)["value_kind"] = "estimated"
    return body


@pytest.mark.parametrize("change", ["missing_factor_data", "delete_targets", "delete_required_input", "wrong_unit", "estimated_label"])
def test_preflight_and_start_reject_same_input_rule_without_enqueue(runtime_clients, change):
    """新增缺列、错误删除、错单位与伪标签在预检和实际启动均阻断且不入队。"""
    client, _ = runtime_clients
    study = client.get(BASE + "/examples/system").json()
    candidate = _changed(study, change)
    check = client.post(BASE + "/check-execution", headers=WRITE,
                        json={"definition": candidate["definition"], "observations": candidate["observations"],
                              "operation": "train", "data_kind": "user_supplied"})
    assert check.status_code == 200, check.text
    assert check.json()["can_execute"] is False
    assert check.json()["issues"][0]["rule"]
    assert client.get(BASE + "/plans").json()["items"] == []
    assert client.get(BASE + "/runs").json()["items"] == []
    saved = client.post(BASE + "/plans", headers={**WRITE, "Idempotency-Key": str(uuid4())},
                        json={"definition": candidate["definition"], "data_kind": "user_supplied"})
    assert saved.status_code == 200, saved.text
    rejected = client.post(BASE + "/runs", headers={**WRITE, "Idempotency-Key": str(uuid4())},
                           json={"design_id": saved.json()["design_id"], "expected_revision": 1,
                                 "observations": candidate["observations"], "data_kind": "user_supplied", "operation": "train"})
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["issues"][0]["rule"] == check.json()["issues"][0]["rule"]
    assert client.get(BASE + "/runs").json()["items"] == []


def test_input_remove_add_then_real_model_and_historical_flow(runtime_clients):
    """合法增删因素后可运行，流程沿准确版本解释，另一工作区不能读取。"""
    client, other = runtime_clients
    original = client.get(BASE + "/examples/system").json()
    smaller = deepcopy(original)
    plan, table = smaller["definition"], smaller["observations"]
    config = plan["input_recipes"]["regression_config"]["value"]
    code = config["features"].pop()
    plan["variables"] = [value for value in plan["variables"] if value["code"] != code]
    plan["collection_requirements"] = [value for value in plan["collection_requirements"] if value["variable_code"] != code]
    plan["input_recipes"]["observations"]["variable_codes"].remove(code)
    table["columns"] = [column for column in table["columns"] if column["code"] != code]
    for value in table["rows"]:
        del value["values"][code]
    for study in (smaller, original):
        checked = client.post(BASE + "/check-execution", headers=WRITE,
                              json={"definition": study["definition"], "observations": study["observations"], "operation": "train", "data_kind": "user_supplied"})
        assert checked.status_code == 200 and checked.json()["can_execute"], checked.text
    saved = client.post(BASE + "/plans", headers={**WRITE, "Idempotency-Key": str(uuid4())},
                        json={"definition": original["definition"], "observations": original["observations"], "data_kind": "user_supplied"}).json()
    started = client.post(BASE + "/runs", headers={**WRITE, "Idempotency-Key": str(uuid4())},
                          json={"design_id": saved["design_id"], "expected_revision": 1, "observations": original["observations"], "operation": "train", "data_kind": "user_supplied"})
    assert started.status_code == 200, started.text
    completed, _ = calculate_next(client, ScientificRunner())
    run_id = started.json()["run_id"]
    assert completed["status"] == "succeeded"
    flow = client.get(BASE + "/runs/" + run_id + "/plan")
    assert flow.status_code == 200, flow.text
    value = flow.json()
    assert value == original["definition"]
    assert other.get(BASE + "/runs/" + run_id + "/plan").status_code == 404
    edited = deepcopy(original["definition"])
    previous = edited["input_recipes"]["regression_config"]["value"]["training_end"]
    edited["input_recipes"]["regression_config"]["value"]["training_end"] = "2026-05-09"
    updated = client.put(BASE + "/plans/" + saved["design_id"], headers=WRITE,
                         json={"definition": edited, "expected_revision": 1, "data_kind": "user_supplied"})
    assert updated.status_code == 200, updated.text
    current = client.get(BASE + "/plans/" + saved["design_id"]).json()["configuration"]["definition"]
    historic = client.get(BASE + "/runs/" + run_id + "/plan").json()
    assert "2026-05-09" in json.dumps(current)
    assert previous in json.dumps(historic) and "2026-05-09" not in json.dumps(historic)


def test_fixed_dataset_edits_are_separate_from_input_replacement(runtime_clients):
    """指定资料不接受上传、结构增删或越权参数；合法参数仍可只读预检。"""
    client, _ = runtime_clients
    row = client.get(BASE + "/study-templates/greenhouse-water-use").json()
    body = {"definition": row["definition"], "operation": row["operation"]}
    checked = client.post(BASE + "/check-execution", headers=WRITE, json=body)
    assert checked.status_code == 200 and checked.json()["can_execute"], checked.text
    body["definition"]["evaluation"]["maximum_runs"] = 2
    checked = client.post(BASE + "/check-execution", headers=WRITE, json=body)
    assert not checked.json()["can_execute"]
    assert checked.json()["issues"][0]["rule"] == "template_edit"
    body["observations"] = client.get(BASE + "/examples/system").json()["observations"]
    checked = client.post(BASE + "/check-execution", headers=WRITE, json=body)
    assert checked.json()["issues"][0]["rule"] == "template_identity"
    assert client.get(BASE + "/runs").json()["items"] == []


def test_unknown_indicator_is_refused_by_preflight_and_start(runtime_clients):
    """格式正确但资料不含的指标不能绕过复选范围进入任务队列。"""
    client, _ = runtime_clients
    row = client.get(BASE + "/study-templates/growth-water-response").json()
    row["definition"]["input_recipes"]["settings"]["value"]["variables"] = ["unknown_indicator"]
    checked = client.post(BASE + "/check-execution", headers=WRITE,
                          json={"definition": row["definition"], "operation": row["operation"]})
    assert checked.status_code == 200 and not checked.json()["can_execute"], checked.text
    issue = checked.json()["issues"][0]
    assert issue["rule"] == "input_bindings"
    assert issue["path"] == ["input_recipes", "settings", "value", "variables"]
    saved = client.post(BASE + "/plans", headers={**WRITE, "Idempotency-Key": str(uuid4())},
                        json={"definition": row["definition"]}).json()
    rejected = client.post(BASE + "/template-runs", headers={**WRITE, "Idempotency-Key": str(uuid4())},
                           json={"design_id": saved["design_id"], "expected_revision": 1,
                                 "template_id": row["id"], "template_sha256": row["sha256"]})
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["issues"][0] == issue
    assert client.get(BASE + "/runs").json()["items"] == []
