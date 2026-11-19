# -*- coding: utf-8 -*-
# @Time    : 2026/11/18 22:25
# @Author  : Codex
# @File    : study_routes.py
"""提供业务与个人工作区的固定版本应用协议。"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from .input_sources.contracts import AcquisitionWindow
from .routes import Principal, RequestKey, require_key
from .runtime.contracts import ModelRequest, RunView
from .runtime.dataset_routes import CreateDataset
from .runtime.routes import Owner
from .studies import BusinessStudyStart, ResearchStudies, StudyExecution, WorkspaceStudyStart, study_view

workspace = APIRouter(prefix="/api/v1/workspace", tags=["研究实例"])
business = APIRouter(prefix="/api/v1/research", tags=["业务研究实例"], dependencies=[Depends(require_key)])


def service(request: Request) -> ResearchStudies:
    """数据库就绪后复用当前研究环境。"""
    runtime = request.app.state.research_runtime
    if runtime is None:
        raise HTTPException(503, "Study persistence is not configured")
    return ResearchStudies(runtime)


Studies = Annotated[ResearchStudies, Depends(service)]


@workspace.post("/studies", status_code=201)
def create_workspace(body: WorkspaceStudyStart, owner: Owner, studies: Studies, key: RequestKey) -> dict:
    """在个人工作区应用固定方案版本。"""
    return studies.create(owner, body, key)


@business.post("/studies", status_code=201)
def create_business(body: BusinessStudyStart, owner: Principal, studies: Studies, key: RequestKey) -> dict:
    """按业务授权绑定地块、作物种植季和采集点。"""
    return studies.create(owner, body, key)


def study_actions(owner_dependency) -> APIRouter:
    """两类入口共用实例操作，各自解析可信主体。"""
    router = APIRouter(prefix="/studies/{study_id}")

    @router.get("")
    def detail(study_id: UUID, owner: owner_dependency, studies: Studies) -> dict:
        """查询固定版本及应用范围。"""
        return study_view(studies.store.read(owner, study_id))

    @router.post("/input-acquisitions", status_code=202)
    def acquire(study_id: UUID, body: AcquisitionWindow, owner: owner_dependency, studies: Studies, key: RequestKey) -> dict:
        """按已应用范围提交一次采集。"""
        return studies.acquire(owner, study_id, body, key)

    @router.get("/input-acquisitions/{acquisition_id}")
    def acquisition(study_id: UUID, acquisition_id: UUID, owner: owner_dependency, studies: Studies) -> dict:
        """查询本实例采集状态与不可变来源快照身份。"""
        return studies.runtime.sources.read(owner, acquisition_id, study_id=study_id)

    @router.post("/datasets")
    def dataset(study_id: UUID, body: CreateDataset, owner: owner_dependency, studies: Studies) -> dict:
        """用同一实例的来源快照和人工记录封存数据集。"""
        return studies.dataset(owner, study_id, body.source_snapshot_ids, body.observations, body.data_kind)

    @router.get("/datasets/{dataset_id}")
    def read_dataset(study_id: UUID, dataset_id: UUID, owner: owner_dependency, studies: Studies) -> dict:
        """查询本实例的封存样本和来源快照引用。"""
        return studies.read_dataset(owner, study_id, dataset_id)

    @router.post("/runs", status_code=202, response_model=RunView)
    def run(study_id: UUID, body: StudyExecution, owner: owner_dependency, studies: Studies, key: RequestKey) -> dict:
        """按固定方案及本实例封存数据提交运行。"""
        return studies.run(owner, study_id, body, key)

    @router.get("/runs/{run_id}", response_model=RunView)
    def read_run(study_id: UUID, run_id: UUID, owner: owner_dependency, studies: Studies) -> dict:
        """读取本实例运行和数据集归属。"""
        return studies.read_run(owner, study_id, run_id)

    @router.post("/models")
    def save_model(study_id: UUID, body: ModelRequest, owner: owner_dependency, studies: Studies) -> dict:
        """保存本实例已经成功训练的准确模型。"""
        return studies.save_model(owner, study_id, body.run_id, body.name)

    return router


workspace.include_router(study_actions(Owner))
business.include_router(study_actions(Principal))
