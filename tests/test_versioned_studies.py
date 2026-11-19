# -*- coding: utf-8 -*-
# @Time    : 2026/11/18 22:25
# @Author  : Codex
# @File    : test_versioned_studies.py
"""通过实际接口验证方案版本、研究实例、数据快照和模型归属。"""

from copy import deepcopy
from datetime import date
from uuid import uuid4

import httpx

from modarchitect.input_sources.service import execute_acquisition
from test_design_api import AUTH, ROOT, SELECTION, create_draft, new_draft
from test_design_api import live_design_api as live_design_api
from test_input_acquisition import SOURCE_INTERNAL, source_plan, weather_response
from test_research_runtime import BASE, WORKER, WRITE, ScientificRunner, calculate_next, profiles_file
from test_research_runtime import runtime_clients as runtime_clients


def test_two_applied_versions_train_and_reopen_independent_models(runtime_clients):
    """编辑后老实例还能采编样本和训练，新实例用新版，模型各自可追溯。"""
    client, other = runtime_clients
    example = client.get(BASE + "/examples/multivariable").raise_for_status().json()
    original = example["definition"]
    response = client.post(BASE + "/plans", headers={**WRITE, "Idempotency-Key": str(uuid4())},
                           json={"definition": original, "version_name": "春季基线", "data_kind": "synthetic"})
    assert response.status_code == 200, response.text
    saved = response.json()
    draft = BASE + "/plans/" + saved["design_id"]

    def publish(revision):
        """通过正常入口固定指定修订。"""
        return client.post(draft + "/publish", headers=WRITE,
                           json={"expected_revision": revision}).raise_for_status().json()

    def apply(version, field, crop=None):
        """将同一模板应用到不同地块并回读固定对象。"""
        table = deepcopy(example["observations"])
        for record in table["rows"]:
            record["object"]["field_ref"] = field
            if crop:
                record["object"]["crop_code"] = crop
        body = {"design_version_id": version["design_version_id"],
                "observation_start": min(row["business_date"] for row in table["rows"]),
                "observation_end": max(row["business_date"] for row in table["rows"]),
                "objects": [{"object": table["rows"][0]["object"], "reference_point": {"latitude": 39, "longitude": 116}}]}
        headers = {**WRITE, "Idempotency-Key": str(uuid4())}
        instance = client.post(BASE + "/studies", headers=headers, json=body).raise_for_status().json()
        assert client.post(BASE + "/studies", headers=headers, json=body).json() == instance
        path = BASE + "/studies/" + instance["study_id"]
        assert client.get(path).json() == instance and other.get(path).status_code == 404
        return path, instance, table

    a_version = publish(saved["revision"])
    assert a_version["version_name"] == "春季基线"
    first = apply(a_version, "field-a")
    same_version = apply(a_version, "field-c", crop="maize")
    changed = deepcopy(original)
    config = next(r for r in changed["input_recipes"].values() if "features" in r.get("value", {}))
    original_features = config["value"]["features"][:]
    config["value"]["features"] = original_features[:-1]
    response = client.put(draft, headers=WRITE, json={"definition": changed, "expected_revision": saved["revision"],
                                                      "version_name": "缩减因子版", "data_kind": "synthetic"})
    assert response.status_code == 200, response.text
    update = response.json()
    b_version = publish(update["revision"])
    assert b_version["version_name"] == "缩减因子版" and a_version["design_version_id"] != b_version["design_version_id"]
    second = apply(b_version, "field-b")

    def dataset(instance):
        """持久化本次应用的观测，再验证可以按原实例回读。"""
        path, _, table = instance
        reply = client.post(path + "/datasets", headers=WRITE,
                            json={"observations": table, "data_kind": "synthetic"}).raise_for_status().json()
        snapshot_id = reply["dataset_snapshot_id"]
        assert client.get(path + "/datasets/" + snapshot_id).json()["observations"]["rows"] == table["rows"]
        return snapshot_id

    data_a, data_b = dataset(first), dataset(second)
    assert client.get(same_version[0] + "/datasets/" + data_a).status_code == 404
    assert client.post(second[0] + "/runs", headers={**WRITE, "Idempotency-Key": str(uuid4())},
                       json={"dataset_snapshot_id": data_a, "operation": "train"}).status_code == 409
    assert client.post(second[0] + "/datasets", headers=WRITE,
                       json={"observations": first[2], "data_kind": "synthetic"}).status_code == 422

    runner = ScientificRunner()
    models = []
    for (path, instance, _), snapshot_id, version, features in (
        (first, data_a, a_version, original_features), (second, data_b, b_version, original_features[:-1]),
    ):
        payload = {"dataset_snapshot_id": snapshot_id, "operation": "train"}
        headers = {**WRITE, "Idempotency-Key": str(uuid4())}
        run = client.post(path + "/runs", headers=headers, json=payload).raise_for_status().json()
        assert client.post(path + "/runs", headers=headers, json=payload).json()["run_id"] == run["run_id"]
        completed, _ = calculate_next(client, runner)
        assert completed["run_id"] == run["run_id"] and completed["status"] == "succeeded"
        frozen = client.get(BASE + "/runs/" + completed["run_id"] + "/plan").raise_for_status().json()
        settings = next(r for r in frozen["input_recipes"].values() if "features" in (r.get("value") or {}))
        assert settings["value"]["features"] == features
        model = client.post(path + "/models", headers=WRITE,
                            json={"run_id": completed["run_id"], "name": version["version_name"]}).raise_for_status().json()
        reopened = client.get(BASE + "/models/" + model["model_id"]).raise_for_status().json()
        assert reopened["design_version_id"] == version["design_version_id"]
        assert reopened["study_id"] == instance["study_id"] and reopened["dataset_snapshot_id"] == snapshot_id
        models.append(reopened)
    assert models[0]["model_id"] != models[1]["model_id"]
    assert models[0]["model_sha256"] != models[1]["model_sha256"]
    prediction = client.post(BASE + "/predictions", headers={**WRITE, "Idempotency-Key": str(uuid4())},
                             json={"model_id": models[0]["model_id"], "data_kind": "synthetic",
                                   "observations": example["prediction_observations"]}).raise_for_status().json()
    assert prediction["design_version_id"] == a_version["design_version_id"]
    completed, _ = calculate_next(client, runner)
    assert completed["status"] == "succeeded"


