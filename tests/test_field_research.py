# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 14:17
# @Author  : Codex
# @File    : test_field_research.py
"""使用明确阈值和独立样本验证标准日值条件及科学覆盖。"""

from copy import deepcopy
from datetime import date, timedelta

import pytest

from components.field_research.weather import conditions
from modarchitect.study_templates import template, template_view


def heat_table() -> dict:
    """七日实际样本有一天36度，第二地块不应被混入第一个地块。"""
    obj = {"field_ref": "field-a", "crop_code": "potato", "season_ref": "2025"}
    return {
        "columns": [
            {
                "code": "temperature_maximum_daily",
                "name": "日最高气温",
                "unit": "celsius",
                "value_kind": "estimated",
            }
        ],
        "rows": [
            {
                "object": obj,
                "business_date": (date(2025, 6, 1) + timedelta(days=i)).isoformat(),
                "values": {"temperature_maximum_daily": value},
            }
            for i, value in enumerate([28, 29, 31, 36, 30, 29, 27])
        ],
        "source_sha256": ["a" * 64],
    }


def test_weather_conditions_keep_partial_positive_and_never_invent_negative_window():
    """完整高温窗口触发；已知低于阈值但缺日只能给资料不足。"""
    table = heat_table()
    params = {
        "rule": "heat_exposure",
        "as_of": "2025-06-07",
        "window_days": 7,
        "variables": ["temperature_maximum_daily"],
    }
    result = conditions({"observations": table}, params)
    assert result["report"]["results"][0]["result"] == "triggered"
    assert result["report"]["results"][0]["metric"] == 36
    assert len(result["series"]["rows"]) == 7
    table["rows"] = table["rows"][:3]
    result = conditions({"observations": table}, params)
    assert result["report"]["results"][0]["result"] == "not_evaluated"
    assert result["report"]["results"][0]["window"]["missing_dates"] == [
        "2025-06-04",
        "2025-06-05",
        "2025-06-06",
        "2025-06-07",
    ]
    table["rows"][0]["values"]["temperature_maximum_daily"] = 36
    assert (
        conditions({"observations": table}, params)["report"]["results"][0]["result"]
        == "triggered"
    )
    broken = deepcopy(table)
    broken["columns"][0]["unit"] = "kpa"
    with pytest.raises(ValueError):
        conditions({"observations": broken}, params)


def test_current_weather_and_soil_templates_use_catalog_inputs_and_keep_old_exact_examples():
    """当前五个方案有准确指标来源，旧示例继续按归档摘要读取。"""
    from importlib.resources import files
    import json

    old_rows = json.loads(
        files("modarchitect.contracts")
        .joinpath("study-templates-archive-v3.json")
        .read_text(encoding="utf-8")
    )
    assert len(old_rows) == 5
    for old in old_rows:
        current = template(old["id"])
        assert current["revision"] == 2
        assert current["definition"]["collection_requirements"]
        assert all(
            r["catalog_binding"] and r["required_for"] == ["explore"]
            for r in current["definition"]["collection_requirements"]
        )
        assert not any(
            r["kind"] == "artifact"
            for r in current["definition"]["input_recipes"].values()
        )
        assert template_view(current)["input_policy"]["mode"] == "user_observations"
        assert (
            template(old["id"], old["sha256"])["bundle_sha256"] == old["bundle_sha256"]
        )


def test_weather_series_can_feed_another_analysis_without_losing_external_lineage():
    """气象窗口的正式表输出可串联统计，实际启动仍准确要求原始日最高温。"""
    from modarchitect.contracts.research.plans import ResearchPlan
    from modarchitect.execution_contracts import external_input_codes
    from modarchitect.validation import compile_plan

    plan = deepcopy(template("crop-high-temperature")["definition"])
    source = plan["composition"]["nodes"][0]["code"]
    statistics = template("soil-properties")["definition"]
    parameter = next(
        port
        for port in statistics["composition"]["inputs"]
        if port["role"] == "parameter"
    )
    plan["composition"]["inputs"].append({**parameter, "code": "statistics_config"})
    plan["input_recipes"]["statistics_config"] = {
        "kind": "configuration",
        "value": {"variables": ["temperature_maximum_daily"]},
    }
    plan["composition"]["nodes"].append(
        {
            "code": "statistics",
            "component": {"code": "research_descriptive_statistics", "revision": 1},
            "bindings": [
                {"port": "observations", "source": {"node": source, "port": "series"}},
                {
                    "port": "request",
                    "source": {"node": None, "port": "statistics_config"},
                },
            ],
        }
    )
    plan["composition"]["outputs"].append(
        {"code": "statistics", "source": {"node": "statistics", "port": "summary"}}
    )
    parsed = ResearchPlan.model_validate(plan)
    order = compile_plan(parsed, adopted=True)["order"]
    assert order.index(source) < order.index("statistics")
    assert external_input_codes(parsed, "analyze") == {"temperature_maximum_daily"}
