# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 21:32
# @Author  : Codex
# @File    : routes.py
"""独立工作区和可信 Worker 的运行 HTTP 协议。"""

from importlib.resources import files
import json
import os
from secrets import compare_digest
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from ..contracts.enterprise.identity import VerifiedPrincipal
from ..contracts.model_center.components import Contract
from .contracts import (
    Attempt,
    Completion,
    DispatchRequest,
    ModelRequest,
    PredictionRequest,
    TrainingRequest,
    ExecutionRequest,
    SavePlan,
    RunView,
    RunList,
    TemplateExecutionRequest,
    ExecutionCheckRequest,
    ExecutionCheckResult,
)
from .service import ResearchRuntime
from .workspace import owner, session
from ..system_inputs import input_readiness
from ..study_templates import templates, design_template, template_view
from ..inspection import inspect_definition

workspace = APIRouter(prefix="/api/v1/workspace", tags=["个人研究工作区"])
internal = APIRouter(prefix="/internal/v1/research", tags=["可信研究执行"])
Owner = Annotated[VerifiedPrincipal, Depends(owner)]
RequestKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=1, max_length=128)
]


class DispatchResult(Contract):
    """调度回执独立于科学计算结果。"""

    scheduler_id: str | None = None
    error: str | None = None


def service(request: Request) -> ResearchRuntime:
    """缺少数据库时关闭持久化能力，保留公开设计器。"""
    runtime = request.app.state.research_runtime
    if runtime is None:
        raise HTTPException(503, "Research persistence is not configured")
    return runtime


def worker_key(request: Request) -> None:
    """Worker 凭据只保存在独立部署环境中。"""
    actual = request.headers.get("X-Research-Worker-Key", "")
    expected = os.getenv("MODARCHITECT_WORKER_KEY", "")
    if len(expected) < 32 or not compare_digest(actual, expected):
        raise HTTPException(401, "Research worker authentication is required")


Runtime = Annotated[ResearchRuntime, Depends(service)]
internal.dependencies.append(Depends(worker_key))


@workspace.get("/session")
def open_session(request: Request, response: Response) -> dict:
    """创建或恢复签名个人工作区。"""
    return session(request, response)


@workspace.get("/examples/{kind}")
def example(kind: str) -> dict:
    """读取准确标注为合成数据的可编辑研究样例。"""
    if kind not in {"multivariable", "chain", "system", "analysis", "calendar"}:
        raise HTTPException(404, "Research example was not found")
    source = files("modarchitect").joinpath("web", "designer", kind + "-study.json")
    return json.loads(source.read_text(encoding="utf-8"))


@workspace.get("/plans")
def list_plans(principal: Owner, runtime: Runtime) -> dict:
    """列出当前主体云端保存的方案草稿。"""
    return {"items": runtime.designs.list_drafts(principal)}


@workspace.get("/study-templates")
def list_templates() -> dict:
    """公开研究目的和来源，原始业务档案不进入目录响应。"""
    return {"items": [template_view(row) for row in templates()]}


@workspace.get("/study-templates/{template_id}")
def read_template(template_id: str, principal: Owner, sha256: str | None = None) -> dict:
    """会话内读取可采用定义，受限原生输入不发送给浏览器。"""
    result = template_view(design_template(template_id, sha256), include_definition=True)
    return {**result, "inspection": inspect_definition(result["definition"]).model_dump(mode="json")}


@workspace.post("/template-runs", response_model=RunView)
def run_template(body: TemplateExecutionRequest, principal: Owner, runtime: Runtime, key: RequestKey) -> dict:
    """按准确修订运行模板封存输入，拒绝客户端替换数值冒充来源。"""
    return runtime.run_template(principal, body, key)


@workspace.post("/plans")
def create_plan(
    body: SavePlan, principal: Owner, runtime: Runtime, key: RequestKey
) -> dict:
    """复用现有方案保存与幂等规则。"""
    return runtime.save_plan(principal, body, key=key)


@workspace.post("/check-execution", response_model=ExecutionCheckResult, response_model_exclude_unset=True)
def check_execution(body: ExecutionCheckRequest, principal: Owner, runtime: Runtime) -> dict:
    """只读核验输入增删后的执行条件，和实际启动共用规则。"""
    return runtime.check_execution(principal, body)


@workspace.get("/plans/{design_id}")
def read_plan(design_id: UUID, principal: Owner, runtime: Runtime) -> dict:
    """按准确身份重新读取方案。"""
    saved = runtime.designs.read(principal, design_id)
    return {
        **saved,
        **runtime.store.data(principal, design_id),
        "inspection": inspect_definition(saved["configuration"]["definition"]).model_dump(mode="json"),
    }


