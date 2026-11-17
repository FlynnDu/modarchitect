# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 18:24
# @Author  : Codex
# @File    : component.py
"""以日期截点训练多目标线性回归，并预测随后日期的数值。"""

from datetime import date
import math
import re

import numpy as np


def selected_codes(value: object) -> list[str]:
    """校验顺序明确、无重复的变量选择。"""
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,95}", code) for code in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError("Invalid regression columns")
    return value


def numeric_values(row: dict, codes: list[str]) -> list[float]:
    """读取完整有限数值，不自动补值或把布尔值当数值。"""
    values = [row["values"][code] for code in codes]
    if any(type(value) not in {int, float} or not math.isfinite(value) for value in values):
        raise ValueError("Regression requires complete finite observations")
    return values


def business_day(value: str) -> date:
    """校验并解析统一格式的业务日期。"""
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Expected an ISO business date")
    return parsed


def split_rows(table: dict, cutoff: date) -> tuple[list[dict], list[dict]]:
    """以完整对象和业务日期去重，并冻结训练与预测两组。"""
    if set(table) != {"columns", "rows", "source_sha256"}:
        raise ValueError("Invalid observation table")
    training, future, seen = [], [], set()
    for row in table["rows"]:
        obj = row["object"]
        day = business_day(row["business_date"])
        key = (obj["field_ref"], obj["crop_code"], obj["season_ref"], day)
        if key in seen or any(not isinstance(value, str) or not value for value in key[:3]):
            raise ValueError("Duplicate or invalid object date")
        seen.add(key)
        (training if day <= cutoff else future).append(row)
    return training, future


def train_predict(inputs: dict, parameters: dict) -> dict[str, dict]:
    """按用户选择绑定各列，输出线性模型及逐目标预测值。"""
    if set(parameters) != {"features", "targets", "training_end"}:
        raise ValueError("Invalid regression parameters")
    features = selected_codes(parameters["features"])
    targets = selected_codes(parameters["targets"])
    cutoff = business_day(parameters["training_end"])
    table = inputs["observations"]
    columns = {column["code"]: column for column in table["columns"]}
    if (
        set(features) & set(targets)
        or len(columns) != len(table["columns"])
        or not set(features + targets) <= columns.keys()
        or any(columns[code]["value_kind"] != "observed" for code in targets)
    ):
        raise ValueError("Regression requires distinct input and observed target columns")
    training, future = split_rows(table, cutoff)
    if len(training) <= len(features) + 1:
        raise ValueError("Insufficient training observations")
    x = np.asarray([[1, *numeric_values(row, features)] for row in training], dtype=float)
    y = np.asarray([numeric_values(row, targets) for row in training], dtype=float)
    coefficients, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)
    if rank != x.shape[1] or not np.isfinite(coefficients).all():
        raise ValueError("Training predictors are not identifiable")
    output_rows = []
    for row in future:
        predicted = np.asarray([1, *numeric_values(row, features)]) @ coefficients
        if not np.isfinite(predicted).all():
            raise ValueError("Predicted values must be finite")
        output_rows.append({
            "object": row["object"],
            "business_date": row["business_date"],
            "values": dict(zip(targets, predicted.tolist(), strict=True)),
        })
    model = {
        "algorithm": "ordinary_least_squares_v1",
        "training_end": cutoff.isoformat(),
        "training_rows": len(training),
        "feature_codes": features,
        "target_codes": targets,
        "intercepts": dict(zip(targets, coefficients[0].tolist(), strict=True)),
        "coefficients": dict(zip(features, coefficients[1:].tolist(), strict=True)),
        "source_sha256": table["source_sha256"],
    }
    prediction = {
        "columns": [{**columns[code], "value_kind": "predicted"} for code in targets],
        "rows": output_rows,
        "source_sha256": table["source_sha256"],
    }
    return {"trained_model": model, "predictions": prediction}
