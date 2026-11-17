# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 21:13
# @Author  : Codex
# @File    : growth.py
"""保存逻辑斯蒂训练状态，并按准确状态生成后续预测因子。"""

from collections import defaultdict
from hashlib import sha256
import json

from mlgrowth_logistic_growth.core import evaluate_curve, fit_curve

from components.chain_tables import business_date, code, number, read_table


def forecast(inputs: dict, parameters: dict) -> dict[str, dict]:
    """按对象拟合一次，同时返回可复用模型和留出预测。"""
    if set(parameters) != {"x_code", "target_code", "fit_through"}:
        raise ValueError("Invalid logistic training parameters")
    x_code, target = code(parameters["x_code"]), code(parameters["target_code"])
    cutoff = business_date(parameters["fit_through"])
    table = inputs["observations"]
    columns, rows = read_table(table)
    if (
        x_code == target
        or columns[x_code]["unit"] != "day"
        or any(columns[item]["value_kind"] != "observed" for item in (x_code, target))
    ):
        raise ValueError("Logistic fitting requires observed days and target")
    groups = defaultdict(list)
    for key, row in sorted(rows.items()):
        groups[key[:3]].append((key[3], row))
    states = []
    for identity, group in groups.items():
        history = [row for day, row in group if day <= cutoff]
        fitted = fit_curve(
            [number(row["values"][x_code]) for row in history],
            [number(row["values"][target]) for row in history],
        )
        states.append({"object": list(identity), "parameters": fitted["parameters"]})
    model = {
        "format": "logistic_state_v1",
        "x_column": columns[x_code],
        "target_column": columns[target],
        "fit_through": cutoff.isoformat(),
        "states": states,
        "source_sha256": table["source_sha256"],
    }
    future = {**table, "rows": [row for key, row in rows.items() if key[3] > cutoff]}
    return {
        "trained_model": model,
        **predict({"model": model, "observations": future}, {}),
    }


def predict(inputs: dict, parameters: dict) -> dict[str, dict]:
    """只读取已训练参数，预测新对象日期，拒绝缺模型或错误单位。"""
    if parameters:
        raise ValueError("Logistic inference has no mutable fitting parameters")
    model = inputs["model"]
    if model.get("format") != "logistic_state_v1":
        raise ValueError("Invalid logistic model format")
    columns, rows = read_table(inputs["observations"])
    x_column, target = model["x_column"], model["target_column"]
    if columns[x_column["code"]]["unit"] != x_column["unit"]:
        raise ValueError("Logistic inference unit differs")
    states = {tuple(item["object"]): item["parameters"] for item in model["states"]}
    cutoff = business_date(model["fit_through"])
    result = []
    for key, row in sorted(rows.items()):
        if key[:3] not in states or key[3] <= cutoff:
            raise ValueError("Prediction is outside the fitted object or time range")
        value = evaluate_curve(
            states[key[:3]],
            [number(row["values"][x_column["code"]])],
            allow_extrapolation=True,
        )["values"][0]
        result.append({**row, "values": {target["code"]: value}})
    return {
        "forecast": {
            "columns": [{**target, "value_kind": "predicted"}],
            "rows": result,
            "source_sha256": list(
                dict.fromkeys(
                    [
                        *model["source_sha256"],
                        *inputs["observations"]["source_sha256"],
                        sha256(
                            json.dumps(model, sort_keys=True, allow_nan=False).encode(
                                "utf-8"
                            )
                        ).hexdigest(),
                    ]
                )
            ),
            "fit_through": model["fit_through"],
        }
    }
