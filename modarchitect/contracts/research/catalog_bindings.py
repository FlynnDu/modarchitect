# -*- coding: utf-8 -*-
# @Time    : 2026/11/5 11:17
# @Author  : feidu
# @File    : catalog_bindings.py
"""指标定义与来源独立；在采集需求中冻结来源的准确版本，不复制现有标准表。"""

from collections.abc import Mapping, Sequence
from typing import Annotated, Literal
from pydantic import Field, model_validator
from modarchitect.contracts.model_center.components import (
    Code,
    Contract,
)


def source_selection_schema(options: Mapping[str, Sequence[str]]) -> dict:
    """从来源版本允许的选择生成同一份界面和发布校验合同。"""
    return {
        "type": "object",
        "properties": {
            code: {"type": "string", "enum": list(values)}
            for code, values in options.items()
        },
        "required": list(options),
        "additionalProperties": False,
    }


class CatalogBinding(Contract):
    """公开目录的准确引用；来源已实现不表示某项目已有合格数据。"""

    kind: Literal[
        "research_variable",
        "variable_source",
        "sampling_indicator",
        "timeseries_feature",
        "planned_source",
    ]
    code: Code
    definition_version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    contract_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    value_nature: Literal["observed", "estimated", "simulated", "predicted"]
    source_system: Code | None = None
    selectors: dict[Code, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def identity_kind(self):
        """核对声明类型所要求的准确目录与来源字段。"""
        if self.kind in {"research_variable", "sampling_indicator"} and (
            self.value_nature != "observed" or self.source_system is not None
        ):
            raise ValueError(
                "Manual measurement cannot impersonate a third-party source"
            )
        return self
