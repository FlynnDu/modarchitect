# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 22:03
# @Author  : Codex
# @File    : test_input_acquisition.py
"""验证准确来源替换、真实协议转换与快照进入研究的受权行为。"""

from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
from uuid import uuid4

import httpx
import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from modarchitect import system_inputs
from modarchitect.contracts.identifiers import identity_sha256
from modarchitect.contracts.model_center.components import DesignPublication
from modarchitect.runtime.workspace import COOKIE, principal
from modarchitect.input_sources.service import execute_acquisition, prepare_acquisition
from modarchitect.input_sources.contracts import AcquisitionRequest
from modarchitect.input_sources.soil import IGH, normalize_soil, read_pixel
from modarchitect.input_sources.weather import convert_weather
from modarchitect.system_inputs import (
    configure_input,
    resolve_input,
    validate_input_bindings,
    validate_input_adoption,
)

from test_research_runtime import BASE, WORKER, WRITE, ScientificRunner, calculate_next
from test_research_runtime import runtime_clients as runtime_clients

ROOT = Path(__file__).parents[1]
SOURCE_INTERNAL = "/internal/v1/input-acquisitions"


def weather_response(start: date, end: date) -> dict:
    """独立构造可验证单位/时间的工程响应，不冒充真实提供方联验。"""
    days = [
        (start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)
    ]
    return {
        "latitude": 39.0,
        "longitude": 116.0,
        "elevation": 30.0,
        "timezone": "Asia/Shanghai",
        "utc_offset_seconds": 28800,
        "daily_units": {
            "temperature_2m_min": "°C",
            "temperature_2m_max": "°C",
            "precipitation_sum": "mm",
            "shortwave_radiation_sum": "MJ/m²",
        },
        "daily": {
            "time": days,
            "temperature_2m_min": [5.0 for _ in days],
            "temperature_2m_max": [30.0 for _ in days],
            "precipitation_sum": [1.0 for _ in days],
            "shortwave_radiation_sum": [15.0 for _ in days],
        },
        "hourly_units": {
            "temperature_2m": "°C",
            "wind_speed_10m": "m/s",
            "dew_point_2m": "°C",
        },
        "hourly": {
            "time": [d + "T%02d:00" % h for d in days for h in range(24)],
            "temperature_2m": [
                10 + i / 10 for i in range(len(days)) for _ in range(24)
            ],
            "wind_speed_10m": [2.0 for _ in days for _ in range(24)],
            "dew_point_2m": [5.0 for _ in days for _ in range(24)],
        },
    }


def source_plan() -> dict:
    """在已支持的真实目录方案中选择一项人工标签和一项固定天气因素。"""
    plan = json.loads(
        (ROOT / "modarchitect/web/designer/system-study.json").read_bytes()
    )["definition"]
    configured = [
        configure_input("sampling_indicator:lai@1.0.0", {}, "target"),
        configure_input("variable_source:temperature_mean_daily@1.0.0", {}),
    ]
    plan["variables"] = [c["variable"] for c in configured]
    plan["collection_requirements"] = [c["requirement"] for c in configured]
    plan["input_recipes"]["observations"]["variable_codes"] = [
        "lai",
        "temperature_mean_daily",
    ]
    plan["input_recipes"]["regression_config"]["value"] = {
        "features": ["temperature_mean_daily"],
        "targets": ["lai"],
        "training_end": "2025-04-20",
    }
    plan["evaluation"]["target_codes"] = ["lai"]
    return plan


def source_request() -> dict:
    """明确自有参考位置与业务日范围，不声明企业选地授权。"""
    return {
        "expected_revision": 1,
        "object": {
            "field_ref": "source-test",
            "crop_code": "potato",
            "season_ref": "2025",
        },
        "reference_point": {"latitude": 39.0, "longitude": 116.0},
        "start_date": "2025-04-01",
        "end_date": "2025-04-30",
    }


