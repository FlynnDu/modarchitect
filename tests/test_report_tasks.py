# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 14:03
# @Author  : Codex
# @File    : test_report_tasks.py
"""通过正式任务接口验证日期闭区间、每日唯一批次和真实运行来源。"""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
import json
from pathlib import Path

import pytest

from modarchitect.report_tasks.contracts import DailyTick, observation_day, trigger_time
from test_research_runtime import BASE, WORKER, WRITE, ScientificRunner, calculate_next
from test_research_runtime import runtime_clients as runtime_clients
from test_design_api import live_design_api as live_design_api


def test_daily_clock_uses_shanghai_complete_previous_day_and_requires_logical_time():
    """跨年日界按上海计算，错时刻及缺时区不能冒充日任务。"""
    body = DailyTick(
        scheduled_at=datetime(2026, 12, 31, 18, tzinfo=timezone.utc), scheduler_id="42"
    )
    assert observation_day(body) == date(2026, 12, 31)
    assert trigger_time(date(2026, 12, 31)).isoformat() == "2027-01-01T02:00:00+08:00"
    with pytest.raises(ValueError):
        DailyTick(scheduled_at=datetime(2027, 1, 1, 2), scheduler_id="42")
    with pytest.raises(ValueError):
        observation_day(
            DailyTick(
                scheduled_at=datetime(2027, 1, 1, 2, tzinfo=timezone.utc),
                scheduler_id="42",
            )
        )


def test_sparse_scene_gap_waits_for_same_observation_day_and_has_bounded_recovery(monkeypatch):
    """采集成功但只有旧景也应等待，不得将当前日缺景直接终结或改用旧景。"""
    from types import SimpleNamespace
    from modarchitect.datasets import assemble_tables
    from modarchitect.report_tasks.service import ReportTasks
    from modarchitect.runtime.store import now
    from modarchitect.study_templates import template

    current = now()
    obj = {"field_ref": "A", "crop_code": "potato", "season_ref": "2025"}
    manual = {"columns": [{"code": "lai", "name": "叶面积指数", "unit": "m2_m2", "value_kind": "observed"}], "rows": [{"object": obj, "business_date": "2025-05-12", "values": {"lai": 2}}]}
    old_scene = {"columns": [{"code": "sentinel2_red_reflectance", "name": "red", "unit": "dimensionless", "value_kind": "estimated"}], "rows": [{"object": obj, "business_date": "2025-05-11", "values": {"sentinel2_red_reflectance": .2}}]}

    def prepare(owner, definition, ids, table, kind):
        """使用真实装配缺口检测，只替换存储/传输。"""
        return {"observations": assemble_tables([old_scene], base=table.model_dump(mode="json")), "data_kind": kind}

    sources = SimpleNamespace(read=lambda *args: {"status": "succeeded", "snapshot_ids": [str(uuid4())]})
    service = ReportTasks(SimpleNamespace(sources=sources, datasets=SimpleNamespace(prepare=prepare)), None)
    task = {"definition_json": template("soil-weather-satellite-lai")["definition"], "settings_json": {"business_selection": None, "model_id": None}, "observation_start": date(2025,5,1)}
    batch = {"observation_day": date(2025,5,12), "manual_json": manual, "run_id": None, "acquisition_ids": [str(uuid4())], "attempts_json": [{}], "created_at": current, "error": None}
    result, delay = service._advance(None, task, batch, "lease")
    assert result["status"] == "waiting_data" and delay >= 1800
    observed = []

    def recollect(owner, same_task, same_batch):
        """补取仍针对原观察日，不把旧景或者次日资料换进来。"""
        observed.append(same_batch["observation_day"])
        return ["replacement-acquisition"]

    monkeypatch.setattr(service, "_collect", recollect)
    batch["error"] = result["error"]
    retry, _ = service._advance(None, task, batch, "lease")
    assert retry["status"] == "collecting" and observed == [date(2025,5,12)]
    batch["created_at"] = current-timedelta(hours=73)
    terminal, _ = service._advance(None, task, batch, "lease")
    assert terminal["status"] == "failed" and "72-hour" in terminal["error"]