@workspace.get("/plans/{design_id}/input-readiness")
def plan_input_readiness(design_id: UUID, principal: Owner, runtime: Runtime) -> dict:
    """受权读取准确方案的取数位置及尚未满足的运行条件。"""
    saved = runtime.designs.read(principal, design_id)
    return {"items": input_readiness(saved["configuration"]["definition"])}


@workspace.put("/plans/{design_id}")
def update_plan(
    design_id: UUID, body: SavePlan, principal: Owner, runtime: Runtime
) -> dict:
    """保留修订比较，两个页面的并发编辑不会互相覆盖。"""
    return runtime.save_plan(principal, body, design_id=design_id)


@workspace.post("/design-versions/{version_id}/drafts")
def open_version_draft(version_id: UUID, principal: Owner, runtime: Runtime, key: RequestKey) -> dict:
    """个人工作区复用正式版本的新草稿规则。"""
    return runtime.designs.open_draft(principal, version_id, key)


@workspace.post("/runs", response_model=RunView)
def train(
    body: TrainingRequest | ExecutionRequest,
    principal: Owner,
    runtime: Runtime,
    key: RequestKey,
) -> dict:
    """兼容旧训练请求，按显式操作封存并提交真实调度。"""
    return runtime.train(principal, body, key)


@workspace.get("/runs", response_model=RunList)
def list_runs(principal: Owner, runtime: Runtime) -> dict:
    """列出真实运行状态和可追溯成果。"""
    return {"items": runtime.store.list_runs(principal)}


@workspace.get("/runs/{run_id}", response_model=RunView)
def read_run(run_id: UUID, principal: Owner, runtime: Runtime) -> dict:
    """查询队列、调度、计算及结果。"""
    return runtime.store.read(principal, run_id)


@workspace.get("/runs/{run_id}/plan")
def run_plan(run_id: UUID, principal: Owner, runtime: Runtime) -> dict:
    """读取该次运行采用的准确方案；布局和卡片由客户端展示。"""
    return runtime.store.run_plan(principal, run_id)


@workspace.post("/models")
def save_model(body: ModelRequest, principal: Owner, runtime: Runtime) -> dict:
    """将准确成功训练成果登记为不可变模型。"""
    return runtime.store.save_model(principal, body.run_id, body.name)


@workspace.get("/models")
def list_models(principal: Owner, runtime: Runtime) -> dict:
    """列出可以继续预测的模型。"""
    return {"items": runtime.store.list_models(principal)}


@workspace.get("/models/{model_id}")
def read_model(model_id: UUID, principal: Owner, runtime: Runtime) -> dict:
    """读取模型状态及来源摘要，继续受工作区隔离。"""
    return runtime.store.model(principal, model_id)


@workspace.post("/predictions", response_model=RunView)
def predict(
    body: PredictionRequest, principal: Owner, runtime: Runtime, key: RequestKey
) -> dict:
    """按已保存模型提交独立预测，不重新训练。"""
    return runtime.predict(principal, body, key)


@internal.post("/dispatch/next")
def next_dispatch(runtime: Runtime) -> dict:
    """内部消费者取得一次准确投递。"""
    return {"job": runtime.store.next_dispatch()}


@internal.post("/runs/{run_id}/dispatch")
def dispatch_result(run_id: UUID, body: DispatchResult, runtime: Runtime) -> dict:
    """持久化真实海豚实例或未能确认的提交。"""
    runtime.store.dispatch_result(run_id, body.scheduler_id, body.error)
    return {"accepted": True}


@internal.post("/claim")
def claim(body: DispatchRequest, runtime: Runtime) -> dict:
    """独立 Worker 领取封存输入与当前尝试身份。"""
    return runtime.store.claim(body.run_id, body.dispatch_token)


@internal.post("/runs/{run_id}/heartbeat")
def heartbeat(run_id: UUID, body: Attempt, runtime: Runtime) -> dict:
    """检查当前尝试并续租，实际结果由完成入口登记。"""
    runtime.store.heartbeat(run_id, body.attempt_id)
    return {"accepted": True}


@internal.post("/runs/{run_id}/complete")
def complete(run_id: UUID, body: Completion, runtime: Runtime) -> dict:
    """核对当前尝试并提交成功成果或失败。"""
    return runtime.store.complete(run_id, body.attempt_id, body.result, body.error)
