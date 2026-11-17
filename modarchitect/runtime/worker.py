# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 21:35
# @Author  : Codex
# @File    : worker.py
"""由 DolphinScheduler 调用的独立研究 Worker，只执行封存任务。"""

import os
from threading import BoundedSemaphore
from datetime import datetime
from secrets import compare_digest

from fastapi import FastAPI, HTTPException, Header
import httpx

from ..contracts.identifiers import identity_sha256
from .containers import ContainerRunner
from .contracts import DispatchRequest
from .executor import execute
from .service import profiles
from ..input_sources.contracts import AcquisitionDispatch
from ..input_sources.worker import execute_claim as acquire_sources
from ..contracts.model_center.components import Contract
from ..report_tasks.contracts import DailyTick, SHANGHAI
from .source_environment import source_settings

app = FastAPI(title="modarchitect research worker")
capacity = BoundedSemaphore(2)


def api_client() -> httpx.Client:
    """只向部署指定的研究 API 提交内部身份。"""
    return httpx.Client(
        base_url=os.environ["MODARCHITECT_INTERNAL_API"].rstrip("/"),
        headers={"X-Research-Worker-Key": os.environ["MODARCHITECT_WORKER_KEY"]},
        timeout=20,
    )


@app.get("/health")
def health() -> dict:
    """用于独立 Worker 服务的存活检查。"""
    return {"status": "ok"}


@app.post("/acquire")
def acquire(body: AcquisitionDispatch) -> dict:
    """采集有独立身份和入口，计算组件继续使用封存输入。"""
    if not capacity.acquire(timeout=120):
        raise HTTPException(503, "Source worker is at capacity")
    try:
        with api_client() as client:
            return acquire_sources(client, body, settings_factory=source_settings)
    finally:
        capacity.release()


class DailyDispatch(Contract):
    """接收海豚内置的逻辑时刻，不在Worker用当前时间替代。"""

    trigger_date: str
    scheduler_id: str


@app.post("/report-tick")
def report_tick(body: DailyDispatch, x_daily_trigger_key: str = Header(default="")) -> dict:
    """独立日触发凭据仅授予固定回调，不暴露通用研究Worker凭据。"""
    expected = os.getenv("MODARCHITECT_DAILY_TRIGGER_KEY", "")
    if len(expected) < 32 or not compare_digest(expected, x_daily_trigger_key):
        raise HTTPException(401, "Daily trigger authentication is required")
    try:
        if len(body.trigger_date) != 8 or not body.trigger_date.isdigit():
            raise ValueError("Invalid scheduler business date")
        logical = datetime.strptime(body.trigger_date, "%Y%m%d").replace(hour=2, tzinfo=SHANGHAI)
        tick = DailyTick(scheduled_at=logical, scheduler_id=body.scheduler_id)
    except ValueError as exc:
        raise HTTPException(422, "Daily trigger logical time is invalid") from exc
    with api_client() as client:
        created = 0
        while True:
            response = client.post("/internal/v1/report-tasks/tick", json=tick.model_dump(mode="json"))
            response.raise_for_status()
            result = response.json()
            created += result["created"]
            if not result.get("has_more"):
                return {"created": created}


@app.post("/execute")
def run(body: DispatchRequest) -> dict:
    """真实计算结束后才回复调度器，重复投递由服务端领取规则处理。"""
    if not capacity.acquire(timeout=120):
        raise HTTPException(503, "Research worker is at capacity")
    try:
        return execute_claim(body)
    finally:
        capacity.release()


def execute_claim(body: DispatchRequest) -> dict:
    """验证输入与制品，续租、执行并幂等提交当次结果。"""
    with api_client() as client:
        response = client.post(
            "/internal/v1/research/claim", json=body.model_dump(mode="json")
        )
        if response.status_code == 409:
            raise HTTPException(409, "The research run already has an active attempt")
        response.raise_for_status()
        claim = response.json()
        if claim["finished"]:
            if claim["status"] != "succeeded":
                raise HTTPException(409, "The research run has already failed")
            return {"status": "succeeded", "replayed": True}
        attempt = {"attempt_id": claim["attempt_id"]}
        endpoint = "/internal/v1/research/runs/" + str(body.run_id)

        def heartbeat() -> None:
            """每个节点开始前检查执行权并延长租约。"""
            client.post(endpoint + "/heartbeat", json=attempt).raise_for_status()

        runner = ContainerRunner()
        try:
            payload = claim["input"]
            if identity_sha256(payload) != claim["input_sha256"]:
                raise ValueError("Worker input checksum differs")
            registered = profiles()
            if any(
                registered.get(key) != spec for key, spec in payload["profiles"].items()
            ):
                raise ValueError(
                    "Worker execution artifacts differ from the frozen registry"
                )
            result = execute(payload, runner, heartbeat)
            completion = {**attempt, "result": result}
        except (ValueError, KeyError, TypeError, OSError, httpx.HTTPError) as exc:
            detail = (
                str(exc)[:500]
                if isinstance(exc, ValueError)
                else "Research component execution failed (%s)" % type(exc).__name__
            )
            completion = {**attempt, "error": detail}
        finally:
            runner.close()
        completed = None
        for _ in range(3):
            try:
                completed = client.post(endpoint + "/complete", json=completion)
                completed.raise_for_status()
                break
            except httpx.TransportError:
                continue
        if completed is None:
            raise HTTPException(503, "Research result acknowledgement is unavailable")
        if "error" in completion:
            raise HTTPException(422, completion["error"])
        return {
            "status": "succeeded",
            "run_id": str(body.run_id),
            "result_sha256": completed.json()["result_sha256"],
        }