def manual_task(client, monkeypatch, days: int = 1):
    """通过用户可见接口建立一份日分析任务，返回准确待提交人工记录。"""
    monkeypatch.setattr(
        client.app.state.report_tasks, "daily_check", lambda *args: None
    )
    monkeypatch.setattr(
        client.app.state.report_tasks, "daily_instance_check", lambda *args: None
    )
    example = client.get(BASE + "/examples/analysis").json()
    saved = client.post(
        BASE + "/plans",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={"definition": example["definition"]},
    ).json()
    version = client.post(
        BASE + "/plans/" + saved["design_id"] + "/publish",
        headers=WRITE,
        json={"expected_revision": saved["revision"]},
    ).json()
    table = deepcopy(example["observations"])
    columns = example["definition"]["input_recipes"]["regression_config"]["value"][
        "variables"
    ]
    table["columns"] = [c for c in table["columns"] if c["code"] in columns]
    table["rows"] = [table["rows"][0]]
    for row in table["rows"]:
        row["values"] = {
            code: value for code, value in row["values"].items() if code in columns
        }
    day = date.fromisoformat(table["rows"][0]["business_date"])
    body = {
        "design_version_id": version["design_version_id"],
        "observation_start": day.isoformat(),
        "observation_end": (day + timedelta(days=days - 1)).isoformat(),
        "objects": [
            {
                "object": table["rows"][0]["object"],
                "reference_point": {"latitude": 39.0, "longitude": 116.0},
            }
        ],
    }
    response = client.post(
        BASE + "/report-tasks",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json=body,
    )
    assert response.status_code == 202, response.text
    return response.json(), body, table


