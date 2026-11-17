# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 21:48
# @Author  : Codex
# @File    : soil.py
"""读取 SoilGrids WCS 原生单像元，保留深度、覆盖和准确单位转换。"""

from datetime import timedelta
import math
import xml.etree.ElementTree as ET

from pyproj import CRS, Transformer
from rasterio.io import MemoryFile
from rasterio.errors import RasterioError

from ..runtime.contracts import ObservationTable
from .contracts import AcquisitionRequest, SourceSnapshot, instant
from .transport import ProviderSession
from .settings import SourceSettings

NATIVE_CRS = "http://www.opengis.net/def/crs/EPSG/0/152160"
IGH = CRS.from_proj4("+proj=igh +datum=WGS84 +no_defs")
SOIL_UNITS = {
    "bdod": (100, "kg_dm3", 10),
    "cec": (10, "cmol_kg", 500),
    "cfvo": (10, "percent", 100),
    "clay": (10, "percent", 100),
    "phh2o": (10, "dimensionless", 14),
    "sand": (10, "percent", 100),
    "silt": (10, "percent", 100),
    "soc": (10, "g_kg", 1000),
    "wv0010": (1000, "fraction", 1),
    "wv0033": (1000, "fraction", 1),
    "wv1500": (1000, "fraction", 1),
}


