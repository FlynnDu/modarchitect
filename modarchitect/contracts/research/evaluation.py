# -*- coding: utf-8 -*-
# @Time    : 2026/11/4 23:47
# @Author  : feidu
# @File    : evaluation.py
"""研究拟合前冻结的数值评价口径，指标门槛不由事后报告重新解释。"""

from datetime import date
import math
from statistics import fmean
from typing import Annotated, Literal

from pydantic import Field, model_validator

from modarchitect.contracts.model_center.components import Code, Contract
from .variables import Finite


DEFAULT_TRAINING_PERCENT = 80
EvaluationMetricCode = Literal["r2", "rmse", "mae", "bias"]


def _rmse(errors: list[float], _observed: list[float]) -> float:
    """均方根误差保留目标的科学单位。"""
    return math.sqrt(fmean(value * value for value in errors))


def _mae(errors: list[float], _observed: list[float]) -> float:
    """平均绝对误差反映典型偏离大小。"""
    return fmean(abs(value) for value in errors)


def _bias(errors: list[float], _observed: list[float]) -> float:
    """平均偏差保留预测偏高或偏低的方向。"""
    return fmean(errors)


def _r2(errors: list[float], observed: list[float]) -> float | None:
    """至少两条非恒定的配对实测才允许计算决定系数。"""
    if len(observed) < 2 or min(observed) == max(observed):
        return None
    mean = fmean(observed)
    variation = fmean((value - mean) ** 2 for value in observed)
    return 1 - fmean(error * error for error in errors) / variation if variation else None


PREDICTION_METRICS = {
    "r2": ("决定系数（R²）", _r2),
    "rmse": ("均方根误差", _rmse),
    "mae": ("平均绝对误差", _mae),
    "bias": ("平均偏差", _bias),
}


class NumericEvaluationGate(Contract):
    """首期支持按完整对象的后续时间段验证，不能冒充跨地域或前瞻试验。"""

    target_code: Code
    metric: Literal["rmse", "mae"]
    maximum_error: Annotated[Finite, Field(ge=0)]
    minimum_rows: Annotated[int, Field(strict=True, ge=3, le=10000)]
    minimum_independent_units: Annotated[int, Field(strict=True, ge=1, le=10000)]
    minimum_coverage: Annotated[Finite, Field(gt=0, le=1)] = 1.0
    holdout_start: date
    holdout_end: date

    @model_validator(mode="after")
    def window(self):
        """核对留出时间窗及最低评价门槛。"""
        if self.holdout_start > self.holdout_end:
            raise ValueError("Research holdout window is reversed")
        return self
