# -*- coding: utf-8 -*-
# @Time    : 2026/11/4 22:29
# @Author  : feidu
# @File    : variables.py
"""研究变量与科学单位；试验分配、实际观测和数值特征分别表达。"""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from modarchitect.contracts.model_center.components import Code, Contract, Text

Finite = Annotated[float, Field(strict=True, allow_inf_nan=False)]
UnitKind = Literal["field_season", "quadrat", "plant", "soil_layer", "point", "report_area"]
VariableRole = Literal[
    "treatment", "group", "covariate", "driver", "target", "validation", "parameter"
]


class Variable(Contract):
    """方案内冻结变量定义，不将用户私有变量自动注册成平台预测标准。"""

    code: Code
    name: Text
    definition_version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    description: Text
    value_type: Literal["number", "category"]
    unit: Text
    role: VariableRole
    minimum: Finite | None = None
    maximum: Finite | None = None
    categories: tuple[Code, ...] = ()

    @model_validator(mode="after")
    def scientific_definition(self):
        """类别不得伪装连续量；范围与枚举属于版本化的科学含义。"""
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("Research variable range is reversed")
        if self.value_type == "category":
            if not self.categories or len(set(self.categories)) != len(self.categories):
                raise ValueError("Categorical variable requires unique categories")
            if self.minimum is not None or self.maximum is not None:
                raise ValueError("Categorical variable cannot declare numeric bounds")
        elif self.categories:
            raise ValueError("Numeric variable cannot declare categories")
        return self

    def validate_value(self, value: object) -> None:
        """在采集边界核对实际值，拒绝布尔数值、非有限量及未知类别。"""
        import math

        if self.value_type == "category":
            valid = isinstance(value, str) and value in self.categories
        else:
            valid = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and (self.minimum is None or value >= self.minimum)
                and (self.maximum is None or value <= self.maximum)
            )
        if not valid:
            raise ValueError("Research variable %s has an invalid value" % self.code)


class ScientificUnit(Contract):
    """业务系统的实际对象引用及研究内层级；不在本系统管理地块主数据。"""

    unit_ref: Text
    kind: UnitKind
    field_ref: Text
    crop_code: Code
    season_ref: Text
    parent_ref: Text | None = None
    experimental_unit_ref: Text
    block_ref: Text | None = None
    assignments: dict[Code, str | Finite] = Field(default_factory=dict)


class StudyContext(Contract):
    """研究实例的确切对象集合，实际种植季和对象归属须由可信适配器核验。"""

    project_ref: Text
    season_start: date
    season_end: date
    units: Annotated[tuple[ScientificUnit, ...], Field(min_length=1, max_length=10000)]

    @model_validator(mode="after")
    def unit_hierarchy(self):
        """全部单位同一研究边界，父对象和试验单位均须能解析且没有循环。"""
        if self.season_start > self.season_end:
            raise ValueError("Study season dates are reversed")
        units = {unit.unit_ref: unit for unit in self.units}
        if len(units) != len(self.units):
            raise ValueError("Study unit references must be unique")
        for unit in self.units:
            root = units.get(unit.experimental_unit_ref)
            if root is None or root.experimental_unit_ref != root.unit_ref:
                raise ValueError("Experimental unit reference is unresolved")
            if (root.field_ref, root.crop_code, root.season_ref) != (
                unit.field_ref,
                unit.crop_code,
                unit.season_ref,
            ):
                raise ValueError("Observation and experimental units differ in context")
            seen = {unit.unit_ref}
            current = unit
            while current.parent_ref is not None:
                if current.parent_ref not in units or current.parent_ref in seen:
                    raise ValueError("Scientific unit parent is unresolved or cyclic")
                seen.add(current.parent_ref)
                current = units[current.parent_ref]
                if (current.field_ref, current.crop_code, current.season_ref) != (
                    unit.field_ref,
                    unit.crop_code,
                    unit.season_ref,
                ):
                    raise ValueError("Scientific unit parent context differs")
        return self


def require_aware(value: datetime) -> datetime:
    """科研外部事实和冻结时点必须保留时区，不推测本地时区。"""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Research timestamps must include a timezone")
    return value
