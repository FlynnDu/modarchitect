# -*- coding: utf-8 -*-
# @Time    : 2026/11/4 23:47
# @Author  : feidu
# @File    : evaluation.py
"""研究拟合前冻结的数值评价口径，指标门槛不由事后报告重新解释。"""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, model_validator

from modarchitect.contracts.model_center.components import Code, Contract
from .variables import Finite


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
