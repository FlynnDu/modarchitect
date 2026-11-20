# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 21:52
# @Author  : Codex
# @File    : test_research_runtime.py
"""通过真实方案与低权限数据库验证训练、模型复用及工作区隔离。"""

from copy import deepcopy
from datetime import date, timedelta
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from modarchitect.api import create_app
from modarchitect.catalog import catalog
from modarchitect.runtime.containers import Artifact
from modarchitect.runtime.executor import evaluate, execute

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "components/logistic_growth/src"))

WORKER = {"X-Research-Worker-Key": "worker-test-" * 8}
WRITE = {"X-Workspace-Request": "1"}
BASE = "/api/v1/workspace"
INTERNAL = "/internal/v1/research"
INFERENCE = {
    "historical_logistic_training": "historical_logistic_predict",
    "multivariate_linear_training": "multivariate_linear_predict",
}


class ScientificRunner:
    """用真实科学实现替代容器传输，保留每一步准确成果和调用。"""

    def __init__(self):
        """收集实际调用的组件，核对预测阶段没有重新训练。"""
        self.calls = []

    def call(self, component, profile, parameters, inputs):
        """调用实际算法并按准确字节返回成果。"""
        from components.forecast_join.component import join_forecast
        from components.research_runtime.growth import forecast
        from components.research_runtime.growth import predict as predict_growth
        from components.research_runtime.linear import predict as predict_linear
        from components.research_runtime.linear import train as train_linear
        from components.descriptive_statistics.component import summarize
        from components.field_research.weather import conditions
        from components.field_research.ndvi import derive_ndvi
        from components.field_research.calendar import calendar_axis

        code = component["code"]
        functions = {
            "historical_logistic_training": forecast,
            "historical_logistic_predict": predict_growth,
            "research_forecast_feature_join": join_forecast,
            "multivariate_linear_training": train_linear,
            "multivariate_linear_predict": predict_linear,
            "research_descriptive_statistics": summarize,
            "catalog_weather_conditions": conditions,
            "sentinel_ndvi_features": derive_ndvi,
            "research_calendar_axis": calendar_axis,
        }
        self.calls.append(code)
        results = functions[code](
            {key: value.value for key, value in inputs.items()}, parameters
        )
        return {key: Artifact.encode(value) for key, value in results.items()}


def profiles_file(path: Path) -> Path:
    """生成测试制品登记表，科学代码保持实际实现。"""
    profiles = {}
    for (code, revision), entry in catalog().items():
        profile = {
            "image": "sha256:" + sha256(code.encode()).hexdigest(),
            "outputs": [port.code for port in entry.definition.outputs],
        }
        if code in INFERENCE:
            profile["inference"] = INFERENCE[code] + "@1"
            profile["state_output"] = "trained_model"
        profiles["%s@%s" % (code, revision)] = profile
    path.write_text(json.dumps(profiles), encoding="utf-8")
    return path


@pytest.fixture
def runtime_clients(monkeypatch, tmp_path):
    """使用项目专用 PostgreSQL，两个真实 Cookie 空间共享受保护数据库。"""
    database = os.getenv("MODARCHITECT_TEST_DATABASE_URL")
    if not database:
        pytest.skip("Requires the dedicated modarchitect PostgreSQL test database")
    monkeypatch.setenv("MODARCHITECT_WORKSPACE_KEY", "workspace-test-" * 8)
    monkeypatch.setenv("MODARCHITECT_WORKER_KEY", WORKER["X-Research-Worker-Key"])
    monkeypatch.setenv(
        "MODARCHITECT_RUNTIME_PROFILES", str(profiles_file(tmp_path / "profiles.json"))
    )
    app = create_app(database_url=database)
    with TestClient(app) as first, TestClient(app) as second:
        assert first.get(BASE + "/session").status_code == 200
        assert second.get(BASE + "/session").status_code == 200
        yield first, second


