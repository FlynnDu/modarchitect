# -*- coding: utf-8 -*-
# @Time    : 2026/10/24 23:00
# @Author  : feidu
# @File    : sampling_geometry.py
"""API、模板与Worker共用采样几何结构规则，拓扑/归属由数据库验证。"""

from collections.abc import Mapping
import math
from typing import Any


class SamplingGeometryError(ValueError):
    """采样几何结构错误，不隐式修复坐标或改变空间支撑。"""


def _position(value: Any, label: str) -> list[float]:
    """有限二维经纬度，不接受布尔、第三维或超出WGS84范围的坐标。"""
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or any(
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            for item in value
        )
    ):
        raise SamplingGeometryError("%s must be a finite lon/lat position" % label)
    longitude, latitude = (float(item) for item in value)
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise SamplingGeometryError("%s is outside WGS84" % label)
    return [longitude, latitude]


def normalize_sampling_geometry(value: Any) -> dict[str, Any]:
    """规范化现行 Point、LineString、Polygon 采样几何，不接受旧字段。"""

    if not isinstance(value, Mapping):
        raise SamplingGeometryError("geometry must be a GeoJSON object")
    if set(value) != {"type", "coordinates"}:
        raise SamplingGeometryError("geometry fields differ")
    geometry_type = value.get("type")
    coordinates = value.get("coordinates")
    if geometry_type not in {"Point", "LineString", "Polygon"}:
        raise SamplingGeometryError("geometry type is not supported")
    if not isinstance(coordinates, (list, tuple)):
        raise SamplingGeometryError("geometry coordinates must be an array")
    if geometry_type == "Point":
        return {
            "type": "Point",
            "coordinates": _position(coordinates, "Point coordinates"),
        }
    if geometry_type == "LineString":
        positions = [_position(item, "LineString position") for item in coordinates]
        if len(positions) < 2 or len({tuple(item) for item in positions}) < 2:
            raise SamplingGeometryError(
                "LineString requires at least two distinct positions"
            )
        return {"type": "LineString", "coordinates": positions}

    if not coordinates:
        raise SamplingGeometryError("Polygon requires an exterior ring")
    rings: list[list[list[float]]] = []
    for raw_ring in coordinates:
        if not isinstance(raw_ring, (list, tuple)):
            raise SamplingGeometryError("Polygon ring must be an array")
        ring = [_position(item, "Polygon position") for item in raw_ring]
        if len(ring) < 4 or ring[0] != ring[-1]:
            raise SamplingGeometryError(
                "Polygon rings must be closed with at least four positions"
            )
        signed_area = sum(
            left[0] * right[1] - right[0] * left[1]
            for left, right in zip(ring, ring[1:])
        )
        if signed_area == 0:
            raise SamplingGeometryError("Polygon rings must enclose a non-zero area")
        rings.append(ring)
    return {"type": "Polygon", "coordinates": rings}
