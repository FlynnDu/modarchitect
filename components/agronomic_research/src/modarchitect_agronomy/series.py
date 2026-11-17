# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 17:13
# @Author  : Codex
# @File    : series.py
"""分析明确来源与单位的农业指标序列，不把模拟值改称实测值。"""

from datetime import date
import math
from statistics import mean, stdev


def process(inputs: dict, parameters: dict) -> dict[str, dict]:
    """按用户选择的日期与固定指标计算过程描述及同日关系，缺测不补零。"""
    if set(inputs) != {"series"} or set(parameters) != {
        "variables",
        "start_date",
        "end_date",
    }:
        raise ValueError("Indicator research requires declared inputs and parameters")
    data = inputs["series"]
    if (
        data.get("schema_version") != "1.0"
        or not 1 <= len(data.get("rows", [])) <= 5000
    ):
        raise ValueError("Indicator research data is invalid")
    variables = {item["code"]: item for item in data["variables"]}
    if len(variables) != len(data["variables"]) or not 1 <= len(variables) <= 128:
        raise ValueError("Indicator definitions must be unique and bounded")
    for item in variables.values():
        if (
            item["value_kind"] not in {"observed", "estimated", "simulated"}
            or not item.get("unit")
            or not item.get("name")
        ):
            raise ValueError("Indicator scientific unit and value nature are required")
    selected = parameters["variables"]
    if (
        not isinstance(selected, list)
        or not selected
        or len(set(selected)) != len(selected)
        or not set(selected) <= set(variables)
    ):
        raise ValueError("Selected indicators differ from the declared data")
    start, end = (
        date.fromisoformat(parameters["start_date"]),
        date.fromisoformat(parameters["end_date"]),
    )
    if start > end:
        raise ValueError("Research date window is reversed")
    rows, seen = [], set()
    for row in data["rows"]:
        day = date.fromisoformat(row["date"])
        if day in seen:
            raise ValueError("Indicator dates must be unique")
        seen.add(day)
        if set(row["values"]) != set(variables):
            raise ValueError("Indicator row columns differ")
        for code, value in row["values"].items():
            if value is None:
                continue
            definition = variables[code]
            if (
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not math.isfinite(value)
                or value < definition.get("minimum", -math.inf)
                or value > definition.get("maximum", math.inf)
            ):
                raise ValueError("Indicator value is outside its scientific definition")
        if start <= day <= end:
            rows.append(row)
    rows.sort(key=lambda row: row["date"])
    if not rows:
        raise ValueError("Research window contains no available indicator records")
    summaries = []
    for code in selected:
        present = [row for row in rows if row["values"][code] is not None]
        numbers = [row["values"][code] for row in present]
        summaries.append(
            {
                **variables[code],
                "count": len(numbers),
                "missing_count": len(rows) - len(numbers),
                "minimum_value": min(numbers) if numbers else None,
                "maximum_value": max(numbers) if numbers else None,
                "mean": mean(numbers) if numbers else None,
                "sample_std": stdev(numbers) if len(numbers) > 1 else None,
                "first_date": present[0]["date"] if present else None,
                "last_date": present[-1]["date"] if present else None,
                "change": numbers[-1] - numbers[0] if len(numbers) > 1 else None,
            }
        )
    relationships = []
    for index, left in enumerate(selected):
        for right in selected[index + 1 :]:
            pairs = [
                (row["values"][left], row["values"][right])
                for row in rows
                if row["values"][left] is not None and row["values"][right] is not None
            ]
            coefficient, status = None, "insufficient_pairs"
            if len(pairs) >= 3:
                x, y = zip(*pairs)
                mx, my = mean(x), mean(y)
                xx, yy = sum((v - mx) ** 2 for v in x), sum((v - my) ** 2 for v in y)
                if xx and yy:
                    coefficient = max(
                        -1.0,
                        min(
                            1.0,
                            sum((a - mx) * (b - my) for a, b in pairs)
                            / math.sqrt(xx * yy),
                        ),
                    )
                    status = "descriptive_correlation"
                else:
                    status = "constant_indicator"
            relationships.append(
                {
                    "left": left,
                    "right": right,
                    "paired_rows": len(pairs),
                    "correlation": coefficient,
                    "status": status,
                }
            )
    return {
        "report": {
            "format": "agronomic_indicator_analysis_v1",
            "context": data["context"],
            "source_description": data["source_description"],
            "start_date": parameters["start_date"],
            "end_date": parameters["end_date"],
            "row_count": len(rows),
            "indicators": summaries,
            "relationships": relationships,
            "series": [
                {
                    "date": row["date"],
                    "values": {code: row["values"][code] for code in selected},
                }
                for row in rows
            ],
            "interpretation": "指标性质与数据支撑保持原样；同日相关不代表因果关系，模拟过程不能代替田间实测。",
        }
    }