def test_history_binding_remains_exact_after_current_adoption_changes(monkeypatch):
    """换当前来源后旧方案仍准确解释，新的采用不能偷改旧绑定。"""
    original = system_inputs._snapshot()
    configured = configure_input("variable_source:temperature_mean_daily@1.0.0", {})
    changed = deepcopy(original)
    policy = next(
        p
        for p in changed["payload"]["policies"]
        if p["code"] == "temperature_mean_daily"
    )
    source = next(
        s
        for s in changed["payload"]["sources"]
        if s["code"] == policy["source"]["code"]
    )
    source["code"] = "replacement_temperature_daily"
    source["definition_version"] = "2.0.0"
    source["component"]["code"] = "replacement_weather"
    policy["source"] = {
        "code": source["code"],
        "definition_version": source["definition_version"],
    }
    changed["sha256"] = identity_sha256(changed["payload"])
    monkeypatch.setattr(system_inputs, "_snapshot", lambda: changed)
    monkeypatch.setattr(system_inputs, "_history", lambda: (original, changed))
    latest = configure_input("variable_source:temperature_mean_daily@1.0.0", {})
    assert (
        latest["requirement"]["catalog_binding"]
        != configured["requirement"]["catalog_binding"]
    )
    validate_input_bindings(
        {
            "variables": [configured["variable"]],
            "collection_requirements": [configured["requirement"]],
        },
        require_catalog=True,
    )
    assert (
        resolve_input(configured["requirement"]["catalog_binding"])["source"]["code"]
        == "openmeteo_weather"
    )
    old = {
        "variables": [configured["variable"]],
        "collection_requirements": [configured["requirement"]],
    }
    with pytest.raises(ValueError, match="new adoption"):
        validate_input_adoption(old)
    validate_input_adoption(old, old)
    with pytest.raises(ValueError, match="new adoption"):
        prepare_acquisition(old, AcquisitionRequest.model_validate(source_request()))
    prepare_acquisition(
        old,
        AcquisitionRequest.model_validate(source_request()),
        retained_definition=old,
    )


def test_policy_metadata_revision_does_not_change_historical_scientific_identity(
    monkeypatch,
):
    """采用策略仅换展示版本，不得使准确历史来源和原方法无法解释。"""
    old = system_inputs._snapshot()
    binding = configure_input("variable_source:temperature_mean_daily@1.0.0", {})
    changed = deepcopy(old)
    policy = next(
        p
        for p in changed["payload"]["policies"]
        if p["code"] == "temperature_mean_daily"
    )
    policy["definition_version"] = "2.0.0"
    changed["sha256"] = identity_sha256(changed["payload"])
    monkeypatch.setattr(system_inputs, "_history", lambda: (old, changed))
    validate_input_bindings(
        {
            "variables": [binding["variable"]],
            "collection_requirements": [binding["requirement"]],
        },
        require_catalog=True,
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "timezone",
        "unit",
        "missing_hour",
        "duplicate_hour",
        "missing_value",
        "negative_wind",
        "hourly_temperature",
        "hourly_dewpoint",
    ],
)
def test_weather_rejects_wrong_units_missing_or_incompatible_source_data(mutation):
    """单位、日界、时间完整性和物理无效值不能通过平均掩盖。"""
    start = end = date(2025, 4, 1)
    raw = weather_response(start, end)
    if mutation == "timezone":
        raw["timezone"] = "UTC"
    elif mutation == "unit":
        raw["daily_units"]["shortwave_radiation_sum"] = "J/m²"
    elif mutation == "missing_hour":
        raw["hourly"]["time"].pop()
    elif mutation == "duplicate_hour":
        raw["hourly"]["time"][1] = raw["hourly"]["time"][0]
    elif mutation == "missing_value":
        raw["hourly"]["dew_point_2m"][0] = None
    elif mutation == "negative_wind":
        raw["hourly"]["wind_speed_10m"][0] = -1
    else:
        name = "temperature_2m" if mutation == "hourly_temperature" else "dew_point_2m"
        raw["hourly"][name][0:2] = [1000, -980]
    with pytest.raises(ValueError):
        convert_weather(raw, start, end)