def test_daily_report_records_each_observation_day_and_preserves_scoped_history(
    runtime_clients, monkeypatch
):
    """启用、日触发、重放、补资料、计算、暂停和重开均走正式HTTP入口。"""
    client, other = runtime_clients
    monkeypatch.setattr(
        client.app.state.report_tasks, "daily_check", lambda *args: None
    )
    monkeypatch.setattr(
        client.app.state.report_tasks, "daily_instance_check", lambda *args: None
    )
    example = client.get(BASE + "/examples/analysis").json()
    saved = client.post(
        BASE + "/plans",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={"definition": example["definition"]},
    ).json()
    published = client.post(
        BASE + "/plans/" + saved["design_id"] + "/publish",
        headers=WRITE,
        json={"expected_revision": saved["revision"]},
    )
    assert published.status_code == 200, published.text
    table = deepcopy(example["observations"])
    first = date.fromisoformat(table["rows"][0]["business_date"])
    last = first + timedelta(days=1)
    body = {
        "design_version_id": published.json()["design_version_id"],
        "observation_start": first.isoformat(),
        "observation_end": last.isoformat(),
        "objects": [
            {
                "object": table["rows"][0]["object"],
                "reference_point": {"latitude": 39.0, "longitude": 116.0},
            }
        ],
    }
    headers = {**WRITE, "Idempotency-Key": str(uuid4())}
    started = client.post(BASE + "/report-tasks", headers=headers, json=body)
    assert started.status_code == 202, started.text
    task = started.json()
    assert (
        client.post(BASE + "/report-tasks", headers=headers, json=body).json() == task
    )
    changed = {**body, "observation_end": (last + timedelta(days=1)).isoformat()}
    assert (
        client.post(BASE + "/report-tasks", headers=headers, json=changed).status_code
        == 409
    )
    identity = task["task_id"]
    assert other.get(BASE + "/report-tasks/" + identity).status_code == 404
    endpoint = "/internal/v1/report-tasks/tick"
    before = client.post(
        endpoint,
        headers=WORKER,
        json={
            "scheduled_at": trigger_time(first - timedelta(days=1)).isoformat(),
            "scheduler_id": "101",
        },
    )
    assert before.json() == {"created": 0}
    tick = {"scheduled_at": trigger_time(last).isoformat(), "scheduler_id": "102"}
    assert client.post(endpoint, headers=WORKER, json=tick).json() == {"created": 2}
    assert client.post(endpoint, headers=WORKER, json=tick).json() == {"created": 0}
    after = client.post(
        endpoint,
        headers=WORKER,
        json={
            "scheduled_at": trigger_time(last + timedelta(days=1)).isoformat(),
            "scheduler_id": "103",
        },
    )
    assert after.json() == {"created": 0}
    history = client.get(BASE + "/report-tasks/" + identity + "/batches").json()[
        "items"
    ]
    assert {row["observation_day"] for row in history} == {
        first.isoformat(),
        last.isoformat(),
    }
    earliest = next(
        row for row in history if row["observation_day"] == first.isoformat()
    )
    table["rows"] = [table["rows"][0]]
    variables = example["definition"]["input_recipes"]["regression_config"]["value"][
        "variables"
    ]
    table["columns"] = [c for c in table["columns"] if c["code"] in variables]
    for row in table["rows"]:
        row["values"] = {
            code: value for code, value in row["values"].items() if code in variables
        }
    provided = client.put(
        BASE + "/report-batches/" + earliest["batch_id"] + "/observations",
        headers=WRITE,
        json=table,
    )
    assert provided.status_code == 200, provided.text
    assert (
        other.put(
            BASE + "/report-batches/" + earliest["batch_id"] + "/observations",
            headers=WRITE,
            json=table,
        ).status_code
        == 404
    )
    for _ in range(2):
        advance = client.post("/internal/v1/report-tasks/advance", headers=WORKER)
        assert advance.status_code == 200, advance.text
    state = client.get(BASE + "/report-tasks/" + identity + "/batches").json()["items"]
    assert any(row["run_id"] for row in state), state
    completed, _ = calculate_next(client, ScientificRunner())
    assert completed["status"] == "succeeded"
    monkeypatch.setattr(
        "modarchitect.persistence.report_store.now",
        lambda: datetime.now(timezone.utc) + timedelta(seconds=20),
    )
    for _ in range(3):
        client.post("/internal/v1/report-tasks/advance", headers=WORKER)
    history = client.get(BASE + "/report-tasks/" + identity + "/batches").json()[
        "items"
    ]
    success = next(
        row for row in history if row["observation_day"] == first.isoformat()
    )
    assert (
        success["status"] == "succeeded"
        and success["run_id"] == completed["run_id"]
        and success["dataset_id"]
    )
    series = client.get(
        BASE
        + "/report-tasks/"
        + identity
        + "/series?start="
        + first.isoformat()
        + "&end="
        + last.isoformat()
    )
    assert series.status_code == 200, series.text
    assert len([row for row in series.json()["rows"] if row["output"] == "input"]) == 1
    assert series.json()["rows"][0]["business_date"] == first.isoformat()
    assert other.get(BASE + "/report-tasks/" + identity + "/series").status_code == 404
    assert (
        client.put(
            BASE + "/report-batches/" + success["batch_id"] + "/observations",
            headers=WRITE,
            json=table,
        ).status_code
        == 409
    )
    paused = client.post(
        BASE + "/report-tasks/" + identity + "/pause",
        headers=WRITE,
        json={"expected_revision": 1},
    )
    assert paused.status_code == 200 and paused.json()["status"] == "paused"
    assert (
        client.post(
            BASE + "/report-tasks/" + identity + "/resume",
            headers=WRITE,
            json={"expected_revision": 1},
        ).status_code
        == 409
    )
    resumed = client.post(
        BASE + "/report-tasks/" + identity + "/resume",
        headers=WRITE,
        json={"expected_revision": paused.json()["revision"]},
    )
    assert resumed.status_code == 200
    assert (
        len(client.get(BASE + "/report-tasks/" + identity + "/batches").json()["items"])
        == 2
    )


def test_business_report_writes_use_the_same_streaming_body_budget():
    """业务调用不能绕过工作区已经执行的上传大小限制。"""
    from fastapi.testclient import TestClient
    from modarchitect.api import create_app

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/research/report-tasks",
            content=b" " * 8_000_001 + b"{}",
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 413


def test_chain_prediction_requires_external_features_and_not_upstream_named_label():
    """同名目标来自上游预测端口时，不能再次要求调用方提供未知实测标签。"""
    from modarchitect.contracts.research.plans import ResearchPlan
    from modarchitect.execution_contracts import external_input_codes

    definition = json.loads(
        (
            Path(__file__).parents[1] / "modarchitect/web/designer/chain-study.json"
        ).read_text(encoding="utf-8")
    )["definition"]
    plan = ResearchPlan.model_validate(definition)
    assert external_input_codes(plan, "predict") == {
        "day",
        "ndvi",
        "soil_water",
        "temperature",
    }
    assert "height" in external_input_codes(plan, "train")


