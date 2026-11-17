# -*- coding: utf-8 -*-
# @Time    : 2026/11/05 17:31
# @Author  : feidu
# @File    : field_selection.py
"""框选用于检索已有业务地块，不创建地块、裁切科学对象或产生授权。"""

from datetime import date
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from modarchitect.contracts.model_center.components import Code, Contract, Text
from modarchitect.contracts.sampling_geometry import normalize_sampling_geometry
from .variables import StudyContext


def selection_geometry(value: dict) -> dict:
    """严格WGS84二维Polygon结构；API适配器再做不修复的拓扑检查。"""
    result = normalize_sampling_geometry(value)
    if (
        result["type"] != "Polygon"
        or sum(len(ring) for ring in result["coordinates"]) > 2000
    ):
        raise ValueError("Research field selection requires a bounded polygon")
    longitudes = [p[0] for ring in result["coordinates"] for p in ring]
    if max(longitudes) - min(longitudes) >= 180:
        raise ValueError("Research field selection cannot cross the antimeridian")
    return result


class FieldSelectionQuery(Contract):
    """没有企业/用户自报字段；实际种植季由业务系统匹配并再次核权。"""

    geometry: dict
    crop_code: Code
    season_start: date
    season_end: date

    @field_validator("geometry", mode="before")
    @classmethod
    def geometry_structure(cls, value):
        """规范化圈选请求的有界地理坐标。"""
        return selection_geometry(value)

    @model_validator(mode="after")
    def season_window(self):
        """拒绝倒序或超过支持范围的种植季。"""
        if not 0 <= (self.season_end - self.season_start).days <= 730:
            raise ValueError("Research selection season is reversed or too long")
        return self


class FieldSelectionCandidate(Contract):
    """受信业务服务确认的一个完整地块及种植季，不是圈选交集。"""

    field_name: Text
    boundary_ref: Text
    geometry: dict
    context: StudyContext

    @field_validator("geometry", mode="before")
    @classmethod
    def geometry_structure(cls, value):
        """规范化业务候选的完整地块边界。"""
        return selection_geometry(value)

    @model_validator(mode="after")
    def single_field(self):
        """确保候选只包含同一地块及其点位。"""
        field, *points = self.context.units
        if field.kind != "field_season" or any(
            point.kind != "point"
            or (point.field_ref, point.season_ref, point.crop_code)
            != (field.field_ref, field.season_ref, field.crop_code)
            for point in points
        ):
            raise ValueError(
                "Field selection requires one field and its sampling points"
            )
        return self


class SelectedResearchFields(Contract):
    """只保存选地条件和业务引用，实际点位由业务服务重新核验。"""

    selection: FieldSelectionQuery
    field_refs: Annotated[tuple[Text, ...], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def unique_fields(self):
        """保证每个所选地块只引用一次。"""
        if len(set(self.field_refs)) != len(self.field_refs):
            raise ValueError("Selected business fields must be unique")
        return self


class FieldSelectionResult(Contract):
    """候选数量有界，空集合表示没有获权匹配地块，不能生成占位地块。"""

    candidates: Annotated[tuple[FieldSelectionCandidate, ...], Field(max_length=100)]


def require_sampling_points(fields: tuple[FieldSelectionCandidate, ...]) -> None:
    """矩阵以业务系统返回的已授权点位集合表达，每个地块必须覆盖。"""
    if any(len(field.context.units) == 1 for field in fields):
        raise ValueError("Configure sampling points for each selected business field")


class StudyLaunchEvidence(Contract):
    """初始规则中冻结实际边界/版本；检索范围不替代真实地块边界。"""

    query: FieldSelectionQuery
    fields: Annotated[
        tuple[FieldSelectionCandidate, ...], Field(min_length=1, max_length=100)
    ]

    def boundary_refs(self, context: StudyContext) -> dict[str, str]:
        """按科学单位绑定不可变边界证据；不能在取数时跟随当前边界静默漂移。"""
        units = [unit for field in self.fields for unit in field.context.units]
        if (
            tuple(units) != context.units
            or any(
                (
                    field.context.project_ref,
                    field.context.season_start,
                    field.context.season_end,
                )
                != (context.project_ref, context.season_start, context.season_end)
                for field in self.fields
            )
            or (self.query.season_start, self.query.season_end)
            != (context.season_start, context.season_end)
            or any(unit.crop_code != self.query.crop_code for unit in units)
        ):
            raise ValueError("Research launch evidence differs from its context")
        return {
            unit.unit_ref: field.boundary_ref
            for field in self.fields
            for unit in field.context.units
        }