def test_weather_conversion_preserves_declared_scientific_units():
    """独立预期核对辐射、雨量及均温，水汽压保留日均露点转换含义。"""
    rows = convert_weather(
        weather_response(date(2025, 4, 1), date(2025, 4, 1)),
        date(2025, 4, 1),
        date(2025, 4, 1),
    )
    values = rows[0]["values"]
    assert values["temperature_mean_daily"] == 10
    assert values["solar_radiation_daily"] == 15000
    assert values["precipitation_daily"] == 1
    assert values["wind_speed_2m_daily"] == pytest.approx(1.5)
    assert values["vapour_pressure_daily"] == pytest.approx(0.872)


@pytest.mark.parametrize(
    "name,raw,expected",
    [
        ("bdod", 149, 1.49),
        ("cec", 123, 12.3),
        ("cfvo", 10, 1),
        ("clay", 250, 25),
        ("phh2o", 65, 6.5),
        ("sand", 500, 50),
        ("silt", 250, 25),
        ("soc", 170, 17),
        ("wv0010", 350, 0.35),
        ("wv0033", 250, 0.25),
        ("wv1500", 100, 0.1),
    ],
)
def test_eleven_soil_properties_use_exact_normalization(name, raw, expected):
    """全部11项独立数值预期，水量不得误作百分数或复用旧CSV因子。"""
    assert normalize_soil(name, raw) == expected


def test_real_wcs_native_crs_is_accepted_without_inventing_a_bound_datum_shift():
    """真实公开 GeoTIFF 固定正例捕捉 WGS84 BoundCRS 与原生 CRS 的误拒绝。"""
    body = (ROOT / "tests/fixtures/soilgrids_bdod_native.tif").read_bytes()
    assert read_pixel(body, 10132250, 5585000) == 107


@pytest.mark.parametrize(
    "bad", ["zero", "nodata", "resampled", "many_pixels", "wrong_crs"]
)
def test_wcs_rejects_ambiguous_coverage_or_changed_native_support(bad):
    """实际 GeoTIFF 正反例验证，HTTP成功不能替代原生空间与覆盖门禁。"""
    width = 2 if bad == "many_pixels" else 1
    transform = from_origin(-1000000, 2000000, 248 if bad == "resampled" else 250, 250)
    with MemoryFile() as memory:
        with memory.open(
            driver="GTiff",
            height=1,
            width=width,
            count=1,
            dtype="int16",
            crs="EPSG:4326" if bad == "wrong_crs" else IGH.to_wkt(),
            transform=transform,
            nodata=-32768,
        ) as dataset:
            value = 0 if bad == "zero" else -32768 if bad == "nodata" else 149
            dataset.write(np.full((1, width), value, dtype=np.int16), 1)
        raw = memory.read()
    with pytest.raises(ValueError):
        read_pixel(raw, -1000000, 2000000)


def collect_test_snapshot(
    client, design_id: str, monkeypatch, request: dict | None = None
) -> tuple[str, dict]:
    """从正式采集请求、领取和回传入口完成；仅网络替身，非外部联验。"""
    request = request or source_request()
    key = str(uuid4())
    created = client.post(
        BASE + "/plans/" + design_id + "/input-acquisitions",
        headers={**WRITE, "Idempotency-Key": key},
        json=request,
    )
    assert created.status_code == 202, created.text
    identity = created.json()["acquisition_id"]
    assert (
        client.post(
            BASE + "/plans/" + design_id + "/input-acquisitions",
            headers={**WRITE, "Idempotency-Key": key},
            json=request,
        ).json()
        == created.json()
    )
    dispatched = client.post(SOURCE_INTERNAL + "/dispatch/next", headers=WORKER).json()[
        "job"
    ]
    assert dispatched["acquisition_id"] == identity
    claimed = client.post(SOURCE_INTERNAL + "/claim", headers=WORKER, json=dispatched)
    assert claimed.status_code == 200, claimed.text
    claim = claimed.json()
    monkeypatch.setenv("MODARCHITECT_WEATHER_ACCESS", "research")

    def provider(req):
        """只响应固定公开历史端点，其他URL一律失败。"""
        assert req.url.host == "archive-api.open-meteo.com"
        start, end = (
            date.fromisoformat(req.url.params["start_date"]),
            date.fromisoformat(req.url.params["end_date"]),
        )
        return httpx.Response(200, json=weather_response(start, end))

    result = execute_acquisition(
        claim["input"], lambda: None, transport=httpx.MockTransport(provider)
    )
    completion = {"attempt_id": claim["attempt_id"], "result": {"snapshots": result}}
    response = client.post(
        SOURCE_INTERNAL + "/" + identity + "/complete", headers=WORKER, json=completion
    )
    assert response.status_code == 200, response.text
    assert (
        client.post(
            SOURCE_INTERNAL + "/" + identity + "/complete",
            headers=WORKER,
            json=completion,
        ).json()
        == response.json()
    )
    snapshot_id = response.json()["snapshot_ids"][0]
    table = client.get(BASE + "/input-snapshots/" + snapshot_id).json()["observations"]
    return snapshot_id, table


