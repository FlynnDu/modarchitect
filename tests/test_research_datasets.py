# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 13:38
# @Author  : Codex
# @File    : test_research_datasets.py
"""从来源封存入口验证多地块覆盖，不以拼表绕过真实来源。"""

from copy import deepcopy
from datetime import date
from uuid import uuid4

import httpx
import pytest

from modarchitect.contracts.identifiers import identity_sha256
from modarchitect.input_sources.contracts import AcquisitionRequest
from modarchitect.input_sources.service import execute_acquisition, prepare_acquisition
from modarchitect.system_inputs import seal_input_sources

from test_input_acquisition import source_plan, source_request, weather_response


def collected_part(plan: dict, field: str, monkeypatch) -> tuple[dict, dict]:
    """用真实转换实现和固定网络响应产生一个可校验的地块来源快照。"""
    monkeypatch.setenv("MODARCHITECT_WEATHER_ACCESS", "research")
    request = source_request()
    request["object"]["field_ref"] = field
    body = AcquisitionRequest.model_validate(request)

    def response(_request):
        """固定独立提供方样本，不重写天气转换或来源配对算法。"""
        return httpx.Response(
            200, json=weather_response(date(2025, 4, 1), date(2025, 4, 30))
        )

    payload = prepare_acquisition(plan, body)
    snapshots = execute_acquisition(
        payload, lambda: None, transport=httpx.MockTransport(response)
    )
    snapshot = snapshots[0]
    return snapshot["observations"], {
        "snapshot_id": str(uuid4()),
        "sha256": identity_sha256(snapshot),
        "snapshot": snapshot,
    }


def test_multifield_sources_cover_exact_objects_and_reject_duplicate_or_missing_coverage(
    monkeypatch,
):
    """两个地块可以共同封存，同对象重复来源、缺口和改值均明确拒绝。"""
    plan = source_plan()
    first, source_a = collected_part(plan, "field-a", monkeypatch)
    second, source_b = collected_part(plan, "field-b", monkeypatch)
    table = {"columns": first["columns"], "rows": first["rows"] + second["rows"]}
    sources = [source_a, source_b]
    sealed = seal_input_sources(
        plan, table, "user_supplied", "owner", source_snapshots=sources
    )
    assert sealed["row_count"] == 60
    references = sealed["inputs"][0]["source_snapshots"]
    assert {r["snapshot_id"] for r in references} == {
        source_a["snapshot_id"],
        source_b["snapshot_id"],
    }
    with pytest.raises(ValueError):
        seal_input_sources(
            plan, table, "user_supplied", "owner", source_snapshots=[source_a]
        )
    with pytest.raises(ValueError):
        seal_input_sources(
            plan,
            table,
            "user_supplied",
            "owner",
            source_snapshots=sources + [deepcopy(source_a)],
        )
    changed = deepcopy(table)
    changed["rows"][-1]["values"]["temperature_mean_daily"] += 1
    with pytest.raises(ValueError):
        seal_input_sources(
            plan, changed, "user_supplied", "owner", source_snapshots=sources
        )
