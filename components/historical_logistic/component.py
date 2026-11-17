# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 19:25
# @Author  : Codex
# @File    : component.py
"""用封存数值内核为之后日期生成历史逻辑斯蒂预测因子。"""

from collections import defaultdict
from hashlib import sha256
import json

from mlgrowth_logistic_growth.core import evaluate_curve, fit_curve

from components.chain_tables import business_date, code, number, read_table


def forecast(inputs: dict, parameters: dict) -> dict[str, dict]:
    """按地块种植季训练，仅向基线截止日之后的业务日期发出预测。"""
    if set(parameters) != {"x_code", "target_code", "fit_through"}:
        raise ValueError("Invalid historical logistic parameters")
    x_code, target = code(parameters["x_code"]), code(parameters["target_code"])
    cutoff = business_date(parameters["fit_through"])
    table = inputs["observations"]
    columns, rows = read_table(table)
    if (
        x_code == target or columns[x_code]["unit"] != "day"
        or any(columns[key]["value_kind"] != "observed" for key in (x_code, target))
    ):
        raise ValueError("Historical logistic requires observed days and target")
    groups = defaultdict(list)
    for key, row in sorted(rows.items()):
        groups[key[:3]].append((key[3], row))
    predicted_rows = []
    fits = []
    for identity, group in groups.items():
        history = [row for day, row in group if day <= cutoff]
        future = [row for day, row in group if day > cutoff]
        if not future:
            continue
        fitted = fit_curve(
            [number(row["values"][x_code]) for row in history],
            [number(row["values"][target]) for row in history],
        )
        values = evaluate_curve(
            fitted["parameters"],
            [number(row["values"][x_code]) for row in future],
            allow_extrapolation=True,
        )["values"]
        fits.append({"object": identity, "parameters": fitted["parameters"]})
        predicted_rows.extend(
            {**row, "values": {target: value}} for row, value in zip(future, values, strict=True)
        )
    if not predicted_rows:
        raise ValueError("No forecast rows follow the fit cutoff")
    evidence = json.dumps(
        {"parameters": parameters, "fits": fits}, sort_keys=True, allow_nan=False
    ).encode()
    return {"forecast": {
        "columns": [{**columns[target], "value_kind": "predicted"}],
        "rows": predicted_rows,
        "source_sha256": list(dict.fromkeys([*table["source_sha256"], sha256(evidence).hexdigest()])),
        "fit_through": cutoff.isoformat(),
    }}
