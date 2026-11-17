# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 21:13
# @Author  : Codex
# @File    : linear.py
"""在独立组件中使用冻结线性系数预测，保持特征和目标定义。"""

import math

from components.chain_tables import number, read_table
from components.multivariate_regression.component import train_predict


def train(inputs: dict, parameters: dict) -> dict[str, dict]:
    """复用已验收的回归算法，补齐独立推理需要的准确列定义。"""
    result = train_predict(inputs, parameters)
    columns = {column["code"]: column for column in inputs["observations"]["columns"]}
    state = result["trained_model"]
    result["trained_model"] = {
        "format": "linear_state_v1",
        "state": state,
        "feature_columns": [columns[code] for code in state["feature_codes"]],
        "target_columns": result["predictions"]["columns"],
        "training_objects": sorted(
            {
                (
                    row["object"]["field_ref"],
                    row["object"]["crop_code"],
                    row["object"]["season_ref"],
                )
                for row in inputs["observations"]["rows"]
                if row["business_date"] <= state["training_end"]
            }
        ),
    }
    return result


def predict(inputs: dict, parameters: dict) -> dict[str, dict]:
    """按特征代码绑定输入，预测阶段不读取或拟合目标标签。"""
    if parameters:
        raise ValueError("Linear inference has no mutable fitting parameters")
    bundle = inputs["model"]
    if bundle.get("format") != "linear_state_v1":
        raise ValueError("Invalid linear model format")
    state = bundle["state"]
    columns, rows = read_table(inputs["observations"])
    features, targets = state["feature_codes"], state["target_codes"]
    for column in bundle["feature_columns"]:
        if columns[column["code"]]["unit"] != column["unit"]:
            raise ValueError("Linear inference feature unit differs")
    predictions = []
    for row in rows.values():
        values = {}
        for index, target in enumerate(targets):
            value = number(state["intercepts"][target]) + sum(
                number(row["values"][feature])
                * number(state["coefficients"][feature][index])
                for feature in features
            )
            if not math.isfinite(value):
                raise ValueError("Linear prediction is not finite")
            values[target] = value
        predictions.append({**row, "values": values})
    return {
        "predictions": {
            "columns": bundle["target_columns"],
            "rows": predictions,
            "source_sha256": inputs["observations"]["source_sha256"],
        }
    }
