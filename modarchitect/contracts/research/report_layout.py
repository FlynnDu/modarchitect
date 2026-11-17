# -*- coding: utf-8 -*-
# @Time    : 2026/11/6 16:12
# @Author  : feidu
# @File    : report_layout.py
"""从已登记输出端口编译报告展示计划；不解释数据、不执行计算。"""

from typing import Annotated, Literal

from pydantic import Field

from modarchitect.contracts.model_center.components import (
    Code,
    Contract,
)


class ReportOptions(Contract):
    """只允许调整标题和报告所选输出顺序，科学组件和必读说明独立。"""

    schema_version: Literal["1.0"] = "1.0"
    title: Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")] | None = (
        None
    )
    outputs: Annotated[tuple[Code, ...], Field(min_length=1, max_length=64)] | None = (
        None
    )
