# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 17:28
# @Author  : Codex
# @File    : test_agronomic_research.py
"""验证研究主题独立计算、可编辑参数与数据来源边界。"""

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from modarchitect.contracts.research.plans import ResearchPlan
from modarchitect.study_templates import matches_template, template, templates
from modarchitect.validation import compile_plan

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "components/agronomic_research/src"))
from modarchitect_agronomy.series import process  # noqa: E402


def series_data():
    """用明确模拟性质的三日数据验证实际统计，而非镜像实现断言。"""
    return {
        "schema_version": "1.0",
        "context": {"support": "同一模型情景"},
        "source_description": "模型输出",
        "variables": [
            {
                "code": "water",
                "name": "水分限制系数",
                "unit": "1",
                "value_kind": "simulated",
                "minimum": 0,
                "maximum": 1,
            },
            {
                "code": "growth",
                "name": "生物量",
                "unit": "kg/ha",
                "value_kind": "simulated",
            },
        ],
        "rows": [
            {
                "date": "2026-10-%02d" % (index + 1),
                "values": {"water": value, "growth": value * 20},
            }
            for index, value in enumerate([0.2, 0.5, 0.8])
        ],
    }


def test_process_is_independent_math_and_preserves_nature_missingness_and_pairing():
    """选择窗口改变真实结果，缺测不补零，少于三对不输出相关系数。"""
    data = series_data()
    params = {
        "variables": ["water", "growth"],
        "start_date": "2026-10-01",
        "end_date": "2026-10-03",
    }
    result = process({"series": data}, params)["report"]
    assert result["indicators"][0]["mean"] == 0.5
    assert result["indicators"][0]["value_kind"] == "simulated"
    assert result["relationships"][0]["correlation"] == pytest.approx(1)
    data["rows"][1]["values"]["growth"] = None
    result = process({"series": data}, params)["report"]
    assert (
        result["indicators"][1]["count"] == 2
        and result["indicators"][1]["missing_count"] == 1
    )
    assert result["relationships"][0]["correlation"] is None
    params["start_date"] = "2026-10-03"
    assert process({"series": data}, params)["report"]["row_count"] == 1
    for bad in (True, float("nan"), 2):
        broken = series_data()
        broken["rows"][0]["values"]["water"] = bad
        with pytest.raises(ValueError, match="scientific"):
            process({"series": broken}, params)


def test_public_topics_are_split_and_request_parameters_do_not_replace_sources():
    """九个独立勘察方向各自计算，不经过整份评分；仅登记参数可调整。"""
    rows = templates()
    assert len(rows) == 20
    assert not any(row["id"] == "survey-658b" for row in rows)
    public = json.dumps(
        [{"title": row["title"], "researcher": row["researcher"]} for row in rows],
        ensure_ascii=False,
    )
    assert not any(
        term in public for term in ("658b", "冻结", "封存", "工程验收", "SHA", "制品")
    )
    ids = [
        "crop-low-temperature",
        "crop-high-temperature",
        "crop-rainfall-deficit",
        "crop-heavy-rainfall",
        "crop-disease-weather",
        "soil-properties",
        "vegetation-index-change",
        "growth-water-response",
        "yield-formation",
    ]
    for code in ids:
        row = template(code)
        compile_plan(ResearchPlan.model_validate(row["definition"]), adopted=True)
        assert all(
            node["component"]["code"] != "survey_assessment"
            for node in row["definition"]["composition"]["nodes"]
        )
    from importlib.resources import files

    archived = json.loads(files("modarchitect.contracts").joinpath("study-templates-archive-v3.json").read_text(encoding="utf-8"))
    old = next(row for row in archived if row["id"] == "crop-low-temperature")
    row = template(old["id"], old["sha256"])
    changed = deepcopy(row["definition"])
    changed["input_recipes"]["settings"]["value"]["as_of"] = "2026-10-20"
    assert matches_template(row, changed)
    changed["input_recipes"]["settings"]["value"]["rule"] = "heat_exposure"
    assert not matches_template(row, changed)
    changed = deepcopy(row["definition"])
    changed["input_recipes"]["weather"]["artifact_output"] = "another_source"
    assert not matches_template(row, changed)
