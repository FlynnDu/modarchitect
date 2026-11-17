# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 16:20
# @Author  : Codex
# @File    : sentinel_scene.py
"""核验卫星参考网格、单景元数据和原始质量，不在取数中计算NDVI。"""

from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import math
import tarfile

from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.errors import RasterioError


class SceneNotUsable(ValueError):
    """真实场景存在但该参考像元没有合格观测，不能补零。"""


def timestamp(value: str) -> datetime:
    """采集时间必须带明确时区，不以UTC日期截断替代上海业务日。"""
    if not isinstance(value, str):
        raise ValueError("Sentinel acquisition timestamp must be a string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() is None:
        raise ValueError("Sentinel acquisition timestamp requires a timezone")
    return result.astimezone(timezone.utc)


def reference_grid(longitude: float, latitude: float) -> dict:
    """构造包含参考点的10m UTM对齐请求网格，明确它不等于地块均值。"""
    if not -80 <= latitude <= 84:
        raise ValueError("Sentinel reference point is outside the UTM coverage")
    zone = min(60, int(math.floor((longitude+180)/6))+1)
    epsg = (32600 if latitude >= 0 else 32700)+zone
    x, y = Transformer.from_crs(4326, epsg, always_xy=True).transform(longitude, latitude, errcheck=True)
    left, bottom = math.floor(x/10)*10, math.floor(y/10)*10
    return {"epsg": epsg, "bbox": [left, bottom, left+10, bottom+10], "resolution_m": 10,
            "spatial_support": "resampled_reference_grid", "resampling": "NEAREST", "scl_native_resolution_m": 20}


def decode_scene(raw: bytes, grid: dict, acquired_at: datetime) -> dict:
    """只读两个有界常规tar成员，核对实际场景、网格及SCL/dataMask。"""
    try:
        with tarfile.open(fileobj=BytesIO(raw), mode="r:*") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            raster_names = [name for name in names if name in {"bands.tif", "bands.tiff"}]
            if len(members) != 2 or len(raster_names) != 1 or "userdata.json" not in names or len(set(names)) != 2:
                raise ValueError("Sentinel Process response members differ")
            content = {}
            for member in members:
                if not member.isfile() or not 0 < member.size <= 1_000_000:
                    raise ValueError("Sentinel Process member exceeds its resource contract")
                stream = archive.extractfile(member)
                content[member.name] = stream.read(member.size+1)
                if len(content[member.name]) != member.size:
                    raise ValueError("Sentinel Process member is truncated")
        metadata = json.loads(content["userdata.json"])
        scenes = metadata["scenes"]
        if not isinstance(scenes, list) or len(scenes) != 1:
            raise SceneNotUsable("ambiguous_or_missing_single_scene")
        scene = scenes[0]
        actual_time = timestamp(scene["date"])
        if abs(actual_time-acquired_at) > timedelta(seconds=1):
            raise ValueError("Sentinel Process acquisition differs from its Catalog time")
        identifier = scene.get("shId")
        valid_identifier = type(identifier) is int and identifier > 0 or isinstance(identifier, str) and 0 < len(identifier) <= 4096
        if not valid_identifier or not isinstance(scene.get("dataPath"), str) or not 0 < len(scene["dataPath"]) <= 4096 or not isinstance(metadata.get("serviceVersion"), str) or not metadata["serviceVersion"]:
            raise ValueError("Sentinel Process actual scene evidence is incomplete")
        with MemoryFile(content[raster_names[0]]) as memory, memory.open() as raster:
            left, bottom, right, top = grid["bbox"]
            transform = raster.transform
            if (raster.width, raster.height, raster.count) != (1, 1, 4) or raster.crs is None or raster.crs.to_epsg() != grid["epsg"] or raster.dtypes != ("float32",)*4 or tuple(transform)[:6] != (10.0, 0.0, left, 0.0, -10.0, top) or tuple(raster.bounds) != (left, bottom, right, top):
                raise ValueError("Sentinel Process grid, bands or encoding differ")
            red, nir, scl, mask = [float(value) for value in raster.read()[:,0,0]]
        if not all(math.isfinite(value) for value in (red, nir, scl, mask)):
            raise SceneNotUsable("nonfinite_reference_pixel")
        if mask != 1 or scl not in {4,5}:
            raise SceneNotUsable("cloud_shadow_or_missing_reference_pixel")
        if red < 0 or nir < 0:
            raise SceneNotUsable("negative_harmonized_reflectance")
        return {"acquired_at": actual_time.isoformat(), "bands": {"B04": red, "B08": nir},
                "scl": int(scl), "data_mask": 1, "scene": scene, "service_version": metadata["serviceVersion"]}
    except (tarfile.TarError, OSError, RasterioError, KeyError, TypeError, UnicodeError) as exc:
        raise ValueError("Sentinel Process response cannot be verified") from exc
