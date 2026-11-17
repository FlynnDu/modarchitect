# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 21:56
# @Author  : Codex
# @File    : routes.py
"""独立采集与来源快照的最小 HTTP 协议，复用工作区和 Worker 身份。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from ..runtime.routes import Owner, RequestKey, DispatchResult, worker_key
from ..runtime.contracts import Attempt, Completion
from .contracts import AcquisitionRequest, AcquisitionDispatch, SourceSnapshot
from .service import InputAcquisition

workspace = APIRouter(prefix="/api/v1/workspace", tags=["研究输入采集"])
internal = APIRouter(
    prefix="/internal/v1/input-acquisitions", dependencies=[Depends(worker_key)]
)


def acquisition_service(request: Request) -> InputAcquisition:
    """数据库缺配置时不提供持久采集接口。"""
    value = request.app.state.input_acquisition
    if value is None:
        raise HTTPException(503, "Input acquisition persistence is not configured")
    return value


Service = Annotated[InputAcquisition, Depends(acquisition_service)]


@workspace.post("/plans/{design_id}/input-acquisitions", status_code=202)
def create(
    design_id: UUID,
    body: AcquisitionRequest,
    owner: Owner,
    service: Service,
    key: RequestKey,
) -> dict:
    """封存准确来源需求，实际访问提供方由海豚调度采集 Worker。"""
    row = service.create(owner, design_id, body, key)
    return {"acquisition_id": row["acquisition_id"]}


@workspace.get("/input-acquisitions/{identity}")
def read(identity: UUID, owner: Owner, service: Service) -> dict:
    """返回实际采集状态、准确快照引用和必要失败原因。"""
    row = service.store.read(owner, identity)
    return {k: row[k] for k in ("status", "snapshot_ids", "error")}


@workspace.post("/input-acquisitions/{identity}/cancel")
def cancel(identity: UUID, owner: Owner, service: Service) -> dict:
    """撤销该采集的结果发布权，不把取消请求显示成进程已停止。"""
    row = service.store.cancel(owner, identity)
    return {"status": row["status"]}


@workspace.get("/input-snapshots/{identity}")
def snapshot(identity: UUID, owner: Owner, service: Service) -> dict:
    """读取可用于装配的标准记录与必要科学支撑，不混入原始大制品。"""
    raw = service.store.read_snapshot(owner, identity)["snapshot"]
    value = SourceSnapshot.model_validate(raw)
    return {
        "observations": value.observations.sealed(),
        "support": value.support,
        "quality": value.quality,
    }


@workspace.get("/input-snapshots/{identity}/evidence")
def evidence(identity: UUID, owner: Owner, service: Service) -> dict:
    """需要追溯时按权限读取原始证据及准确快照摘要。"""
    row = service.store.read_snapshot(owner, identity)
    return {"sha256": row["sha256"], "snapshot": row["snapshot"]}


@internal.post("/dispatch/next")
def next_dispatch(service: Service) -> dict:
    """实际投递任务独立于研究计算的队列。"""
    return {"job": service.store.next_dispatch()}


@internal.post("/{identity}/dispatch")
def dispatched(identity: UUID, body: DispatchResult, service: Service) -> dict:
    """登记真实海豚回执或等待对账。"""
    service.store.dispatch_result(identity, body.scheduler_id, body.error)
    return {"accepted": True}


@internal.post("/claim")
def claim(body: AcquisitionDispatch, service: Service) -> dict:
    """采集 Worker 领取封存载荷和唯一执行权。"""
    return service.store.claim(body.acquisition_id, body.dispatch_token)


@internal.post("/{identity}/heartbeat")
def heartbeat(identity: UUID, body: Attempt, service: Service) -> dict:
    """有界网络访问间隔检查执行权并续租。"""
    service.store.heartbeat(identity, body.attempt_id)
    return {"accepted": True}


@internal.post("/{identity}/complete")
def complete(identity: UUID, body: Completion, service: Service) -> dict:
    """回传准确资料或明确失败，不能调用普通用户上传入口冒充。"""
    return service.store.complete(identity, body.attempt_id, body.result, body.error)
