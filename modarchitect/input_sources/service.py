# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 21:50
# @Author  : Codex
# @File    : service.py
"""将准确来源采集编排为有界适配调用，不承担研究模型计算。"""

from collections.abc import Callable
from datetime import date, timedelta
import os
from typing import TYPE_CHECKING
from uuid import UUID

import httpx

from ..system_inputs import (
    resolve_input,
    validate_input_bindings,
    validate_input_adoption,
)
from ..contracts.enterprise.identity import VerifiedPrincipal
from ..contracts.identifiers import identity_sha256
from ..designs import ResearchDesigns
from .contracts import (
    AcquisitionRequest,
    SourceSnapshot,
    SourceAdapter,
    adapter_identity,
    source_registration,
    validate_snapshot,
)
from .soil import SoilGridsSource
from .weather import OpenMeteoSource
from .transport import ProviderSession
from .settings import SourceSettings
from .sentinel import SentinelHubSource

if TYPE_CHECKING:
    from ..persistence.source_store import SourceStore


class InputAcquisition:
    """API 应用流程复用草稿身份和独立采集持久化，不在请求内访问提供方。"""

    def __init__(self, designs: ResearchDesigns, store: "SourceStore"):
        """注入已有方案服务和受权存储。"""
        self.designs, self.store = designs, store

    def create(
        self,
        owner: VerifiedPrincipal,
        design_id: UUID,
        body: AcquisitionRequest,
        key: str,
    ) -> dict:
        """校验准确修订后封存取数需求，重复请求优先返回原采集。"""
        request_sha = identity_sha256(body.model_dump(mode="json"))
        previous = self.store.replay(owner, design_id, key, request_sha)
        if previous is not None:
            return previous
        draft = self.designs.read(owner, design_id)
        if draft["revision"] != body.expected_revision:
            from ..persistence.design_store import DesignConflict

            raise DesignConflict("Research draft revision has changed")
        payload = prepare_acquisition(
            draft["configuration"]["definition"],
            body,
            retained_definition=draft["configuration"]["definition"],
        )
        payload["definition_sha256"] = identity_sha256(
            draft["configuration"]["definition"]
        )
        return self.store.enqueue(owner, design_id, key, request_sha, payload)


def prepare_acquisition(
    definition: dict,
    request: AcquisitionRequest,
    *,
    retained_definition: dict | None = None,
) -> dict:
    """从准确定义选取需求并冻结接入制品，未知或未接通来源不得入队。"""
    validate_input_bindings(definition, require_catalog=True)
    validate_input_adoption(definition, retained_definition)
    requirements = {
        r["code"]: r
        for r in definition["collection_requirements"]
        if r.get("source") == "third_party"
    }
    chosen = request.requirements or tuple(requirements)
    if not chosen or not set(chosen) <= set(requirements):
        raise ValueError("Acquisition requires declared third-party inputs")
    items = []
    for code in chosen:
        binding = requirements[code]["catalog_binding"]
        entry = resolve_input(binding, requirements[code]["method"])
        adapter = source_registration(binding)
        if adapter is None or entry["unit_kind"] != "field_season":
            raise ValueError("No adopted source adapter supports this input")
        items.append(
            {
                "requirement": code,
                "entry": entry,
                "binding": binding,
                "adapter": adapter_identity(adapter),
            }
        )
    maximum = min(366, *(item["entry"]["source"]["definition"].get("acquisition", {}).get("maximum_days", 366) for item in items))
    if (request.end_date-request.start_date).days >= maximum:
        raise ValueError("Acquisition range exceeds the registered source limit: %s days" % maximum)
    return {
        "format": "input_acquisition_v1",
        "request": request.model_dump(mode="json"),
        "items": items,
    }


def acquisition_windows(definition: dict, requirements: tuple[str, ...], start: date, end: date) -> list[tuple[date, date]]:
    """按所选准确来源的最小请求上限分段，日窗口不重叠也不遗漏。"""
    limits = [366]
    for requirement in definition["collection_requirements"]:
        if requirement["code"] in requirements:
            entry = resolve_input(requirement["catalog_binding"], requirement["method"])
            limits.append(entry["source"]["definition"].get("acquisition", {}).get("maximum_days", 366))
    maximum = min(limits)
    windows = []
    while start <= end:
        last = min(end, start+timedelta(days=maximum-1))
        windows.append((start, last))
        start = last+timedelta(days=1)
    return windows


def execute_acquisition(
    payload: dict,
    heartbeat: Callable[[], None],
    *,
    transport: httpx.BaseTransport | None = None,
    settings: SourceSettings | None = None,
) -> list[dict]:
    """执行真实采集；完整批次失败不伪造部分就绪，已有成功资源不受影响。"""
    request = AcquisitionRequest.model_validate(payload["request"])
    settings = settings if settings is not None else SourceSettings.from_mapping(os.environ)
    session = ProviderSession(transport, heartbeat=heartbeat)
    try:
        registry: dict[str, SourceAdapter] = {
            "openmeteo_archive": OpenMeteoSource(
                session,
                adapter_identity("openmeteo_archive"),
                settings.get("MODARCHITECT_OPENMETEO_KEY"),
                settings.get("MODARCHITECT_WEATHER_ACCESS"),
                {"archive": settings.endpoint("MODARCHITECT_OPENMETEO_ARCHIVE_URL"),
                 "customer": settings.endpoint("MODARCHITECT_OPENMETEO_CUSTOMER_ARCHIVE_URL")},
            ),
            "soilgrids_wcs": SoilGridsSource(
                session, adapter_identity("soilgrids_wcs"), settings.endpoint("MODARCHITECT_SOIL_WCS_BASE_URL")
            ),
            "sentinelhub_s2_l2a": SentinelHubSource(session, adapter_identity("sentinelhub_s2_l2a"), settings),
        }
        snapshots = []
        for item in payload["items"]:
            heartbeat()
            identity = item["adapter"]
            if identity != adapter_identity(identity["code"]):
                raise ValueError(
                    "Installed source adapter differs from the sealed acquisition"
                )
            if source_registration(item["binding"]) != identity["code"]:
                raise ValueError(
                    "Source adapter adoption differs from the sealed acquisition"
                )
            snapshot = registry[identity["code"]].acquire(
                item["entry"], item["binding"], request
            )
            validate_snapshot(snapshot, item, request)
            snapshots.append(snapshot.model_dump(mode="json"))
        heartbeat()
        return snapshots
    finally:
        session.close()


def validate_acquisition_result(
    payload: dict, result: list[dict]
) -> list[SourceSnapshot]:
    """回传必须逐项对应封存需求，禁止多送、漏送或替换准确制品。"""
    request = AcquisitionRequest.model_validate(payload["request"])
    if not isinstance(result, list) or len(result) != len(payload["items"]):
        raise ValueError("Acquisition results differ from the sealed requirements")
    snapshots = [SourceSnapshot.model_validate(raw) for raw in result]
    for snapshot, item in zip(snapshots, payload["items"], strict=True):
        validate_snapshot(snapshot, item, request)
    return snapshots