def test_business_applied_scope_verifies_points_and_acquisition_lineage(live_design_api, monkeypatch, tmp_path):
    """应用时按业务取证保存点位，采集从已固定的对象范围取坐标。"""
    client, _ = live_design_api
    definition = source_plan()
    draft = create_draft(client, new_draft(client, definition)).raise_for_status().json()
    version = client.post(ROOT + "/design-drafts/" + draft["design_id"] + "/publish", headers=AUTH,
                          json={"expected_revision": draft["revision"]}).raise_for_status().json()
    body = {"design_version_id": version["design_version_id"], "observation_start": "2025-04-01", "observation_end": "2025-04-30",
            "fields": {"selection": SELECTION, "field_refs": ["field-a"]}, "point_refs": ["field-a-point"]}
    headers = {**AUTH, "Idempotency-Key": str(uuid4())}
    assert client.post(ROOT + "/studies", headers=headers, json={**body, "point_refs": ["outside"]}).status_code == 422
    study = client.post(ROOT + "/studies", headers=headers, json=body).raise_for_status().json()
    assert study["sampling_points"] == [{"point_ref": "field-a-point", "object": study["objects"][0]}]
    study_path = ROOT + "/studies/" + study["study_id"]
    assert client.get(study_path, headers={**AUTH, "X-Enterprise-Delegation": "other-company"}).status_code == 404
    acquisition = {"object": study["objects"][0], "start_date": "2025-04-01", "end_date": "2025-04-30"}
    path = study_path + "/input-acquisitions"
    assert client.post(path, headers=headers, json={**acquisition, "start_date": "2025-03-31"}).status_code == 422
    queued = client.post(path, headers=headers, json=acquisition).raise_for_status().json()
    assert client.get(path + "/" + queued["acquisition_id"], headers=AUTH).json() == queued
    other = client.post(ROOT + "/studies", headers={**AUTH, "Idempotency-Key": str(uuid4())}, json=body).raise_for_status().json()
    second = ROOT + "/studies/" + other["study_id"]
    assert client.get(second + "/input-acquisitions/" + queued["acquisition_id"], headers=AUTH).status_code == 404
    monkeypatch.setenv("MODARCHITECT_WORKER_KEY", WORKER["X-Research-Worker-Key"])
    monkeypatch.setenv("MODARCHITECT_WEATHER_ACCESS", "research")
    monkeypatch.setenv("MODARCHITECT_RUNTIME_PROFILES", str(profiles_file(tmp_path / "study-profiles.json")))
    job = client.post(SOURCE_INTERNAL + "/dispatch/next", headers=WORKER).raise_for_status().json()["job"]
    assert job["acquisition_id"] == queued["acquisition_id"]
    claim = client.post(SOURCE_INTERNAL + "/claim", headers=WORKER, json=job).raise_for_status().json()

    def provider(request):
        """测试采集协议及转换，外部提供方由工程响应替代。"""
        assert request.url.host == "archive-api.open-meteo.com"
        return httpx.Response(200, json=weather_response(date(2025, 4, 1), date(2025, 4, 30)))

    snapshots = execute_acquisition(claim["input"], lambda: None, transport=httpx.MockTransport(provider))
    done = client.post(SOURCE_INTERNAL + "/" + job["acquisition_id"] + "/complete", headers=WORKER,
                       json={"attempt_id": claim["attempt_id"], "result": {"snapshots": snapshots}}).raise_for_status().json()
    table = deepcopy(snapshots[0]["observations"])
    label = next(variable for variable in definition["variables"] if variable["code"] == "lai")
    table["columns"] = [{"code": "lai", "name": label["name"], "unit": label["unit"], "value_kind": "observed"}]
    for row in table["rows"]:
        row["values"] = {"lai": 1 + 0.1 * row["values"]["temperature_mean_daily"]}
    dataset_body = {"source_snapshot_ids": done["snapshot_ids"], "observations": table}
    data = client.post(study_path + "/datasets", headers=AUTH, json=dataset_body).raise_for_status().json()
    assert client.get(study_path + "/datasets/" + data["dataset_snapshot_id"], headers=AUTH).json()["source_snapshot_ids"] == done["snapshot_ids"]
    assert client.post(second + "/datasets", headers=AUTH, json=dataset_body).status_code == 404
    run = client.post(study_path + "/runs", headers=headers,
                      json={"dataset_snapshot_id": data["dataset_snapshot_id"], "operation": "train"}).raise_for_status().json()
    completed, _ = calculate_next(client, ScientificRunner())
    assert completed["status"] == "succeeded" and completed["run_id"] == run["run_id"]
    model = client.post(study_path + "/models", headers=AUTH,
                        json={"run_id": run["run_id"], "name": "固定业务实例模型"}).raise_for_status().json()
    assert model["study_id"] == study["study_id"] and model["design_version_id"] == version["design_version_id"]
    remote_input = next(item for item in model["model_json"]["input_sources"]["inputs"]
                        if item["variable"]["code"] == "temperature_mean_daily")
    assert remote_input["channel"] == "source_snapshot"