def test_acquired_source_trains_saves_reopens_and_predicts_with_immutable_origin(
    runtime_clients, monkeypatch
):
    """真实数据库及科学算法验证来源贯穿模型；提供方与容器传输使用替身。"""
    client, other = runtime_clients
    plan = source_plan()
    saved = client.post(
        BASE + "/plans",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={"definition": plan},
    ).json()
    snapshot_id, table = collect_test_snapshot(client, saved["design_id"], monkeypatch)
    assert other.get(BASE + "/input-snapshots/" + snapshot_id).status_code == 404
    label = configure_input("sampling_indicator:lai@1.0.0", {}, "target")["variable"]
    table["columns"].append(
        {
            "code": "lai",
            "name": label["name"],
            "unit": label["unit"],
            "value_kind": "observed",
        }
    )
    for row in table["rows"]:
        row["values"]["lai"] = 1 + 0.1 * row["values"]["temperature_mean_daily"]
    request = {
        "definition": plan,
        "observations": table,
        "source_snapshot_ids": [snapshot_id],
        "expected_revision": 1,
    }
    checked = client.post(
        BASE + "/check-execution",
        headers=WRITE,
        json={
            **{k: v for k, v in request.items() if k != "expected_revision"},
            "operation": "train",
        },
    )
    assert checked.json()["can_execute"] is True, checked.text
    saved = client.put(
        BASE + "/plans/" + saved["design_id"], headers=WRITE, json=request
    )
    assert saved.status_code == 200, saved.text
    saved = saved.json()
    reopened = client.get(BASE + "/plans/" + saved["design_id"]).json()
    assert reopened["source_snapshot_ids"] == [snapshot_id]
    started = client.post(
        BASE + "/runs",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={
            "design_id": saved["design_id"],
            "expected_revision": saved["revision"],
            "observations": table,
            "source_snapshot_ids": [snapshot_id],
        },
    )
    assert started.status_code == 200, started.text
    runner = ScientificRunner()
    run, _ = calculate_next(client, runner)
    assert run["status"] == "succeeded"
    model = client.post(
        BASE + "/models",
        headers=WRITE,
        json={"run_id": run["run_id"], "name": "来源快照研究"},
    ).json()
    source_manifest = model["model_json"]["input_sources"]
    assert (
        next(
            i
            for i in source_manifest["inputs"]
            if i["variable"]["code"] == "temperature_mean_daily"
        )["channel"]
        == "source_snapshot"
    )
    later = {
        **source_request(),
        "expected_revision": saved["revision"],
        "start_date": "2025-05-01",
        "end_date": "2025-05-05",
    }
    prediction_snapshot, prediction = collect_test_snapshot(
        client, saved["design_id"], monkeypatch, later
    )
    response = client.post(
        BASE + "/predictions",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={
            "model_id": model["model_id"],
            "observations": prediction,
            "source_snapshot_ids": [prediction_snapshot],
        },
    )
    assert response.status_code == 200, response.text
    predicted, _ = calculate_next(client, runner)
    assert predicted["status"] == "succeeded"
    assert runner.calls == [
        "multivariate_linear_training",
        "multivariate_linear_predict",
    ]
    assert (
        client.get(BASE + "/models/" + model["model_id"]).json()["model_sha256"]
        == model["model_sha256"]
    )
    for bad in ("value", "object", "missing_reference"):
        forged = deepcopy(prediction)
        if bad == "value":
            forged["rows"][0]["values"]["temperature_mean_daily"] += 1
        if bad == "object":
            forged["rows"][0]["object"]["field_ref"] = "different-field"
        body = {
            "model_id": model["model_id"],
            "observations": forged,
            "source_snapshot_ids": []
            if bad == "missing_reference"
            else [prediction_snapshot],
        }
        assert (
            client.post(
                BASE + "/predictions",
                headers={**WRITE, "Idempotency-Key": str(uuid4())},
                json=body,
            ).status_code
            == 422
        )


