# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 14:11
# @Author  : Codex
# @File    : weather.py
"""对准确系统日值分析天气暴露，保留覆盖和逐日数值供真实结果绘图。"""

from datetime import timedelta
import math
from components.chain_tables import business_date, read_table

POLICIES = {
    "heat_exposure": {
        "code": "temperature_maximum_daily",
        "days": 7,
        "threshold": 35.0,
        "name": "作物高温暴露条件",
    },
    "frost_exposure": {
        "code": "temperature_minimum_daily",
        "days": 7,
        "threshold": 0.0,
        "name": "作物低温与霜冻暴露条件",
    },
    "rainfall_excess": {
        "code": "precipitation_daily",
        "days": 7,
        "threshold": 50.0,
        "name": "强降雨暴露条件",
    },
    "rainfall_deficit": {
        "code": "precipitation_daily",
        "days": 30,
        "threshold": 20.0,
        "name": "降雨不足条件",
    },
}


def object_key(row: dict) -> tuple[str, str, str]:
    """独立地块、作物和种植季分别计算，不把相邻地块混成一个窗口。"""
    obj = row["object"]
    return obj["field_ref"], obj["crop_code"], obj["season_ref"]


def conditions(inputs: dict, parameters: dict) -> dict[str, dict]:
    """研究窗口与指标由准确方法决定，缺日保留未知，不能补零或判为阴性。"""
    if set(inputs) != {"observations"} or set(parameters) != {
        "rule",
        "as_of",
        "window_days",
        "variables",
    }:
        raise ValueError(
            "Weather research requires exact inputs and declared parameters"
        )
    rule = parameters["rule"]
    policy = POLICIES.get(rule)
    if (
        policy is None
        or type(parameters["window_days"]) is not int
        or parameters["window_days"] != policy["days"]
        or parameters["variables"] != [policy["code"]]
    ):
        raise ValueError(
            "Weather method indicator or time window differs from its policy"
        )
    table = inputs["observations"]
    code = policy["code"]
    columns, indexed = read_table(table)
    unit = "mm" if code == "precipitation_daily" else "celsius"
    if (
        set(columns) != {code}
        or columns[code]["unit"] != unit
        or columns[code]["value_kind"] not in {"observed", "estimated"}
    ):
        raise ValueError("Weather indicator, scientific unit or nature differs")
    end = business_date(parameters["as_of"])
    start = end - timedelta(days=policy["days"] - 1)
    dates = {(start + timedelta(days=i)).isoformat() for i in range(policy["days"])}
    groups, objects, selected_rows = {}, {}, []
    seen = set()
    for row in indexed.values():
        key, day = object_key(row), row["business_date"]
        if (key, day) in seen or set(row["values"]) != {code}:
            raise ValueError(
                "Weather records have duplicate objects or undeclared columns"
            )
        seen.add((key, day))
        value = row["values"][code]
        if type(value) not in {float, int} or not math.isfinite(value):
            raise ValueError("Weather conditions require finite numeric source values")
        if business_date(day) > end or (code == "precipitation_daily" and value < 0):
            raise ValueError(
                "Weather record exceeds the cutoff or contains negative rainfall"
            )
        objects[key] = row["object"]
        groups.setdefault(key, {})
        if day in dates:
            groups[key][day] = value
            selected_rows.append(row)
    reports = []
    for key, values in groups.items():
        complete = set(values) == dates
        numbers = list(values.values())
        metric = (
            (
                max(numbers)
                if rule == "heat_exposure"
                else min(numbers)
                if rule == "frost_exposure"
                else sum(numbers)
            )
            if numbers
            else None
        )
        triggered = metric is not None and (
            metric >= policy["threshold"]
            if rule in {"heat_exposure", "rainfall_excess"}
            else metric <= policy["threshold"]
            if rule == "frost_exposure"
            else complete and metric < policy["threshold"]
        )
        result = (
            "triggered"
            if triggered
            else "not_triggered"
            if complete
            else "not_evaluated"
        )
        reports.append(
            {
                "object": objects[key],
                "name": policy["name"],
                "result": result,
                "qualification": "complete"
                if complete
                else "partial"
                if values
                else "unavailable",
                "metric": metric,
                "threshold": policy["threshold"],
                "unit": unit,
                "window": {
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "expected_days": policy["days"],
                    "valid_days": len(values),
                    "missing_dates": sorted(dates - set(values)),
                },
            }
        )
    return {
        "report": {
            "format": "catalog_weather_conditions_v1",
            "as_of": end.isoformat(),
            "rule": rule,
            "results": reports,
            "interpretation": "气象条件信号不等于已发生灾损；网格估计不替代田间证据。",
        },
        "series": {
            "columns": table["columns"],
            "rows": selected_rows,
            "source_sha256": table["source_sha256"],
        },
    }