def calculate_next(client, runner):
    """按正式内部 HTTP 领取和回传路径驱动一次科学计算。"""
    job = client.post(INTERNAL + "/dispatch/next", headers=WORKER).json()["job"]
    claimed = client.post(
        INTERNAL + "/claim",
        headers=WORKER,
        json={"run_id": job["run_id"], "dispatch_token": job["dispatch_token"]},
    )
    assert claimed.status_code == 200, claimed.text
    claim = claimed.json()
    result = execute(claim["input"], runner)
    body = {"attempt_id": claim["attempt_id"], "result": result}
    response = client.post(
        INTERNAL + "/runs/" + job["run_id"] + "/complete", headers=WORKER, json=body
    )
    assert response.status_code == 200, response.text
    return response.json(), body


@pytest.mark.parametrize("kind", ["multivariable", "chain"])
def test_saved_study_trains_reopens_and_predicts_without_refitting(
    runtime_clients, kind
):
    """两个真实方案均保存、执行、登记模型和独立预测，跨空间访问被拒绝。"""
    client, other = runtime_clients
    example = client.get(BASE + "/examples/" + kind).json()
    saved = client.post(
        BASE + "/plans",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={
            "definition": example["definition"],
            "observations": example["observations"],
            "data_kind": "synthetic",
        },
    )
    assert saved.status_code == 200, saved.text
    saved = saved.json()
    reopened = client.get(BASE + "/plans/" + saved["design_id"])
    assert reopened.json()["observations"]["rows"] == example["observations"]["rows"]
    body = {
        "design_id": saved["design_id"],
        "expected_revision": saved["revision"],
        "observations": example["observations"],
        "data_kind": "synthetic",
    }
    headers = {**WRITE, "Idempotency-Key": str(uuid4())}
    run = client.post(BASE + "/runs", headers=headers, json=body)
    assert run.status_code == 200, run.text
    assert (
        client.post(BASE + "/runs", headers=headers, json=body).json()["run_id"]
        == run.json()["run_id"]
    )
    runner = ScientificRunner()
    completed, callback = calculate_next(client, runner)
    assert completed["status"] == "succeeded"
    assert (
        max(metric["rmse"] for metric in completed["result_json"]["metrics"]) < 0.0001
    )
    repeated = client.post(
        INTERNAL + "/runs/" + completed["run_id"] + "/complete",
        headers=WORKER,
        json=callback,
    )
    assert repeated.json()["result_sha256"] == completed["result_sha256"]
    changed = deepcopy(callback)
    changed["result"]["data_kind"] = "tampered"
    assert (
        client.post(
            INTERNAL + "/runs/" + completed["run_id"] + "/complete",
            headers=WORKER,
            json=changed,
        ).status_code
        == 409
    )
    model = client.post(
        BASE + "/models",
        headers=WRITE,
        json={"run_id": completed["run_id"], "name": kind + " test model"},
    )
    assert model.status_code == 200, model.text
    model = model.json()
    assert other.get(BASE + "/runs/" + completed["run_id"]).status_code == 404
    assert other.get(BASE + "/models/" + model["model_id"]).status_code == 404
    original_states = deepcopy(model["model_json"]["states"])
    runner.calls.clear()
    prediction = client.post(
        BASE + "/predictions",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={
            "model_id": model["model_id"],
            "observations": example["prediction_observations"],
            "data_kind": "synthetic",
        },
    )
    assert prediction.status_code == 200, prediction.text
    result, _ = calculate_next(client, runner)
    assert "multivariate_linear_training" not in runner.calls
    assert "historical_logistic_training" not in runner.calls
    assert result["result_json"]["pipeline"]["states"] == original_states
    invalid = {
        "kind": "predict",
        "pipeline": model["model_json"],
        "observations": deepcopy(example["prediction_observations"]),
    }
    invalid["observations"]["source_sha256"] = ["0" * 64]
    invalid["observations"]["columns"][0]["unit"] = "wrong_unit"
    with pytest.raises(ValueError, match="unit"):
        execute(invalid, runner)
    outputs = result["result_json"]["outputs"]
    table = next(value for value in outputs.values() if "rows" in value)
    for row in table["rows"]:
        source = next(
            item
            for item in example["prediction_observations"]["rows"]
            if item["business_date"] == row["business_date"]
        )
        x = source["values"]
        if kind == "multivariable":
            expected = (
                20
                + 0.8 * x["day"]
                + 30 * x["ndvi"]
                + 10 * x["soil_water"]
                + 0.5 * x["temperature"]
            )
        else:
            expected = (
                0.85 * 100 / (1 + math.exp(-0.12 * (x["day"] - 25)))
                + 12 * x["ndvi"]
                + 10 * x["soil_water"]
                + 0.2 * x["temperature"]
                + 3
            )
        assert row["values"]["height"] == pytest.approx(expected, abs=0.0001)
    revised = deepcopy(example["definition"])
    revised["name"] += " revised"
    opened = client.post(BASE + "/design-versions/" + completed["design_version_id"] + "/drafts",
                         headers={**WRITE, "Idempotency-Key": str(uuid4())}).raise_for_status().json()
    assert (
        client.put(
            BASE + "/plans/" + saved["design_id"],
            headers=WRITE,
            json={"definition": revised, "expected_revision": opened["revision"]},
        ).status_code
        == 200
    )
    assert (
        client.post(BASE + "/runs", headers=headers, json=body).json()["run_id"]
        == completed["run_id"]
    )


