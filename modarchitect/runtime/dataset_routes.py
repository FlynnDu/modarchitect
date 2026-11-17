# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 13:43
# @Author  : Codex
# @File    : dataset_routes.py
"""提供准确数据集创建与读取协议，不返回重复的来源原文。"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from ..contracts.model_center.components import Contract
from ..datasets import ResearchDatasets
from .contracts import ObservationTable
from .routes import Owner

router = APIRouter(prefix="/api/v1/workspace", tags=["研究数据集"])


class CreateDataset(Contract):
    """首次装配使用准确来源引用及可选人工观测，后续使用只传数据集身份。"""

    source_snapshot_ids: Annotated[tuple[UUID, ...], Field(max_length=1800)] = ()
    observations: ObservationTable | None = None
    data_kind: Literal["synthetic", "user_supplied"] = "user_supplied"


def service(request: Request) -> ResearchDatasets:
    """数据库未装配时不接受持久数据集请求。"""
    value = request.app.state.research_datasets
    if value is None:
        raise HTTPException(503, "Research dataset persistence is not configured")
    return value


Datasets = Annotated[ResearchDatasets, Depends(service)]


@router.post("/plans/{design_id}/datasets")
def create(design_id: UUID, body: CreateDataset, owner: Owner, datasets: Datasets) -> dict:
    """核验后内容寻址保存，重复相同内容返回同一身份。"""
    value = datasets.create(owner, design_id, body.source_snapshot_ids, body.observations, body.data_kind)
    return {"dataset_snapshot_id": value["dataset_id"]}


@router.get("/datasets/{identity}")
def read(identity: UUID, owner: Owner, datasets: Datasets) -> dict:
    """读取实际观测及其性质，完整追溯资料沿已有受权证据接口读取。"""
    value = datasets.resolve(owner, identity)
    return {k: value[k] for k in ("observations", "data_kind")}
