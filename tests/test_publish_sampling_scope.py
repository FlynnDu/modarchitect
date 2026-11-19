# -*- coding: utf-8 -*-
# @Time    : 2026/11/19 20:02
# @Author  : Codex
# @File    : test_publish_sampling_scope.py
"""点位方案发布无需实际选地，应用时必须覆盖每块授权地块。"""

from uuid import uuid4

import pytest

from test_design_api import AUTH, ROOT, SELECTION, fit_file
from test_design_api import live_design_api as live_design_api


def point_plan() -> dict:
    """保留准确历史拟合配置，附加独立的点位观测要求。"""
    plan = fit_file()["definition"]
    plan["variables"].append(
        {**plan["variables"][1], "code": "point_height", "role": "covariate"}
    )
    plan["collection_requirements"].append({
        **plan["collection_requirements"][1], "code": "height_collection",
        "variable_code": "point_height", "unit_kind": "point",
        "requires_sampling_points": True,
    })
    assert plan.get("sampling_selection") is None
    return plan


def save_point_plan(client, headers: dict, scope: dict) -> dict:
    """使用正式保存入口复现业务端已经能完成的无选地保存。"""
    configuration = client.post(ROOT + "/configurations/draft", headers=headers, json=point_plan())
    configuration.raise_for_status()
    saved = client.post(ROOT + "/design-saves", params=scope,
                        headers={**headers, "Idempotency-Key": str(uuid4())},
                        json={"configuration": configuration.json()})
    assert saved.status_code == 200, saved.text
    return saved.json()


@pytest.mark.parametrize("api_key_mode", [False, True])
def test_unbound_point_plan_publishes_without_business_selection(live_design_api, api_key_mode):
    """正式保存及固定版本不取业务选地，重复发布和历史读回一致。"""
    client, state = live_design_api
    headers, scope = AUTH, {}
    if api_key_mode:
        client.app.state.authentication_mode = "api_key"
        headers = {"X-Modarchitect-Api-Key": AUTH["X-MLGrowth-Business-Key"]}
        scope = {"provider_name": "biology-institute", "company_id": 17}
    saved = save_point_plan(client, headers, scope)
    path = ROOT + "/design-drafts/" + saved["design_id"]
    current = client.get(path, headers=headers, params=scope).raise_for_status().json()
    definition = current["configuration"]["definition"]
    definition["question"] = "发布可复用点位方案，应用时再选择地块"
    configuration = client.post(ROOT + "/configurations/draft", headers=headers, json=definition).raise_for_status().json()
    updated = client.post(ROOT + "/design-saves", headers={**headers, "Idempotency-Key": str(uuid4())},
                          params=scope, json={"configuration": configuration, "design_id": saved["design_id"],
                                              "expected_revision": saved["revision"]}).raise_for_status().json()
    revision = {"expected_revision": updated["revision"]}
    published = client.post(path + "/publish", headers=headers, params=scope, json=revision)
    assert published.status_code == 200, published.text
    assert state["calls"] == 0
    version = published.json()
    assert version["definition"]["research_plan"].get("sampling_selection") is None
    assert version["inspection"]["checks"]["execution"]["status"] == "not_checked"
    assert client.post(path + "/publish", headers=headers, params=scope, json=revision).json() == version
    assert client.get(ROOT + "/design-versions/" + version["design_version_id"],
                      headers=headers, params=scope).json() == version


def test_point_plan_application_requires_selected_points_for_each_business_field(live_design_api):
    """逐地块点位覆盖必须由实际应用核验，目录存在点位不能代替选择。"""
    client, state = live_design_api
    saved = save_point_plan(client, AUTH, {})
    published = client.post(ROOT + "/design-drafts/" + saved["design_id"] + "/publish", headers=AUTH,
                            json={"expected_revision": saved["revision"]}).raise_for_status().json()
    body = {"design_version_id": published["design_version_id"], "observation_start": "2025-04-01",
            "observation_end": "2025-04-30", "fields": {"selection": SELECTION, "field_refs": ["field-a", "field-b"]},
            "point_refs": ["field-a-point"]}
    headers = {**AUTH, "Idempotency-Key": str(uuid4())}
    assert client.post(ROOT + "/studies", headers=headers,
                       json={key: value for key, value in body.items() if key != "fields"}).status_code == 422
    assert client.post(ROOT + "/studies", headers=headers, json={**body, "point_refs": []}).status_code == 422
    missing = client.post(ROOT + "/studies", headers=headers, json=body)
    assert missing.status_code == 422 and "each selected business field" in missing.json()["detail"]
    state["second_point"] = True
    missing = client.post(ROOT + "/studies", headers=headers, json=body)
    assert missing.status_code == 422 and "each selected business field" in missing.json()["detail"]
    assert client.post(ROOT + "/studies", headers=headers,
                       json={**body, "point_refs": ["outside"]}).status_code == 422
    assert client.post(ROOT + "/studies", headers=headers,
                       json={**body, "point_refs": ["field-a-point", "field-a-point"]}).status_code == 422
    complete = {**body, "point_refs": ["field-a-point", "field-b-point"]}
    created = client.post(ROOT + "/studies", headers=headers, json=complete)
    assert created.status_code == 201, created.text
    study = created.json()
    assert len(study["objects"]) == len(study["sampling_points"]) == 2
    assert client.get(ROOT + "/studies/" + study["study_id"],
                      headers={**AUTH, "X-Enterprise-Delegation": "other-company"}).status_code == 404
