# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 17:13
# @Author  : Codex
# @File    : weather.py
"""将已拆分的权威气象规则用于独立研究，保留逐变量来源与窗口资格。"""

from datetime import date

RULES = {
    "frost_exposure": "weather_frost_exposure",
    "heat_exposure": "weather_heat_exposure",
    "rainfall_deficit": "weather_rainfall_deficit",
    "rainfall_excess": "weather_rainfall_excess",
    "warm_humid_disease": "weather_warm_humid_disease",
}


def conditions(inputs: dict, parameters: dict) -> dict[str, dict]:
    """调用原规则的准确版本，不经过整份勘察评分或章节提取。"""
    if set(inputs) != {"weather"} or set(parameters) != {"rule", "as_of", "crop_code"}:
        raise ValueError(
            "Weather condition research requires declared inputs and parameters"
        )
    rule = parameters["rule"]
    if rule not in RULES:
        raise ValueError("Weather research rule is not registered")
    if parameters["crop_code"] not in ("potato", "wheat", "maize", "tomato"):
        raise ValueError("Weather research crop is outside the declared contract")
    data = inputs["weather"]
    if (
        data.get("schema_version") != "1.0"
        or not isinstance(data.get("rows"), list)
        or not 1 <= len(data["rows"]) <= 5000
    ):
        raise ValueError("Weather research data is invalid")
    from pymlgrowth.model_components.registry import resolve_implementation

    operation = resolve_implementation(RULES[rule], 4)
    result = operation(
        weather_rows=data["rows"],
        as_of=date.fromisoformat(parameters["as_of"]),
        crop_code=parameters["crop_code"],
    )
    return {
        "report": {
            "format": "research_weather_conditions_v1",
            "as_of": parameters["as_of"],
            "crop_code": parameters["crop_code"],
            "source_description": data["source_description"],
            "rule": result["rule"],
            "candidate": result["candidate"],
            "interpretation": "这是气象条件分析。实际灾损、病害发生和根区水分状态仍需要同对象的田间证据。",
        }
    }
