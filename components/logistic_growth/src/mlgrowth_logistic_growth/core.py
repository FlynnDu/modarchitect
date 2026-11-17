# -*- coding: utf-8 -*-
# @Time    : 2026/11/3 23:46
# @Author  : feidu
# @File    : core.py
"""三参数递增生长曲线的数值拟合与求值；x和y的业务单位由调用方明确。"""

import math

import numpy as np
from scipy.optimize import least_squares
from scipy.special import expit


def _vectors(values: list) -> np.ndarray:
    """跨进程数值边界拒绝bool、非有限数及过大序列，不把文本转换为观测。"""
    if not isinstance(values, list) or not 1 <= len(values) <= 1000:
        raise ValueError("Logistic vectors must contain 1 to 1000 values")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError("Logistic vectors must contain finite numeric values")
    return np.asarray(values, dtype=float)


def fit_curve(x_values: list, y_values: list) -> dict:
    """最小二乘估计K/r/x0；覆盖不足或参数不可辨识时失败，不生成合格模型。"""
    x, y = _vectors(x_values), _vectors(y_values)
    if len(x) != len(y) or len(np.unique(x)) < 8 or np.any(x < 0) or np.any(y < 0):
        raise ValueError(
            "Logistic fitting requires 8 distinct nonnegative driver values"
        )
    origin, span, scale = float(x.min()), float(np.ptp(x)), float(y.max())
    if span <= 0 or scale <= 0 or float(np.ptp(y)) <= 0:
        raise ValueError("Logistic fitting requires nonconstant observations")
    u, v = (x - origin) / span, y / scale

    def residual(theta):
        """归一尺度避免单位改变导致求解器数值路径失控。"""
        amplitude, rate, midpoint = theta
        return amplitude * expit(rate * (u - midpoint)) - v

    def jacobian(theta):
        """解析导数与归一参数对应，不从有量纲矩阵直接判断条件数。"""
        amplitude, rate, midpoint = theta
        fraction = expit(rate * (u - midpoint))
        slope = amplitude * fraction * (1 - fraction)
        return np.column_stack((fraction, slope * (u - midpoint), -rate * slope))

    candidates = [
        least_squares(
            residual,
            [1.1, rate, midpoint],
            jac=jacobian,
            bounds=([1e-12, 1e-12, -100], [1e6, 1e4, 100]),
            max_nfev=2000,
            ftol=1e-10,
            xtol=1e-10,
            gtol=1e-10,
        )
        for rate in (1.0, 4.0, 12.0)
        for midpoint in (0.3, 0.7)
    ]
    candidates = [result for result in candidates if result.success]
    if not candidates:
        raise ValueError("Logistic optimizer did not converge within its budget")
    optimum = min(candidates, key=lambda result: result.cost)
    amplitude, rate, midpoint = optimum.x
    fraction = expit(rate * (u - midpoint))
    jac = jacobian(optimum.x)
    norms = np.linalg.norm(jac, axis=0)
    if np.any(norms == 0):
        raise ValueError("Logistic parameters are not identifiable")
    singular = np.linalg.svd(jac / norms, compute_uv=False)
    condition = float(singular[0] / singular[-1])
    if not math.isfinite(condition) or condition > 1e8:
        raise ValueError("Logistic parameters are ill-conditioned")
    if float(fraction.min()) > 0.2 or float(fraction.max()) < 0.8:
        raise ValueError("Logistic observations have insufficient saturation coverage")
    fitted = amplitude * fraction
    error = fitted - v
    sst = float(np.sum((v - v.mean()) ** 2))
    parameters = {
        "asymptote": float(amplitude * scale),
        "rate": float(rate / span),
        "inflection": float(origin + midpoint * span),
        "x_min": float(x.min()),
        "x_max": float(x.max()),
    }
    if not all(math.isfinite(value) for value in parameters.values()):
        raise ValueError("Logistic parameters exceed their finite numeric range")
    return {
        "parameters": parameters,
        "diagnostics": {
            "sample_count": len(x),
            "distinct_x_count": len(np.unique(x)),
            "rmse_in_sample": float(np.linalg.norm(error) / math.sqrt(len(x)) * scale),
            "r_squared_in_sample": float(1 - np.sum(error**2) / sst),
            "jacobian_condition": condition,
            "minimum_saturation_fraction": float(fraction.min()),
            "maximum_saturation_fraction": float(fraction.max()),
        },
        "values": (fitted * scale).tolist(),
    }


def evaluate_curve(parameters: dict, x_values: list, allow_extrapolation: bool) -> dict:
    """用冻结参数求值；区间外求值须显式允许且逐点标识，不声称外推有效。"""
    required = {"asymptote", "rate", "inflection", "x_min", "x_max"}
    if not isinstance(parameters, dict) or set(parameters) != required:
        raise ValueError("Logistic parameter fields differ from the model contract")
    if any(
        type(v) not in (int, float) or not math.isfinite(v) for v in parameters.values()
    ):
        raise ValueError("Logistic parameters must be finite numbers")
    if (
        parameters["asymptote"] <= 0
        or parameters["rate"] <= 0
        or parameters["x_min"] >= parameters["x_max"]
    ):
        raise ValueError("Logistic parameter bounds are invalid")
    x = _vectors(x_values)
    if np.any(x < 0) or type(allow_extrapolation) is not bool:
        raise ValueError(
            "Logistic evaluation driver or extrapolation policy is invalid"
        )
    outside = (x < parameters["x_min"]) | (x > parameters["x_max"])
    if bool(outside.any()) and not allow_extrapolation:
        raise ValueError("Logistic evaluation would extrapolate beyond fitted support")
    values = parameters["asymptote"] * expit(
        parameters["rate"] * (x - parameters["inflection"])
    )
    return {"values": values.tolist(), "extrapolated": outside.tolist()}
