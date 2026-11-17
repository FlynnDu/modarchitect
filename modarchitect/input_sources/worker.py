# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 21:56
# @Author  : Codex
# @File    : worker.py
"""由实际调度触发来源采集，只领取和回传封存任务。"""

from ..contracts.identifiers import identity_sha256
from .contracts import AcquisitionDispatch
from .service import execute_acquisition
from .transport import SourceUnavailable
from .settings import SourceSettings, environment_keys
from collections.abc import Callable

import httpx


def execute_claim(client: httpx.Client, body: AcquisitionDispatch, *, settings_factory: Callable[[frozenset[str]], SourceSettings] | None = None) -> dict:
    """调用受信内部协议，检查执行权并幂等交回完整资料。"""
    base = "/internal/v1/input-acquisitions"
    response = client.post(base + "/claim", json=body.model_dump(mode="json"))
    response.raise_for_status()
    claim = response.json()
    if claim["finished"]:
        if claim["status"] != "succeeded":
            raise ValueError("Input acquisition has already failed or been cancelled")
        return {"status": "succeeded", "replayed": True}
    endpoint = base + "/" + str(body.acquisition_id)
    attempt = {"attempt_id": claim["attempt_id"]}

    def heartbeat() -> None:
        """每项提供方访问前后核对租约及取消状态。"""
        client.post(endpoint + "/heartbeat", json=attempt).raise_for_status()

    try:
        payload = claim["input"]
        if identity_sha256(payload) != claim["input_sha256"]:
            raise ValueError("Source worker input checksum differs")
        names = environment_keys(frozenset(item["adapter"]["code"] for item in payload["items"]))
        result = execute_acquisition(payload, heartbeat, settings=settings_factory(names) if settings_factory else None)
        completion = {**attempt, "result": {"snapshots": result}}
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        httpx.HTTPError,
        SourceUnavailable,
    ) as exc:
        detail = (
            str(exc)[:500]
            if isinstance(exc, (ValueError, SourceUnavailable))
            else "Source acquisition failed (%s)" % type(exc).__name__
        )
        completion = {**attempt, "error": detail}
    for number in range(3):
        try:
            completed = client.post(endpoint + "/complete", json=completion)
            completed.raise_for_status()
            if "error" in completion:
                raise ValueError(completion["error"])
            return {"status": "succeeded", "acquisition_id": str(body.acquisition_id)}
        except httpx.TransportError:
            if number == 2:
                raise
    raise SourceUnavailable("Source result acknowledgement is unavailable")
