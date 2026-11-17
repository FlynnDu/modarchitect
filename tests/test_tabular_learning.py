# -*- coding: utf-8 -*-
# @Time    : 2026/11/16 20:16
# @Author  : Codex
# @File    : test_tabular_learning.py
"""用独立算法参考及失败输入检验多目标训练、状态保存和无标签推理。"""

from copy import deepcopy
from datetime import date, timedelta
import json

import numpy as np
import pytest

from components.tabular_learning.component import predict, train

ALGORITHMS = ("random_forest", "xgboost", "gaussian_process")
PARAMETERS = {"features": ["temperature", "soil"], "targets": ["height", "leaf"], "training_end": "2026-05-24", "seed": 17}


def observations() -> dict:
    """独立生成含两地块和不同目标单位的非线性合成资料。"""
    columns = [{"code": code, "name": code, "unit": unit, "value_kind": kind} for code, unit, kind in (("temperature", "celsius", "estimated"), ("soil", "fraction", "estimated"), ("height", "cm", "observed"), ("leaf", "cm2", "observed"))]
    rows = []
    for field in ("a", "b"):
        for index in range(30):
            x, soil = 18 + (index % 9), 0.1 + 0.01 * index + (0.03 if field == "b" else 0)
            rows.append({"object": {"field_ref": field, "crop_code": "potato", "season_ref": "2026"}, "business_date": (date(2026, 5, 1) + timedelta(days=index)).isoformat(), "values": {"temperature": x, "soil": soil, "height": x * soil + 2, "leaf": x + 30 * soil ** 2}})
    return {"columns": columns, "rows": rows, "source_sha256": ["a" * 64]}


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_saved_state_matches_reference_and_does_not_fit_holdout(algorithm: str) -> None:
    """与独立拟合结果对照，JSON往返不改数值，改变留出标签不改训练状态。"""
    table = observations()
    result = train({"observations": table}, PARAMETERS, algorithm=algorithm)
    model = json.loads(json.dumps(result["trained_model"], allow_nan=False))
    assert model["training_rows"] == 48 and len(model["training_objects"]) == 2
    held = [row for row in table["rows"] if row["business_date"] > PARAMETERS["training_end"]]
    training = sorted([row for row in table["rows"] if row["business_date"] <= PARAMETERS["training_end"]], key=lambda row: (row["object"]["field_ref"], row["business_date"]))
    future = {**table, "columns": table["columns"][:2], "rows": [{**row, "values": {code: row["values"][code] for code in PARAMETERS["features"]}} for row in held]}
    actual = predict({"observations": future, "model": model}, {}, algorithm=algorithm)["predictions"]
    assert len(actual["rows"]) == 12 and all(column["value_kind"] == "predicted" for column in actual["columns"])
    assert actual == result["predictions"]
    x = np.asarray([[row["values"][code] for code in PARAMETERS["features"]] for row in training])
    points = np.asarray([[row["values"][code] for code in PARAMETERS["features"]] for row in held])
    y = np.asarray([row["values"]["height"] for row in training])
    if algorithm == "random_forest":
        from sklearn.ensemble import RandomForestRegressor

        reference = RandomForestRegressor(n_estimators=64, max_depth=8, n_jobs=1, random_state=17)
    elif algorithm == "xgboost":
        from xgboost import XGBRegressor

        reference = XGBRegressor(n_estimators=64, max_depth=4, learning_rate=0.08, tree_method="hist", device="cpu", n_jobs=1, random_state=17)
    else:
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import RBF
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        reference = make_pipeline(StandardScaler(), GaussianProcessRegressor(kernel=RBF(1.0), alpha=0.01, optimizer=None, normalize_y=True))
    expected = reference.fit(x, y).predict(points)
    np.testing.assert_allclose([row["values"]["height"] for row in actual["rows"]], expected, atol=1e-8, rtol=1e-7)
    poisoned = deepcopy(table)
    for row in poisoned["rows"]:
        if row["business_date"] > PARAMETERS["training_end"]:
            row["values"]["height"] = 1000000
    again = train({"observations": poisoned}, PARAMETERS, algorithm=algorithm)
    assert again["trained_model"]["states"] == model["states"]


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_reject_invalid_scientific_inputs_and_state(algorithm: str) -> None:
    """拒绝伪实测、重叠目标、缺失值、错单位、重复对象日及错误算法状态。"""
    table = observations()
    with pytest.raises(ValueError, match="distinct"):
        train({"observations": table}, {**PARAMETERS, "targets": ["soil"]}, algorithm=algorithm)
    repeated = deepcopy(table)
    repeated["rows"].append(repeated["rows"][0])
    with pytest.raises(ValueError, match="duplicate"):
        train({"observations": repeated}, PARAMETERS, algorithm=algorithm)
    missing = deepcopy(table)
    missing["rows"][0]["values"]["soil"] = None
    with pytest.raises(ValueError, match="finite"):
        train({"observations": missing}, PARAMETERS, algorithm=algorithm)
    model = train({"observations": table}, PARAMETERS, algorithm=algorithm)["trained_model"]
    wrong = deepcopy(table)
    wrong["columns"][0]["unit"] = "kelvin"
    with pytest.raises(ValueError, match="unit"):
        predict({"observations": wrong, "model": model}, {}, algorithm=algorithm)
    with pytest.raises(ValueError, match="algorithm"):
        predict({"observations": table, "model": {**model, "algorithm": "other"}}, {}, algorithm=algorithm)
