# -*- coding: utf-8 -*-
# @Time    : 2026/11/16 20:13
# @Author  : Codex
# @File    : component.py
"""将标准观测表绑定为可保存、多目标的回归训练及独立预测。"""

from importlib.metadata import version
import json

import numpy as np

from components.chain_tables import business_date, read_table
from components.multivariate_regression.component import numeric_values, selected_codes
from . import estimators


def _estimates(algorithm: str, model: dict, table: dict, rows: list[dict]) -> dict:
    """按冻结特征和单位预测，只输出准确目标列。"""
    columns = {column["code"]: column for column in table["columns"]}
    for column in model["feature_columns"]:
        if column["code"] not in columns or columns[column["code"]]["unit"] != column["unit"]:
            raise ValueError("Prediction feature is missing or its unit differs")
    features = [column["code"] for column in model["feature_columns"]]
    values = [{} for _ in rows]
    if rows:
        x = np.asarray([numeric_values(row, features) for row in rows], dtype=float)
        for column, state in zip(model["target_columns"], model["states"], strict=True):
            estimates = estimators.predict(algorithm, state, x)
            if estimates.shape != (len(rows),) or not np.isfinite(estimates).all():
                raise ValueError("Predictions must be finite and match input rows")
            for row, estimate in zip(values, estimates.tolist(), strict=True):
                row[column["code"]] = estimate
    return {"columns": model["target_columns"], "rows": [{"object": row["object"], "business_date": row["business_date"], "values": result} for row, result in zip(rows, values, strict=True)], "source_sha256": table["source_sha256"]}


def train(inputs: dict, parameters: dict, *, algorithm: str) -> dict[str, dict]:
    """封存截止日内训练状态，对截止日之后的因素计算留出预测。"""
    if set(parameters) - {"features", "targets", "training_end", "seed"} or not {"features", "targets", "training_end"} <= parameters.keys():
        raise ValueError("Invalid tabular training parameters")
    features, targets = selected_codes(parameters["features"]), selected_codes(parameters["targets"])
    seed = parameters.get("seed", 17)
    if type(seed) is not int or not 0 <= seed <= 2147483647:
        raise ValueError("Invalid random seed")
    table = inputs["observations"]
    columns, keyed = read_table(table)
    if set(features) & set(targets) or not set(features + targets) <= columns.keys() or any(columns[code]["value_kind"] != "observed" for code in targets):
        raise ValueError("Training requires distinct factors and observed target columns")
    cutoff = business_date(parameters["training_end"])
    training = [row for key, row in sorted(keyed.items()) if key[3] <= cutoff]
    future = [row for key, row in sorted(keyed.items()) if key[3] > cutoff]
    limit = 1000 if algorithm == "gaussian_process" else 10000
    if not 8 <= len(training) <= limit or len(keyed) * len(features) > 500000:
        raise ValueError("Training exceeds the declared sample resource budget or has fewer than eight rows")
    x = np.asarray([numeric_values(row, features) for row in training], dtype=float)
    y = np.asarray([numeric_values(row, targets) for row in training], dtype=float)
    model = {"format": "tabular_regression_state_v1", "algorithm": algorithm, "parameters": {**parameters, "seed": seed},
             "feature_columns": [columns[code] for code in features],
             "target_columns": [{**columns[code], "value_kind": "predicted"} for code in targets],
             "training_end": cutoff.isoformat(), "training_rows": len(training),
             "training_objects": sorted({tuple(row["object"][key] for key in ("field_ref", "crop_code", "season_ref")) for row in training}),
             "source_sha256": table["source_sha256"],
             "runtime": {name: version(name) for name in ("numpy", "scikit-learn")},
             "states": [estimators.fit(algorithm, x, y[:, index], seed) for index in range(len(targets))]}
    if algorithm == "xgboost":
        from xgboost import __version__ as xgboost_version

        model["runtime"]["xgboost"] = xgboost_version
    if len(json.dumps(model, allow_nan=False, separators=(",", ":")).encode("utf-8")) > 3_800_000:
        raise ValueError("Trained model exceeds the reusable state byte budget")
    return {"trained_model": model, "predictions": _estimates(algorithm, model, table, future)}


def predict(inputs: dict, parameters: dict, *, algorithm: str) -> dict[str, dict]:
    """读取准确模型状态，因素单位必须一致，预测不要求目标标签。"""
    model = inputs["model"]
    if parameters or model.get("format") != "tabular_regression_state_v1" or model.get("algorithm") != algorithm:
        raise ValueError("Model format, algorithm or prediction parameters differ")
    selected_codes([column["code"] for column in model["feature_columns"]])
    selected_codes([column["code"] for column in model["target_columns"]])
    if any(column["value_kind"] != "predicted" for column in model["target_columns"]):
        raise ValueError("Model targets must be declared predicted")
    _, rows = read_table(inputs["observations"])
    if len(rows) * len(model["feature_columns"]) > 500000:
        raise ValueError("Prediction exceeds the declared resource budget")
    return {"predictions": _estimates(algorithm, model, inputs["observations"], list(rows.values()))}
