# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 13:54
# @Author  : Codex
# @File    : routes.py
"""面向业务系统、工作区和可信调度器的持续报告协议。"""

from typing import Annotated
from uuid import UUID
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..contracts.model_center.components import Code
from ..persistence.report_store import task_view
from ..routes import Principal, RequestKey, PublishDraft, require_key
from ..runtime.contracts import ObservationTable
from ..runtime.routes import Owner, worker_key
from .contracts import (
    BusinessReportStart,
    DailyTick,
    ReportStateChange,
    WorkspaceReportStart,
)
from .service import ReportTasks

workspace = APIRouter(prefix="/api/v1/workspace", tags=["持续研究报告"])
business = APIRouter(
    prefix="/api/v1/research",
    tags=["业务持续报告"],
    dependencies=[Depends(require_key)],
)
internal = APIRouter(
    prefix="/internal/v1/report-tasks", dependencies=[Depends(worker_key)]
)


def service(request: Request) -> ReportTasks:
    """没有独立数据库时明确关闭持续任务写入。"""
    value = request.app.state.report_tasks
    if value is None:
        raise HTTPException(503, "Report task persistence is not configured")
    return value


Service = Annotated[ReportTasks, Depends(service)]


@workspace.post("/plans/{design_id}/publish")
def publish(
    design_id: UUID, body: PublishDraft, owner: Owner, service: Service
) -> dict:
    """启用前固定方案修订，与单次运行使用同一发布约束。"""
    return service.runtime.designs.publish(owner, design_id, body.expected_revision)


@workspace.post("/report-tasks", status_code=202)
def start_workspace(
    body: WorkspaceReportStart, owner: Owner, service: Service, key: RequestKey
) -> dict:
    """按准确方案版本启用自有对象的每日任务。"""
    return service.launch(owner, body, key)


@business.post("/report-tasks", status_code=202)
def start_business(
    body: BusinessReportStart, owner: Principal, service: Service, key: RequestKey
) -> dict:
    """由可信业务身份和在线选地证据启用每日报告。"""
    return service.launch(owner, body, key)


@workspace.get("/report-tasks")
def workspace_list(owner: Owner, service: Service) -> dict:
    """只列本工作区任务，不把平台全部研究混入列表。"""
    return {"items": service.store.list_tasks(owner)}


@business.get("/report-tasks")
def business_list(owner: Principal, service: Service) -> dict:
    """复用企业授权及行级隔离。"""
    return {"items": service.store.list_tasks(owner)}


@workspace.get("/report-tasks/{task_id}")
def workspace_read(task_id: UUID, owner: Owner, service: Service) -> dict:
    """读取计划事实，详细执行证据由批次接口读取。"""
    row = service.store.read(owner, task_id)
    return {
        **task_view(row),
        "objects": row["settings_json"]["objects"],
        "model_id": row["settings_json"]["model_id"],
    }


@business.get("/report-tasks/{task_id}")
def business_read(task_id: UUID, owner: Principal, service: Service) -> dict:
    """业务系统只能访问本主体受权计划。"""
    row = service.store.read(owner, task_id)
    return {
        **task_view(row),
        "objects": row["settings_json"]["objects"],
        "model_id": row["settings_json"]["model_id"],
    }


@workspace.get("/report-batches/{batch_id}/observation-template")
def workspace_template(batch_id: UUID, owner: Owner, service: Service) -> dict:
    """下载本批次人工记录模板，不允许代填天气或土壤平台列。"""
    return service.manual_template(owner, batch_id)


@business.get("/report-batches/{batch_id}/observation-template")
def business_template(batch_id: UUID, owner: Principal, service: Service) -> dict:
    """平台业务系统可读取相同准确人工观测合同。"""
    return service.manual_template(owner, batch_id)


@workspace.get("/report-tasks/{task_id}/batches")
def workspace_batches(
    task_id: UUID, owner: Owner, service: Service, page: Annotated[int, Query(ge=1)] = 1
) -> dict:
    """按观察日分页查看成功和缺资料批次。"""
    return {"items": service.store.list_batches(owner, task_id, page)}


@business.get("/report-tasks/{task_id}/batches")
def business_batches(
    task_id: UUID,
    owner: Principal,
    service: Service,
    page: Annotated[int, Query(ge=1)] = 1,
) -> dict:
    """平台可回查每次任务输入与成果的准确身份。"""
    return {"items": service.store.list_batches(owner, task_id, page)}


@workspace.post("/report-tasks/{task_id}/pause")
def workspace_pause(
    task_id: UUID, body: ReportStateChange, owner: Owner, service: Service
) -> dict:
    """暂停后续执行，不删除历史结果。"""
    return service.store.change_state(owner, task_id, body.expected_revision, False)


@business.post("/report-tasks/{task_id}/pause")
def business_pause(
    task_id: UUID, body: ReportStateChange, owner: Principal, service: Service
) -> dict:
    """业务暂停遵循同一修订和执行权约束。"""
    return service.store.change_state(owner, task_id, body.expected_revision, False)


@workspace.post("/report-tasks/{task_id}/resume")
def workspace_resume(
    task_id: UUID, body: ReportStateChange, owner: Owner, service: Service
) -> dict:
    """恢复前重新核验真实日计划，已存在日期批次不重复建立。"""
    task = service.store.read(owner, task_id)
    service.daily_check(task["observation_start"], task["observation_end"])
    return service.store.change_state(owner, task_id, body.expected_revision, True)


@business.post("/report-tasks/{task_id}/resume")
def business_resume(
    task_id: UUID, body: ReportStateChange, owner: Principal, service: Service
) -> dict:
    """恢复企业任务而不改变准确观察范围。"""
    task = service.store.read(owner, task_id)
    service.daily_check(task["observation_start"], task["observation_end"])
    return service.store.change_state(owner, task_id, body.expected_revision, True)


@workspace.put("/report-batches/{batch_id}/observations")
def workspace_observations(
    batch_id: UUID, body: ObservationTable, owner: Owner, service: Service
) -> dict:
    """补齐声明的人工资料，不接受冒充提供方数值的列。"""
    service.provide(owner, batch_id, body)
    return {"accepted": True}


@business.put("/report-batches/{batch_id}/observations")
def business_observations(
    batch_id: UUID, body: ObservationTable, owner: Principal, service: Service
) -> dict:
    """业务系统按原采集合同推送人工记录。"""
    service.provide(owner, batch_id, body)
    return {"accepted": True}


@workspace.get("/report-tasks/{task_id}/series")
def workspace_series(
    task_id: UUID,
    owner: Owner,
    service: Service,
    variable: Code | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict:
    """曲线使用该研究真实结果，不生成样例拟合值。"""
    return service.series(owner, task_id, variable, start, end)


@business.get("/report-tasks/{task_id}/series")
def business_series(
    task_id: UUID,
    owner: Principal,
    service: Service,
    variable: Code | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict:
    """向业务报告提供准确指标、单位和有效日期序列。"""
    return service.series(owner, task_id, variable, start, end)


@internal.post("/tick")
def daily_tick(body: DailyTick, service: Service) -> dict:
    """固定海豚日计划的可信回调，逻辑时刻缺失或不符明确拒绝。"""
    return service.tick(body)


@internal.post("/advance")
def advance(service: Service) -> dict:
    """推进已有批次的取数和计算结果，不负责触发每日时钟。"""
    return {"advanced": service.advance_one()}