def test_evaluation_requires_observed_matching_units_and_expected_dates():
    """错单位、预测标签和只输出容易日期均不能制造虚假的满覆盖评价。"""
    rows = [
        {
            "object": {"field_ref": "a", "crop_code": "tomato", "season_ref": "s"},
            "business_date": (date(2026, 4, 1) + timedelta(days=i)).isoformat(),
            "values": {"height": 1.0},
        }
        for i in range(10)
    ]
    column = {"code": "height", "name": "株高", "unit": "cm", "value_kind": "observed"}
    observed = {"columns": [column], "rows": rows}
    output = {
        "prediction": {
            "columns": [{**column, "value_kind": "predicted"}],
            "rows": rows[:1],
        }
    }
    sparse = evaluate(output, observed, {})[0]
    assert sparse["coverage"] == 0.1
    assert sparse["r2"] is None
    bad = deepcopy(observed)
    bad["columns"][0]["value_kind"] = "predicted"
    assert evaluate(output, bad, {})[0]["status"] == "awaiting_observations"
    bad["columns"][0].update(value_kind="observed", unit="m")
    assert evaluate(output, bad, {})[0]["status"] == "reference_unit_mismatch"


@pytest.mark.parametrize("unknown_dispatch", [False, True])
def test_expired_attempt_becomes_failed_and_cannot_publish(
    runtime_clients, unknown_dispatch
):
    """Worker 失联产生可查询终态，旧尝试随后回传仍被拒绝。"""
    from datetime import datetime, timezone
    from sqlalchemy import update
    from modarchitect.runtime.store import runs
    from modarchitect.runtime.workspace import COOKIE, principal

    client, _ = runtime_clients
    example = client.get(BASE + "/examples/multivariable").json()
    saved = client.post(
        BASE + "/plans",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={"definition": example["definition"], "data_kind": "synthetic"},
    ).json()
    run = client.post(
        BASE + "/runs",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={
            "design_id": saved["design_id"],
            "expected_revision": saved["revision"],
            "observations": example["observations"],
            "data_kind": "synthetic",
        },
    ).json()
    job = client.post(INTERNAL + "/dispatch/next", headers=WORKER).json()["job"]
    assert job["run_id"] == run["run_id"]
    if unknown_dispatch:
        assert (
            client.post(
                INTERNAL + "/runs/" + run["run_id"] + "/dispatch",
                headers=WORKER,
                json={"error": "response lost"},
            ).status_code
            == 200
        )
    claim = client.post(
        INTERNAL + "/claim",
        headers=WORKER,
        json={"run_id": job["run_id"], "dispatch_token": job["dispatch_token"]},
    ).json()
    runtime = client.app.state.research_runtime
    with runtime.store.store.transaction(principal(client.cookies[COOKIE])) as tx:
        tx.connection.execute(
            update(runs)
            .where(runs.c.run_id == run["run_id"])
            .values(lease_until=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
    client.post(INTERNAL + "/dispatch/next", headers=WORKER)
    assert client.get(BASE + "/runs/" + run["run_id"]).json()["status"] == "failed"
    late = client.post(
        INTERNAL + "/runs/" + run["run_id"] + "/complete",
        headers=WORKER,
        json={"attempt_id": claim["attempt_id"], "result": {}},
    )
    assert late.status_code == 409


def test_editing_only_observations_advances_shared_revision(runtime_clients):
    """仅编辑数据也能原子保存、重开，旧修订无法覆盖新数据。"""
    client, _ = runtime_clients
    example = client.get(BASE + "/examples/multivariable").json()
    body = {
        "definition": example["definition"],
        "observations": example["observations"],
        "data_kind": "synthetic",
    }
    saved = client.post(
        BASE + "/plans", headers={**WRITE, "Idempotency-Key": str(uuid4())}, json=body
    ).json()
    changed = deepcopy(body)
    changed["observations"]["rows"][0]["values"]["height"] += 1
    changed["expected_revision"] = saved["revision"]
    updated = client.put(
        BASE + "/plans/" + saved["design_id"], headers=WRITE, json=changed
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["revision"] == saved["revision"] + 1
    reopened = client.get(BASE + "/plans/" + saved["design_id"]).json()
    assert reopened["observations"]["rows"] == changed["observations"]["rows"]
    stale = client.put(
        BASE + "/plans/" + saved["design_id"],
        headers=WRITE,
        json={**body, "expected_revision": saved["revision"]},
    )
    assert stale.status_code == 409
    repeated = client.put(
        BASE + "/plans/" + saved["design_id"],
        headers=WRITE,
        json={**changed, "expected_revision": reopened["revision"]},
    )
    assert repeated.json()["revision"] == reopened["revision"]


def test_workspace_identity_and_internal_key_are_required(runtime_clients):
    """自定义请求头、签名会话和独立内部凭据均参与正常入口校验。"""
    client, _ = runtime_clients
    assert (
        client.post(
            BASE + "/models", json={"run_id": str(uuid4()), "name": "test"}
        ).status_code
        == 403
    )
    assert client.post(INTERNAL + "/dispatch/next").status_code == 401
    client.cookies.set("modarchitect_workspace", "forged.1.signature")
    assert client.get(BASE + "/plans").status_code == 401


def test_system_inputs_save_train_preserve_sources_and_predict(runtime_clients):
    """标准人工输入通过真实库和科学实现闭环，来源随模型保存并隔离。"""
    client, other = runtime_clients
    study = client.get(BASE + "/examples/system").json()
    saved = client.post(
        BASE + "/plans",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={
            "definition": study["definition"],
            "observations": study["observations"],
            "data_kind": "user_supplied",
        },
    )
    assert saved.status_code == 200, saved.text
    saved = saved.json()
    readiness = client.get(BASE + "/plans/" + saved["design_id"] + "/input-readiness")
    assert all(
        item["execution"]["channel"] == "workspace_manual_entry"
        for item in readiness.json()["items"]
    )
    assert (
        other.get(
            BASE + "/plans/" + saved["design_id"] + "/input-readiness"
        ).status_code
        == 404
    )
    body = {
        "design_id": saved["design_id"],
        "expected_revision": saved["revision"],
        "observations": study["observations"],
        "data_kind": "user_supplied",
    }
    response = client.post(
        BASE + "/runs", headers={**WRITE, "Idempotency-Key": str(uuid4())}, json=body
    )
    assert response.status_code == 200, response.text
    runner = ScientificRunner()
    completed, _ = calculate_next(client, runner)
    result = completed["result_json"]
    assert result["input_sources"] == result["pipeline"]["input_sources"]
    assert {record["channel"] for record in result["input_sources"]["inputs"]} == {
        "workspace_manual_entry"
    }
    assert {m["target"] for m in result["metrics"]} == {"lai", "agb_kg_ha"}
    assert max(m["rmse"] for m in result["metrics"]) < 0.0001
    model = client.post(
        BASE + "/models",
        headers=WRITE,
        json={"run_id": completed["run_id"], "name": "System input acceptance"},
    ).json()
    runner.calls.clear()
    predicted = client.post(
        BASE + "/predictions",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={
            "model_id": model["model_id"],
            "observations": study["prediction_observations"],
            "data_kind": "user_supplied",
        },
    )
    assert predicted.status_code == 200, predicted.text
    finished, _ = calculate_next(client, runner)
    assert runner.calls == ["multivariate_linear_predict"]
    assert (
        finished["result_json"]["pipeline"]["input_sources"]
        == model["model_json"]["input_sources"]
    )
    assert finished["result_json"]["input_sources"]["row_count"] == 3
    assert (
        finished["result_json"]["input_sources"]["sha256"]
        != result["input_sources"]["sha256"]
    )


def test_ordinary_workspace_cannot_save_or_train_unbound_variables(runtime_clients):
    """旧演示可以明确保存，删去系统绑定不能取得普通运行资格。"""
    client, _ = runtime_clients
    study = client.get(BASE + "/examples/multivariable").json()
    response = client.post(
        BASE + "/plans",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={"definition": study["definition"], "data_kind": "user_supplied"},
    )
    assert response.status_code == 422
    demo = client.post(
        BASE + "/plans",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={"definition": study["definition"], "data_kind": "synthetic"},
    )
    assert demo.status_code == 200, demo.text
    body = {
        "design_id": demo.json()["design_id"],
        "expected_revision": demo.json()["revision"],
        "observations": study["observations"],
        "data_kind": "user_supplied",
    }
    assert (
        client.post(
            BASE + "/runs",
            headers={**WRITE, "Idempotency-Key": str(uuid4())},
            json=body,
        ).status_code
        == 422
    )
    assert client.get(BASE + "/runs").json()["items"] == []


def test_pre_upgrade_queued_input_keeps_legacy_model_prediction(runtime_clients):
    """旧版本已封存任务由新 Worker 完成后仍能预测，不伪造缺失来源证据。"""
    from uuid import UUID
    from modarchitect.contracts.identifiers import identity_sha256
    from modarchitect.contracts.research.plans import ResearchPlan
    from modarchitect.runtime.contracts import ObservationTable
    from modarchitect.runtime.service import execution_profiles
    from modarchitect.runtime.workspace import COOKIE, principal
    from modarchitect.validation import compile_plan

    client, _ = runtime_clients
    study = client.get(BASE + "/examples/multivariable").json()
    saved = client.post(
        BASE + "/plans",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={"definition": study["definition"], "data_kind": "synthetic"},
    ).json()
    owner = principal(client.cookies[COOKIE])
    runtime = client.app.state.research_runtime
    version = runtime.designs.publish(
        owner, UUID(saved["design_id"]), saved["revision"]
    )
    # 模拟升级前已经封存的形状；新的普通用户训练仍必须通过系统目录门槛。
    payload = {
        "kind": "train",
        "plan": study["definition"],
        "order": compile_plan(ResearchPlan.model_validate(study["definition"]))[
            "order"
        ],
        "observations": ObservationTable.model_validate(study["observations"]).sealed(),
        "profiles": execution_profiles(study["definition"]),
        "version_id": str(version["design_version_id"]),
        "request_sha256": identity_sha256({"legacy_acceptance": str(uuid4())}),
        "data_kind": "user_supplied",
    }
    runtime.store.enqueue(
        owner,
        UUID(saved["design_id"]),
        version["design_version_id"],
        "train",
        str(uuid4()),
        payload,
    )
    runner = ScientificRunner()
    completed, _ = calculate_next(client, runner)
    assert "input_sources" not in completed["result_json"]["pipeline"]
    model = client.post(
        BASE + "/models",
        headers=WRITE,
        json={"run_id": completed["run_id"], "name": "Legacy queued model"},
    ).json()
    response = client.post(
        BASE + "/predictions",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={
            "model_id": model["model_id"],
            "observations": study["prediction_observations"],
            "data_kind": "user_supplied",
        },
    )
    assert response.status_code == 200, response.text
    predicted, _ = calculate_next(client, runner)
    assert {
        s["channel"] for s in predicted["result_json"]["input_sources"]["inputs"]
    } == {"legacy_upload"}


def test_non_training_analysis_runs_without_a_trained_model(runtime_clients):
    """普通标准观测可分析并重开成果，分析结果不能登记成训练模型。"""
    client, other = runtime_clients
    study = client.get(BASE + "/examples/system").json()
    plan = study["definition"]
    plan["schema_version"] = "1.5"
    plan["purpose"] = "explore"
    plan["objective"] = "association"
    plan["evaluation"]["target_codes"] = []
    for variable in plan["variables"]:
        variable["role"] = "covariate"
    for requirement in plan["collection_requirements"]:
        requirement["required_for"] = ["explore"]
    node = plan["composition"]["nodes"][0]
    node["component"] = {"code": "research_descriptive_statistics", "revision": 1}
    plan["input_recipes"]["regression_config"]["value"] = {
        "variables": ["lai", "canopy_cover"]
    }
    plan["composition"]["inputs"][1]["data_type"]["semantic"] = (
        "research_statistics_request"
    )
    plan["composition"]["outputs"] = [
        {"code": "summary", "source": {"node": node["code"], "port": "summary"}}
    ]
    saved = client.post(
        BASE + "/plans",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={"definition": plan, "observations": study["observations"]},
    )
    assert saved.status_code == 200, saved.text
    body = {
        "design_id": saved.json()["design_id"],
        "expected_revision": saved.json()["revision"],
        "observations": study["observations"],
        "operation": "analyze",
    }
    response = client.post(
        BASE + "/runs", headers={**WRITE, "Idempotency-Key": str(uuid4())}, json=body
    )
    assert response.status_code == 200, response.text
    runner = ScientificRunner()
    finished, _ = calculate_next(client, runner)
    assert finished["kind"] == "analyze"
    assert finished["status"] == "succeeded"
    result = finished["result_json"]
    assert result["pipeline"] is None
    assert result["metrics"] == []
    summary = result["outputs"]["summary"]
    assert summary["row_count"] == 60
    assert {v["code"] for v in summary["variables"]} == {"lai", "canopy_cover"}
    assert (
        client.get(BASE + "/runs/" + finished["run_id"]).json()["result_sha256"]
        == finished["result_sha256"]
    )
    assert other.get(BASE + "/runs/" + finished["run_id"]).status_code == 404
    assert (
        client.post(
            BASE + "/models",
            headers=WRITE,
            json={"run_id": finished["run_id"], "name": "Not a trained model"},
        ).status_code
        == 409
    )


def test_declared_operation_mismatch_is_rejected_before_queue(runtime_clients):
    """分析组件不可冒充训练；未采用的模拟能力不得生成任务。"""
    client, _ = runtime_clients
    study = client.get(BASE + "/examples/analysis").json()
    saved = client.post(
        BASE + "/plans",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={"definition": study["definition"], "data_kind": "synthetic"},
    ).json()
    body = {
        "design_id": saved["design_id"],
        "expected_revision": saved["revision"],
        "observations": study["observations"],
        "data_kind": "synthetic",
    }
    for operation in [None, "train", "simulate", "calibrate"]:
        request = {**body, **({"operation": operation} if operation else {})}
        response = client.post(
            BASE + "/runs",
            headers={**WRITE, "Idempotency-Key": str(uuid4())},
            json=request,
        )
        assert response.status_code == 422, response.text
    assert client.get(BASE + "/runs").json()["items"] == []
