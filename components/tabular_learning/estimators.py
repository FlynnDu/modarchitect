# -*- coding: utf-8 -*-
# @Time    : 2026/11/16 20:13
# @Author  : Codex
# @File    : estimators.py
"""训练表格回归算法并用显式JSON状态执行独立推理。"""

import json

import numpy as np


def fit(algorithm: str, x: np.ndarray, y: np.ndarray, seed: int) -> dict:
    """每个目标独立拟合；标准化只使用训练行，不读取后段标签。"""
    if algorithm == "random_forest":
        from sklearn.ensemble import RandomForestRegressor

        model = RandomForestRegressor(n_estimators=64, max_depth=8, n_jobs=1, random_state=seed).fit(x, y)
        return {"trees": [{"left": tree.tree_.children_left.tolist(), "right": tree.tree_.children_right.tolist(),
                           "feature": tree.tree_.feature.tolist(), "threshold": tree.tree_.threshold.tolist(),
                           "value": tree.tree_.value[:, 0, 0].tolist()} for tree in model.estimators_]}
    if algorithm == "xgboost":
        from xgboost import XGBRegressor

        model = XGBRegressor(n_estimators=64, max_depth=4, learning_rate=0.08, tree_method="hist", device="cpu", n_jobs=1, random_state=seed).fit(x, y)
        return {"booster": json.loads(model.get_booster().save_raw(raw_format="json"))}
    if algorithm == "gaussian_process":
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import RBF
        from sklearn.preprocessing import StandardScaler

        scaler = StandardScaler().fit(x)
        scaled = scaler.transform(x)
        model = GaussianProcessRegressor(kernel=RBF(1.0), alpha=0.01, optimizer=None, normalize_y=True).fit(scaled, y)
        return {"feature_mean": scaler.mean_.tolist(), "feature_scale": scaler.scale_.tolist(),
                "x_train": scaled.tolist(), "dual": model.alpha_.tolist(),
                "target_mean": float(model._y_train_mean), "target_scale": float(model._y_train_std)}
    raise ValueError("Unknown tabular regression algorithm")


def predict(algorithm: str, state: dict, x: np.ndarray) -> np.ndarray:
    """仅解析指定算法的JSON数值状态，不恢复任意Python对象。"""
    if algorithm == "random_forest":
        trees = state["trees"]
        if not trees or len(trees) > 64:
            raise ValueError("Invalid forest tree count")
        result = np.zeros(len(x))
        # sklearn树训练和预测会将输入转换成float32，独立推理保持相同阈值口径。
        values = x.astype(np.float32)
        for tree in trees:
            count = len(tree["value"])
            if not count or count > 511 or any(len(tree[key]) != count for key in ("left", "right", "feature", "threshold")):
                raise ValueError("Invalid forest tree shape")
            for row, vector in enumerate(values):
                node = 0
                for _ in range(10):
                    if node < 0 or node >= count:
                        raise ValueError("Invalid forest child index")
                    left, right = tree["left"][node], tree["right"][node]
                    if left == right == -1:
                        result[row] += tree["value"][node]
                        break
                    feature = tree["feature"][node]
                    if type(feature) is not int or not 0 <= feature < x.shape[1]:
                        raise ValueError("Invalid forest feature index")
                    node = left if vector[feature] <= tree["threshold"][node] else right
                else:
                    raise ValueError("Forest exceeds declared depth")
        return result / len(trees)
    if algorithm == "xgboost":
        from xgboost import Booster, DMatrix

        model = Booster(params={"nthread": 1, "device": "cpu"})
        model.load_model(bytearray(json.dumps(state["booster"]).encode("utf-8")))
        if model.num_features() != x.shape[1] or model.num_boosted_rounds() > 64:
            raise ValueError("Invalid booster dimensions")
        return model.predict(DMatrix(x))
    if algorithm == "gaussian_process":
        scale = np.asarray(state["feature_scale"], dtype=float)
        mean = np.asarray(state["feature_mean"], dtype=float)
        training = np.asarray(state["x_train"], dtype=float)
        dual = np.asarray(state["dual"], dtype=float)
        if scale.shape != (x.shape[1],) or mean.shape != scale.shape or np.any(scale <= 0) or training.ndim != 2 or training.shape[1] != x.shape[1] or dual.shape != (len(training),) or len(training) > 1000:
            raise ValueError("Invalid Gaussian process state dimensions")
        scaled = (x - mean) / scale
        # 分块计算核矩阵，避免大量预测行一次性分配三维距离数组。
        values = []
        for start in range(0, len(x), 128):
            block = scaled[start:start + 128]
            distance = np.maximum((block ** 2).sum(axis=1)[:, None] + (training ** 2).sum(axis=1)[None, :] - 2 * block @ training.T, 0)
            values.extend((np.exp(-0.5 * distance) @ dual * state["target_scale"] + state["target_mean"]).tolist())
        return np.asarray(values)
    raise ValueError("Unknown tabular regression algorithm")
