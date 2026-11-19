# -*- coding: utf-8 -*-
# @Time    : 2026/11/17 21:16
# @Author  : Codex
# @File    : test_calendar_axis.py
"""验证平台日期坐标、稀疏记录、来源边界及训练预测共同血缘。"""

from copy import deepcopy
from datetime import date
import json
from pathlib import Path

import pytest

from components.field_research.calendar import calendar_axis
from modarchitect.contracts.research.plans import ResearchPlan
from modarchitect.execution_contracts import external_input_codes
from modarchitect.runtime.contracts import ObservationTable
from modarchitect.runtime.executor import execute
from modarchitect.runtime.preparation import prepare_observations, prepare_prediction
from modarchitect.validation import check_definition
from modarchitect.system_inputs import seal_input_sources
from test_research_runtime import ScientificRunner, profiles_file
from test_research_runtime import runtime_clients, calculate_next  # noqa: F401

ROOT = Path(__file__).parents[1]


def calendar_sample() -> dict:
    """采用随制品发布的固定目录样例，不读取业务库或临时环境。"""
    return json.loads((ROOT / "modarchitect/web/designer/calendar-study.json").read_text(encoding="utf-8"))


def test_calendar_driver_is_not_external_and_never_becomes_a_training_label():
    """日期来自平台派生节点，原始输入仅需目标实测且不能上传伪造日期列。"""
    sample = calendar_sample()
    plan = ResearchPlan.model_validate(sample["definition"])
    assert check_definition(sample["definition"])["valid"]
    assert external_input_codes(plan, "train") == {"agb_kg_ha"}
    assert external_input_codes(plan, "predict") == set()
    bad = deepcopy(sample["definition"])
    bad["evaluation"]["target_codes"] = ["platform_calendar_day"]
    bad["input_recipes"]["growth_config"]["value"]["target_code"] = "platform_calendar_day"
    assert not check_definition(bad)["valid"]
    forged = deepcopy(sample["observations"])
    forged["columns"].append({"code": "platform_calendar_day", "name": "观测日期坐标", "unit": "day", "value_kind": "observed"})
    for row in forged["rows"]:
        row["values"]["platform_calendar_day"] = 1
    with pytest.raises(ValueError, match="not a declared external input"):
        seal_input_sources(sample["definition"], forged, "synthetic", "calendar-test")


def test_calendar_training_and_date_only_prediction_keep_the_same_axis(tmp_path):
    """使用真实逻辑斯蒂算法训练与预测，预测只有对象日期，不重新要求天数或目标。"""
    sample = calendar_sample()
    profiles = json.loads(profiles_file(tmp_path / "calendar-profiles.json").read_text())
    prepared = prepare_observations(sample["definition"], "train", ObservationTable.model_validate(sample["observations"]), "synthetic", "calendar-test", lambda _: profiles)
    trained = execute(prepared.payload, ScientificRunner())
    assert trained["pipeline"]["states"]
    assert max(metric["rmse"] for metric in trained["metrics"] if metric["status"] == "evaluated") < 0.001
    table = ObservationTable.model_validate(sample["prediction_observations"])
    model = {"model_json": trained["pipeline"], "model_id": "calendar-model", "model_sha256": "a" * 64}
    prediction = prepare_prediction(model, table, "synthetic", "calendar-test", profiles, [])
    result = execute(prediction.payload, ScientificRunner())
    assert len(result["outputs"]["forecast"]["rows"]) == 1
    assert result["outputs"]["forecast"]["rows"][0]["business_date"] == "2026-06-15"
    assert result["outputs"]["forecast"]["rows"][0]["values"]["agb_kg_ha"] > 5000
    with pytest.raises(ValueError, match="variable or scientific unit"):
        prepare_observations(sample["definition"], "train", table, "synthetic", "calendar-test", lambda _: profiles)


def test_calendar_example_saves_runs_and_predicts_through_api(runtime_clients):  # noqa: F811
    """真实隔离库通过正式API保存、重开、计算、登记模型及只传日期的预测。"""
    from uuid import uuid4

    client, other = runtime_clients
    sample = client.get("/api/v1/workspace/examples/calendar").json()
    headers = {"X-Workspace-Request": "1", "Idempotency-Key": str(uuid4())}
    saved = client.post("/api/v1/workspace/plans", headers=headers, json={"definition": sample["definition"], "observations": sample["observations"], "data_kind": "synthetic"})
    assert saved.status_code == 200, saved.text
    saved = saved.json()
    reopened = client.get("/api/v1/workspace/plans/" + saved["design_id"])
    assert reopened.json()["configuration"]["definition"] == sample["definition"]
    launched = client.post("/api/v1/workspace/runs", headers={**headers, "Idempotency-Key": str(uuid4())}, json={"design_id": saved["design_id"], "expected_revision": saved["revision"], "observations": sample["observations"], "data_kind": "synthetic"})
    assert launched.status_code == 200, launched.text
    completed, _ = calculate_next(client, ScientificRunner())
    assert completed["status"] == "succeeded"
    model = client.post("/api/v1/workspace/models", headers=headers, json={"run_id": completed["run_id"], "name": "平台日期生长模型"}).json()
    assert other.get("/api/v1/workspace/models/" + model["model_id"]).status_code == 404
    prediction = client.post("/api/v1/workspace/predictions", headers={**headers, "Idempotency-Key": str(uuid4())}, json={"model_id": model["model_id"], "observations": sample["prediction_observations"], "data_kind": "synthetic"})
    assert prediction.status_code == 200, prediction.text
    predicted, _ = calculate_next(client, ScientificRunner())
    assert predicted["status"] == "succeeded"


def test_dates_are_exact_sparse_and_do_not_restart_for_new_batches():
    """只换算已有业务日，换对象或预测批次都不按第一条记录重新归零。"""
    table = {"columns": [], "rows": [
        {"object": {"field_ref": field, "crop_code": "potato", "season_ref": "2026"}, "business_date": day, "values": {}}
        for field, day in [("a", "2026-04-01"), ("a", "2026-04-04"), ("b", "2026-04-04")]
    ], "source_sha256": ["a" * 64]}
    request = {"output_code": "calendar_day", "origin_date": "1970-01-01"}
    result = calendar_axis({"observations": table}, request)["table"]
    assert len(result["rows"]) == 3
    expected = (date(2026, 4, 4) - date(1970, 1, 1)).days
    assert result["rows"][1]["values"]["calendar_day"] == expected
    assert result["rows"][2]["values"]["calendar_day"] == expected
    prediction = deepcopy(table)
    prediction["rows"] = prediction["rows"][1:]
    assert calendar_axis({"observations": prediction}, request)["table"]["rows"][0]["values"]["calendar_day"] == expected
    assert table["columns"] == []
    for bad in [{**request, "origin_date": "2026-04-01"}, {**request, "origin_date": "sowing_date"}]:
        with pytest.raises(ValueError):
            calendar_axis({"observations": table}, bad)
    with pytest.raises(ValueError):
        calendar_axis({"observations": result}, request)