def test_daily_tick_drains_more_than_one_hundred_ongoing_tasks(
    runtime_clients, monkeypatch
):
    """超过一页的活跃研究都获得当天批次，重放不会重复且次日继续覆盖。"""
    client, _ = runtime_clients
    task, body, table = manual_task(client, monkeypatch, days=2)
    identities = {task["task_id"]}
    for _ in range(100):
        result = client.post(
            BASE + "/report-tasks",
            headers={**WRITE, "Idempotency-Key": str(uuid4())},
            json=body,
        )
        assert result.status_code == 202, result.text
        identities.add(result.json()["task_id"])
    day = date.fromisoformat(table["rows"][0]["business_date"])
    for offset in (0, 1):
        tick = {
            "scheduled_at": trigger_time(day + timedelta(days=offset)).isoformat(),
            "scheduler_id": "204",
        }
        created = 0
        for _ in range(10):
            result = client.post(
                "/internal/v1/report-tasks/tick", headers=WORKER, json=tick
            ).json()
            created += result["created"]
            if not result.get("has_more"):
                break
        assert created >= 101
        for identity in identities:
            batches = client.get(
                BASE + "/report-tasks/" + identity + "/batches"
            ).json()["items"]
            assert {b["observation_day"] for b in batches} == {
                (day + timedelta(days=n)).isoformat() for n in range(offset + 1)
            }
    for identity in identities:
        assert (
            client.post(
                BASE + "/report-tasks/" + identity + "/pause",
                headers=WRITE,
                json={"expected_revision": 1},
            ).status_code
            == 200
        )


def test_expired_preparation_cannot_enqueue_old_manual_values(
    runtime_clients, monkeypatch
):
    """旧领取者过期后恢复不能占用新资料的稳定运行键，完整输入和运行一次封存。"""
    client, _ = runtime_clients
    task, _, table = manual_task(client, monkeypatch)
    day = date.fromisoformat(table["rows"][0]["business_date"])
    client.post(
        "/internal/v1/report-tasks/tick",
        headers=WORKER,
        json={"scheduled_at": trigger_time(day).isoformat(), "scheduler_id": "201"},
    )
    batch = client.get(BASE + "/report-tasks/" + task["task_id"] + "/batches").json()[
        "items"
    ][0]
    endpoint = BASE + "/report-batches/" + batch["batch_id"] + "/observations"
    assert client.put(endpoint, headers=WRITE, json=table).status_code == 200
    original = client.app.state.research_runtime.datasets.prepare
    entered, release, lock = Event(), Event(), Lock()
    calls = []

    def delay_first(*args, **kwargs):
        """只延迟一次真实准备，不替换来源检查或数据库事务。"""
        with lock:
            calls.append(1)
            first = len(calls) == 1
        result = original(*args, **kwargs)
        if first:
            entered.set()
            assert release.wait(30), "Preparation race did not finish"
        return result

    monkeypatch.setattr(
        client.app.state.research_runtime.datasets, "prepare", delay_first
    )
    changed = deepcopy(table)
    code = changed["columns"][0]["code"]
    changed["rows"][0]["values"][code] += 0.1

    def advance_until_preparing():
        """共享调度队列可能先有其他待资料任务，仍由正常领取入口推进。"""
        for _ in range(20):
            response = client.post("/internal/v1/report-tasks/advance", headers=WORKER)
            if entered.is_set():
                return response
        raise AssertionError("The target batch was not claimed")

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(advance_until_preparing)
        try:
            assert entered.wait(20)
            assert client.put(endpoint, headers=WRITE, json=changed).status_code == 409
            clock = datetime.now(timezone.utc) + timedelta(minutes=4)
            monkeypatch.setattr(
                "modarchitect.persistence.report_store.now", lambda: clock
            )
            assert client.put(endpoint, headers=WRITE, json=changed).status_code == 200
            for _ in range(5):
                second = client.post(
                    "/internal/v1/report-tasks/advance", headers=WORKER
                )
                assert second.status_code == 200, second.text
                current = client.get(
                    BASE + "/report-tasks/" + task["task_id"] + "/batches"
                ).json()["items"][0]
                if current["run_id"]:
                    break
        finally:
            release.set()
        assert first.result(timeout=5).status_code == 409
    history = client.get(BASE + "/report-tasks/" + task["task_id"] + "/batches").json()[
        "items"
    ][0]
    assert history["run_id"] and history["dataset_id"]
    assert len(client.get(BASE + "/runs").json()["items"]) == 1
    actual = client.get(BASE + "/datasets/" + history["dataset_id"]).json()[
        "observations"
    ]
    assert actual["rows"][0]["values"][code] == changed["rows"][0]["values"][code]
    assert client.put(endpoint, headers=WRITE, json=changed).status_code == 409
    completed, _ = calculate_next(client, ScientificRunner())
    assert (
        completed["run_id"] == history["run_id"] and completed["status"] == "succeeded"
    )


