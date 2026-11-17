# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 12:46
# @Author  : Codex
# @File    : component.py
"""按准确观测列计算描述统计，保留来源和单位，不训练预测模型。"""

import math
from statistics import mean, stdev

from components.chain_tables import number, read_table


def summarize(inputs: dict, parameters: dict) -> dict[str, dict]:
    """计算选择列的样本描述，拒绝未知列、重复选择和非有限数据。"""
    if set(parameters) != {"variables"}:
        raise ValueError("Descriptive analysis requires declared variables only")
    selected = parameters["variables"]
    if (
        not isinstance(selected, list)
        or not selected
        or any(not isinstance(c, str) for c in selected)
    ):
        raise ValueError("Analysis variables must be a nonempty code list")
    if len(set(selected)) != len(selected):
        raise ValueError("Analysis variables must be unique")
    table = inputs["observations"]
    columns, rows = read_table(table)
    if any(
        column["value_kind"] not in {"observed", "estimated", "predicted"}
        for column in columns.values()
    ):
        raise ValueError("Analysis requires an explicit supported value nature")
    if not set(selected) <= columns.keys():
        raise ValueError("Analysis variable is missing from the observation input")
    summaries = []
    for code in selected:
        values = [number(row["values"][code]) for row in rows.values()]
        average, spread = mean(values), stdev(values) if len(values) > 1 else None
        if not math.isfinite(average) or (
            spread is not None and not math.isfinite(spread)
        ):
            raise ValueError("Analysis result is not finite")
        summaries.append(
            {
                **columns[code],
                "count": len(values),
                "minimum": min(values),
                "maximum": max(values),
                "mean": average,
                "sample_std": spread,
            }
        )
    return {
        "summary": {
            "format": "research_descriptive_summary_v1",
            "row_count": len(rows),
            "object_count": len({key[:3] for key in rows}),
            "business_date_start": min(row["business_date"] for row in rows.values()),
            "business_date_end": max(row["business_date"] for row in rows.values()),
            "variables": summaries,
            "source_sha256": list(table["source_sha256"]),
        }
    }