def native_window(
    longitude: float, latitude: float, description: bytes
) -> tuple[float, float]:
    """从准确 WCS 描述确认原生网格，再定位包含声明参考点的像元。"""
    if b"<!DOCTYPE" in description.upper() or b"<!ENTITY" in description.upper():
        raise ValueError("Soil WCS description contains unsupported XML declarations")
    try:
        root = ET.fromstring(description)
        ns = {"g": "http://www.opengis.net/gml/3.2"}
        grid = root.find(".//g:RectifiedGrid", ns)
        envelope = root.find(".//g:Envelope", ns)
        origin = grid.find("g:origin/g:Point/g:pos", ns)
        offsets = [
            [float(v) for v in node.text.split()]
            for node in grid.findall("g:offsetVector", ns)
        ]
        x_origin, y_origin = [float(v) for v in origin.text.split()]
        if (
            envelope.attrib["srsName"] != NATIVE_CRS
            or envelope.attrib["axisLabels"] != "x y"
            or offsets != [[250.0, 0.0], [0.0, -250.0]]
        ):
            raise ValueError("Soil WCS grid differs from the registered native support")
        left_origin, top_origin = x_origin - 125, y_origin + 125
        x, y = Transformer.from_crs("EPSG:4326", IGH, always_xy=True).transform(
            longitude, latitude, errcheck=True
        )
        left = left_origin + math.floor((x - left_origin) / 250) * 250
        top = top_origin - math.floor((top_origin - y) / 250) * 250
        return left, top
    except (ET.ParseError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError("Soil WCS native grid metadata is invalid") from exc


def read_pixel(body: bytes, left: float, top: float) -> int:
    """核验返回形态和原生支撑；无 NoData 的零值保守拒绝而不伪装有效。"""
    try:
        with MemoryFile(body) as memory, memory.open() as dataset:
            transform = dataset.transform
            if (
                dataset.width != 1
                or dataset.height != 1
                or dataset.count != 1
                or dataset.crs is None
            ):
                raise ValueError("Soil WCS response is not a single native pixel")
            if not CRS.from_wkt(dataset.crs.to_wkt()).equals(
                IGH, ignore_axis_order=True
            ):
                raise ValueError("Soil WCS returned a different coordinate reference")
            actual = (
                transform.a,
                transform.b,
                transform.c,
                transform.d,
                transform.e,
                transform.f,
            )
            expected = (250, 0, left, 0, -250, top)
            if any(
                not math.isclose(a, b, abs_tol=1e-4, rel_tol=0)
                for a, b in zip(actual, expected, strict=True)
            ):
                raise ValueError("Soil WCS changed the native pixel transform")
            if dataset.dtypes[0] not in {"int16", "int32", "uint16"}:
                raise ValueError("Soil WCS must return mapped integer values")
            pixel = dataset.read(1, masked=True)
            if bool(pixel.mask.any()):
                raise ValueError("Soil WCS reference pixel has no data")
            value = int(pixel[0, 0])
            if value <= 0:
                raise ValueError(
                    "Soil WCS pixel is missing or has an ambiguous zero value"
                )
            return value
    except RasterioError as exc:
        raise ValueError("Soil WCS response is not a valid GeoTIFF") from exc


def normalize_soil(name: str, raw: int) -> float:
    """严格映射整数到登记单位，水量输出为比例而非百分数。"""
    if type(raw) is not int:
        raise ValueError("Soil source requires mapped integers")
    divisor, _, maximum = SOIL_UNITS[name]
    value = raw / divisor
    if value <= 0 or value > maximum:
        raise ValueError("Normalized soil reference is outside physical bounds")
    return value


class SoilGridsSource:
    """只采用 WCS，不实现暂停的 REST 或隐式其他来源回退。"""

    def __init__(self, session: ProviderSession, adapter: dict, base_url: str | None = None):
        """注入一次采集共享会话及准确实现身份。"""
        self.session, self.adapter = session, adapter
        self.base_url = base_url or SourceSettings.from_mapping({}).endpoint("MODARCHITECT_SOIL_WCS_BASE_URL")

    def _pixel(
        self, name: str, depth: str, point
    ) -> tuple[int, tuple[float, float], tuple[dict, dict]]:
        """解析该图层的准确网格并请求其原生边界，缓存只在同次采集中复用。"""
        coverage = "%s_%s_mean" % (name, depth)
        endpoint = self.base_url + "/" + name
        common = [("SERVICE", "WCS"), ("VERSION", "2.0.1")]
        description, metadata = self.session.get(
            endpoint,
            common + [("REQUEST", "DescribeCoverage"), ("COVERAGEID", coverage)],
        )
        if coverage.encode() not in description:
            raise ValueError("Soil WCS coverage identity differs")
        left, top = native_window(point.longitude, point.latitude, description)
        params = common + [
            ("REQUEST", "GetCoverage"),
            ("COVERAGEID", coverage),
            ("FORMAT", "image/tiff"),
            ("SUBSETTINGCRS", NATIVE_CRS),
            ("SUBSET", "X(%s,%s)" % (left, left + 250)),
            ("SUBSET", "Y(%s,%s)" % (top - 250, top)),
        ]
        body, evidence = self.session.get(endpoint, params)
        return read_pixel(body, left, top), (left, top), (metadata, evidence)

    def acquire(
        self, entry: dict, binding: dict, request: AcquisitionRequest
    ) -> SourceSnapshot:
        """准确土层/mean及同像元正容重门禁通过后，生成静态参考记录。"""
        name = entry["source"]["definition"]["field_code"]
        depth = binding["selectors"]["depth"]
        if binding["selectors"]["statistic"] != "mean" or name not in SOIL_UNITS:
            raise ValueError("Soil source property or statistic is not registered")
        raw, window, evidence = self._pixel(name, depth, request.reference_point)
        density, density_window, density_evidence = (
            (raw, window, evidence)
            if name == "bdod"
            else self._pixel("bdod", depth, request.reference_point)
        )
        if density_window != window:
            raise ValueError("Soil coverage gate refers to a different native pixel")
        normalize_soil("bdod", density)
        value = normalize_soil(name, raw)
        variable = entry["variable"]
        if variable["unit"] != SOIL_UNITS[name][1]:
            raise ValueError("Soil normalization differs from its exact input unit")
        top_depth, bottom_depth = [int(v) for v in depth.removesuffix("cm").split("-")]
        table = ObservationTable.model_validate(
            {
                "columns": [
                    {
                        "code": variable["code"],
                        "name": variable["name"],
                        "unit": variable["unit"],
                        "value_kind": "estimated",
                    }
                ],
                "rows": [
                    {
                        "object": request.object.model_dump(),
                        "business_date": request.start_date + timedelta(days=i),
                        "values": {variable["code"]: value},
                    }
                    for i in range((request.end_date - request.start_date).days + 1)
                ],
            }
        )
        retained = evidence if name == "bdod" else evidence + density_evidence
        return SourceSnapshot(
            binding=binding,
            adapter=self.adapter,
            request=request,
            observations=table,
            support={
                **entry["source"]["definition"]["support"],
                "requested_point": request.reference_point.model_dump(),
                "native_crs": "+proj=igh +datum=WGS84",
                "pixel_bounds": [
                    window[0],
                    window[1] - 250,
                    window[0] + 250,
                    window[1],
                ],
                "depth": {"top": top_depth, "bottom": bottom_depth, "unit": "cm"},
                "statistic": "mean",
                "independent_source_records": 1,
            },
            quality={
                "complete": True,
                "zero_policy": "reject_ambiguous",
                "coverage_gate": "same_pixel_positive_bdod",
                "information_time": "unknown",
                "usage": "static_grid_reference",
                "license": "CC BY 4.0; ISRIC SoilGrids",
            },
            acquired_at=instant(),
            evidence=retained,
        )