def test_old_observations_cannot_masquerade_as_current_batch(
    runtime_clients, monkeypatch
):
    """同对象旧年度数据以及未覆盖当日的表必须在补资料接口拒绝。"""
    client, _ = runtime_clients
    task, _, table = manual_task(client, monkeypatch)
    day = date.fromisoformat(table["rows"][0]["business_date"])
    client.post(
        "/internal/v1/report-tasks/tick",
        headers=WORKER,
        json={"scheduled_at": trigger_time(day).isoformat(), "scheduler_id": "202"},
    )
    batch = client.get(BASE + "/report-tasks/" + task["task_id"] + "/batches").json()[
        "items"
    ][0]
    table["rows"][0]["business_date"] = (day - timedelta(days=365)).isoformat()
    response = client.put(
        BASE + "/report-batches/" + batch["batch_id"] + "/observations",
        headers=WRITE,
        json=table,
    )
    assert response.status_code == 422


def test_business_activation_uses_verified_fields_and_refuses_cross_owner_versions(
    live_design_api, monkeypatch, tmp_path
):
    """业务提交只声明选地引用，真实范围与坐标从已核验选地响应获得。"""
    from modarchitect.study_templates import template
    from test_design_api import AUTH, ROOT, SELECTION, create_draft, new_draft
    from test_research_runtime import profiles_file

    client, state = live_design_api
    monkeypatch.setenv(
        "MODARCHITECT_RUNTIME_PROFILES",
        str(profiles_file(tmp_path / "daily-profiles.json")),
    )
    service = client.app.state.report_tasks
    monkeypatch.setattr(service, "daily_check", lambda *args: None)
    created = create_draft(
        client, new_draft(client, template("crop-high-temperature")["definition"])
    )
    assert created.status_code == 201, created.text
    design_id = created.json()["design_id"]
    published = client.post(
        ROOT + "/design-drafts/" + design_id + "/publish",
        headers=AUTH,
        json={"expected_revision": 1},
    )
    assert published.status_code == 200, published.text
    body = {
        "design_version_id": published.json()["design_version_id"],
        "observation_start": "2025-04-01",
        "observation_end": "2025-04-02",
        "fields": {"selection": SELECTION, "field_refs": ["field-a"]},
    }
    endpoint = ROOT + "/report-tasks"
    headers = {**AUTH, "Idempotency-Key": str(uuid4())}
    started = client.post(endpoint, headers=headers, json=body)
    assert started.status_code == 202, started.text
    identity = started.json()["task_id"]
    detail = client.get(endpoint + "/" + identity, headers=AUTH).json()
    assert detail["objects"][0]["object"]["field_ref"] == "field-a"
    assert 39 <= detail["objects"][0]["reference_point"]["latitude"] <= 40
    assert (
        client.post(
            endpoint,
            headers={
                "X-MLGrowth-Business-Key": AUTH["X-MLGrowth-Business-Key"],
                "Idempotency-Key": str(uuid4()),
            },
            json=body,
        ).status_code
        == 401
    )
    assert (
        client.post(
            endpoint,
            headers={**headers, "X-Enterprise-Delegation": "other-company"},
            json=body,
        ).status_code
        == 404
    )
    changed = deepcopy(body)
    changed["fields"]["field_refs"] = ["not-authorized"]
    assert (
        client.post(
            endpoint, headers={**AUTH, "Idempotency-Key": str(uuid4())}, json=changed
        ).status_code
        == 404
    )
    state["bad_query_digest"] = True
    assert (
        client.post(
            endpoint, headers={**AUTH, "Idempotency-Key": str(uuid4())}, json=body
        ).status_code
        == 503
    )