def test_cancelled_acquisition_rejects_late_results_and_cross_workspace_reads(
    runtime_clients,
):
    """取消撤销回传权，重复投递不能恢复执行，也不能读取他人任务。"""
    client, other = runtime_clients
    saved = client.post(
        BASE + "/plans",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={"definition": source_plan()},
    ).json()
    identity = client.post(
        BASE + "/plans/" + saved["design_id"] + "/input-acquisitions",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json=source_request(),
    ).json()["acquisition_id"]
    job = client.post(SOURCE_INTERNAL + "/dispatch/next", headers=WORKER).json()["job"]
    claim = client.post(SOURCE_INTERNAL + "/claim", headers=WORKER, json=job).json()
    assert other.get(BASE + "/input-acquisitions/" + identity).status_code == 404
    assert (
        client.post(
            BASE + "/input-acquisitions/" + identity + "/cancel", headers=WRITE
        ).json()["status"]
        == "cancelled"
    )
    late = client.post(
        SOURCE_INTERNAL + "/" + identity + "/complete",
        headers=WORKER,
        json={"attempt_id": claim["attempt_id"], "error": "Late failure"},
    )
    assert late.status_code == 409
    assert client.post(SOURCE_INTERNAL + "/claim", headers=WORKER, json=job).json() == {
        "finished": True,
        "status": "cancelled",
    }


def test_source_replacement_blocks_new_adoption_but_keeps_creation_replay(
    runtime_clients, monkeypatch
):
    """真实 HTTP 区分新采用、原请求重放及既有草稿保留，不让换源破坏幂等。"""
    client, _ = runtime_clients
    plan = source_plan()
    key = str(uuid4())
    headers = {**WRITE, "Idempotency-Key": key}
    original = client.post(BASE + "/plans", headers=headers, json={"definition": plan})
    assert original.status_code == 200, original.text
    owner = principal(client.cookies[COOKIE])
    designs = client.app.state.research_runtime.designs
    publication = DesignPublication(
        name=plan["name"],
        composition=plan["composition"],
        research_plan=plan,
        revision=1,
    )
    direct, _ = designs.publish_direct(owner, publication, key=key + "-direct")
    old = system_inputs._snapshot()
    changed = deepcopy(old)
    policy = next(
        p
        for p in changed["payload"]["policies"]
        if p["code"] == "temperature_mean_daily"
    )
    source = next(
        s
        for s in changed["payload"]["sources"]
        if s["code"] == policy["source"]["code"]
    )
    source["code"] = "replacement_temperature_daily"
    source["component"]["code"] = "replacement_weather"
    policy["source"]["code"] = source["code"]
    changed["sha256"] = identity_sha256(changed["payload"])
    monkeypatch.setattr(system_inputs, "_snapshot", lambda: changed)
    monkeypatch.setattr(system_inputs, "_history", lambda: (old, changed))
    blocked = client.post(
        BASE + "/plans",
        headers={**WRITE, "Idempotency-Key": str(uuid4())},
        json={"definition": plan},
    )
    assert blocked.status_code == 422 and "new adoption" in blocked.text
    replay = client.post(BASE + "/plans", headers=headers, json={"definition": plan})
    assert replay.status_code == 200, replay.text
    assert replay.json()["design_id"] == original.json()["design_id"]
    updated = client.put(
        BASE + "/plans/" + original.json()["design_id"],
        headers=WRITE,
        json={"definition": plan, "expected_revision": 1},
    )
    assert updated.status_code == 200, updated.text
    repeated, created = designs.publish_direct(owner, publication, key=key + "-direct")
    assert not created and repeated["design_version_id"] == direct["design_version_id"]
    with pytest.raises(ValueError, match="new adoption"):
        designs.publish_direct(owner, publication, key=str(uuid4()))
