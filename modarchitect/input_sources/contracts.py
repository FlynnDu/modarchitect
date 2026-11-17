# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 21:44
# @Author  : Codex
# @File    : contracts.py
"""定义采集范围、不可变来源快照及与研究数据的准确匹配规则。"""

from datetime import date, datetime, timezone
import base64
from hashlib import sha256
from importlib.resources import files
from importlib.metadata import version
import json
import sys
from typing import Annotated, Literal, Protocol
from uuid import UUID

from pydantic import Field, model_validator

from ..contracts.identifiers import identity_sha256
from ..contracts.model_center.components import Code, Contract
from ..runtime.contracts import ObjectReference, ObservationTable


class ReferencePoint(Contract):
    """工作区声明的 WGS84 参考位置，不赋予企业地块资格。"""

    latitude: Annotated[float, Field(strict=True, ge=-90, le=90, allow_inf_nan=False)]
    longitude: Annotated[
        float, Field(strict=True, ge=-180, le=180, allow_inf_nan=False)
    ]


class AcquisitionRequest(Contract):
    """从准确草稿解析来源，只允许选择需求子集和自有研究范围。"""

    expected_revision: Annotated[int, Field(strict=True, ge=1)]
    object: ObjectReference
    reference_point: ReferencePoint
    start_date: date
    end_date: date
    requirements: Annotated[tuple[Code, ...], Field(max_length=256)] = ()

    @model_validator(mode="after")
    def valid_window(self):
        """限制一次采集预算，拒绝倒序、重复需求及未来历史查询。"""
        if not 0 <= (self.end_date - self.start_date).days < 366:
            raise ValueError("Acquisition range must contain between 1 and 366 days")
        if len(set(self.requirements)) != len(self.requirements):
            raise ValueError("Acquisition requirements must be unique")
        return self


class SourceSnapshot(Contract):
    """固定源绑定、标准记录和可复跑原始证据；只由可信采集回传。"""

    format: Literal["source_snapshot_v1"] = "source_snapshot_v1"
    binding: dict
    adapter: dict
    request: AcquisitionRequest
    observations: ObservationTable
    support: dict
    quality: dict
    acquired_at: datetime
    evidence: Annotated[tuple[dict, ...], Field(min_length=1, max_length=4)]

    @model_validator(mode="after")
    def aware_acquisition(self):
        """获取时间必须带时区，不冒充提供方的历史可用时刻。"""
        if self.acquired_at.utcoffset() is None:
            raise ValueError("Source acquisition time requires a timezone")
        return self


class SourceAdapter(Protocol):
    """厂商实现通过同一小接口取得资料，不承担研究训练或数据采用。"""

    def acquire(
        self, entry: dict, binding: dict, request: AcquisitionRequest
    ) -> SourceSnapshot:
        """读取固定来源并返回标准记录及原文，缺失或不相容时明确失败。"""
        ...


class AcquisitionDispatch(Contract):
    """调度仅传准确采集身份与单任务凭据。"""

    acquisition_id: UUID
    dispatch_token: Annotated[str, Field(min_length=32, max_length=128)]


def validate_co_observations(snapshots: list[SourceSnapshot], table: dict) -> None:
    """同一影像产品的波段必须来自相同对象日期的准确场景及网格，跨采集也核验。"""
    selected = {(identity_sha256(row["object"]), row["business_date"]) for row in table["rows"]}
    signatures = {}
    for snapshot in snapshots:
        if snapshot.support.get("temporal_support") != "scene_observation":
            continue
        group = snapshot.binding["source_system"]
        records = {record["business_date"]: record for record in snapshot.support["scene_records"]}
        for row in snapshot.observations.model_dump(mode="json")["rows"]:
            key = identity_sha256(row["object"]), row["business_date"]
            if key not in selected:
                continue
            record = {name: value for name,value in records[row["business_date"]].items() if name != "catalog_candidate"}
            signature = identity_sha256({"point": snapshot.support["requested_point"], "grid": snapshot.support["grid"], "scene": record})
            grouped = (group, *key)
            if grouped in signatures and signatures[grouped] != signature:
                raise ValueError("Co-observed bands require the same actual scene and reference grid")
            signatures[grouped] = signature


def match_snapshot(
    snapshot: SourceSnapshot, requirement: dict, table: dict, code: str
) -> None:
    """逐值核验实际来源，允许准确子集，不允许上传数值冒充或跨对象复用。"""
    if snapshot.binding != requirement["catalog_binding"]:
        raise ValueError("Source snapshot binding differs: %s" % code)
    source = snapshot.observations.model_dump(mode="json")
    columns = {c["code"]: c for c in source["columns"]}
    actual = next(c for c in table["columns"] if c["code"] == code)
    if columns.get(code) != actual:
        raise ValueError("Source snapshot column differs: %s" % code)
    values = {
        (identity_sha256(r["object"]), r["business_date"]): r["values"][code]
        for r in source["rows"]
    }
    for row in table["rows"]:
        key = (identity_sha256(row["object"]), row["business_date"])
        if key not in values or values[key] != row["values"][code]:
            raise ValueError("Source snapshot record or value differs: %s" % code)


def match_snapshots(
    snapshots: list[SourceSnapshot], requirement: dict, table: dict, code: str
) -> None:
    """多个快照按完整对象和日期提供唯一覆盖；重叠、缺口和未使用证据均拒绝。"""
    if not snapshots:
        raise ValueError("Input data channel requires authorized source snapshots: %s" % code)
    actual = next(c for c in table["columns"] if c["code"] == code)
    indexed = {}
    for index, snapshot in enumerate(snapshots):
        if snapshot.binding != requirement["catalog_binding"]:
            raise ValueError("Source snapshot binding differs: %s" % code)
        source = snapshot.observations.model_dump(mode="json")
        column = next((c for c in source["columns"] if c["code"] == code), None)
        if column != actual:
            raise ValueError("Source snapshot column differs: %s" % code)
        for row in source["rows"]:
            key = (identity_sha256(row["object"]), row["business_date"])
            if key in indexed:
                raise ValueError("Source snapshots overlap: %s" % code)
            indexed[key] = (index, row["values"][code])
    used = set()
    for row in table["rows"]:
        key = (identity_sha256(row["object"]), row["business_date"])
        value = indexed.get(key)
        if value is None or value[1] != row["values"][code]:
            raise ValueError("Source snapshot record or value differs: %s" % code)
        used.add(value[0])
    if used != set(range(len(snapshots))):
        raise ValueError("Source snapshots contain unused evidence: %s" % code)


def instant() -> datetime:
    """统一采用 UTC 获取时刻。"""
    return datetime.now(timezone.utc)


def source_registration(binding: dict) -> str | None:
    """只接受登记的准确来源；厂商替换通过追加登记而非研究流程分支。"""
    resource = files("modarchitect.contracts").joinpath("source-adapters-v1.json")
    envelope = json.loads(resource.read_text(encoding="utf-8"))
    if identity_sha256(envelope["payload"]) != envelope["sha256"]:
        raise ValueError("Source adapter registry checksum differs")
    identity = {
        key: binding[key]
        for key in ("kind", "code", "definition_version", "contract_sha256")
    }
    matches = [
        r["adapter"]
        for r in envelope["payload"]["bindings"]
        if r["binding"] == identity
    ]
    if len(matches) > 1:
        raise ValueError("Source adapter registration is ambiguous")
    return matches[0] if matches else None


def adapter_identity(code: str) -> dict:
    """获取与转换的准确实现摘要随任务封存，不接受客户端指定执行代码。"""
    modules = {"openmeteo_archive": "weather.py", "soilgrids_wcs": "soil.py", "sentinelhub_s2_l2a": "sentinel.py"}
    if code not in modules:
        raise ValueError("Source adapter is not installed")
    resources = files("modarchitect.input_sources")
    content = {
        name: sha256(resources.joinpath(name).read_bytes()).hexdigest()
        for name in (modules[code], "contracts.py", "transport.py")
    }
    if code == "sentinelhub_s2_l2a":
        content["sentinel_scene.py"] = sha256(resources.joinpath("sentinel_scene.py").read_bytes()).hexdigest()
    content["settings.py"] = sha256(resources.joinpath("settings.py").read_bytes()).hexdigest()
    content["provider_settings"] = sha256(files("modarchitect.contracts").joinpath("source-provider-settings-v1.json").read_bytes()).hexdigest()
    dependencies = {
        name: version(name) for name in ("httpx", "pydantic", "pyproj", "rasterio")
    }
    runtime = {
        "python": ".".join(str(v) for v in sys.version_info[:3]),
        "dependencies": dependencies,
    }
    return {
        "code": code,
        "version": "1.0.0",
        "sha256": identity_sha256({"files": content, "runtime": runtime}),
        "runtime": runtime,
    }


def validate_snapshot(
    snapshot: SourceSnapshot, item: dict, request: AcquisitionRequest
) -> None:
    """在可信回传边界核对来源、对象、日期、质量及原始制品摘要。"""
    entry, binding = item["entry"], item["binding"]
    if (
        snapshot.binding != binding
        or snapshot.adapter != item["adapter"]
        or snapshot.request != request
    ):
        raise ValueError("Source snapshot identity differs from the sealed acquisition")
    expected_support = entry["source"]["definition"]["support"]
    if (
        snapshot.quality.get("complete") is not True
        or any(
            snapshot.support.get(k) != value for k, value in expected_support.items()
        )
        or snapshot.support.get("requested_point")
        != request.reference_point.model_dump()
    ):
        raise ValueError("Source snapshot support or quality is incomplete")
    variable = entry["variable"]
    columns = snapshot.observations.columns
    if len(columns) != 1 or columns[0].model_dump() != {
        "code": variable["code"],
        "name": variable["name"],
        "unit": variable["unit"],
        "value_kind": "estimated",
    }:
        raise ValueError("Source snapshot columns differ from the exact source")
    expected = (request.end_date - request.start_date).days + 1
    scene_dates = expected_support.get("temporal_support") == "scene_observation"
    count = len(snapshot.observations.rows)
    if (not scene_dates and count != expected) or (scene_dates and not 1 <= count <= expected):
        raise ValueError("Source snapshot date coverage is incomplete")
    dates = set()
    for row in snapshot.observations.rows:
        if (
            row.object != request.object
            or not request.start_date <= row.business_date <= request.end_date
        ):
            raise ValueError("Source snapshot object or date range differs")
        dates.add(row.business_date)
    if len(dates) != (count if scene_dates else expected):
        raise ValueError("Source snapshot dates are not unique")
    if scene_dates:
        records = snapshot.support.get("scene_records", [])
        if snapshot.quality.get("coverage") != "actual_clear_scene_dates" or {r.get("business_date") for r in records} != {day.isoformat() for day in dates} or len(records) != count:
            raise ValueError("Sentinel sparse dates require exact scene evidence")
    for evidence in snapshot.evidence:
        try:
            raw = base64.b64decode(evidence["body_base64"], validate=True)
            if len(raw) > 2_000_000 or sha256(raw).hexdigest() != evidence["sha256"]:
                raise ValueError("Source evidence checksum differs")
        except (KeyError, TypeError) as exc:
            raise ValueError("Source evidence is incomplete") from exc
