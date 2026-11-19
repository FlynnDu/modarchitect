# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 21:15
# @Author  : Codex
# @File    : contracts.py
"""研究运行的有限数值输入、调用结果和模型资源合同。"""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from ..contracts.identifiers import identity_sha256
from ..contracts.model_center.components import Code, Contract, Text
from ..contracts.research.design_saves import VersionName
from ..contracts.research.variables import Finite
from ..contracts.research.execution import ResearchOperation
from ..contracts.research.inspection import ResearchChecks


class Column(Contract):
    """保留科学单位和来源性质的数值列。"""

    code: Code
    name: Text
    unit: Text
    value_kind: Literal["observed", "estimated", "predicted"] = "observed"


class ObjectReference(Contract):
    """用户上传数据中的完整地块作物种植季身份。"""

    field_ref: Text
    crop_code: Code
    season_ref: Text


class Observation(Contract):
    """同一对象业务日的一组有限数值，预测数据允许省略目标列。"""

    object: ObjectReference
    business_date: date
    values: dict[Code, Finite]


class ObservationTable(Contract):
    """首批日尺度构表合同；输入来源摘要由服务端重新计算。"""

    columns: Annotated[tuple[Column, ...], Field(max_length=256)]
    rows: Annotated[tuple[Observation, ...], Field(min_length=1, max_length=5000)]
    source_sha256: tuple[str, ...] = ()

    @model_validator(mode="after")
    def consistent_rows(self):
        """核对列代码和完整对象日期唯一，阻止错位或隐式缺列。"""
        columns = {item.code for item in self.columns}
        if len(columns) != len(self.columns):
            raise ValueError("Observation columns must be unique")
        keys = set()
        for row in self.rows:
            obj = row.object
            key = (obj.field_ref, obj.crop_code, obj.season_ref, row.business_date)
            if key in keys or set(row.values) != columns:
                raise ValueError(
                    "Observation rows have duplicate keys or missing columns"
                )
            keys.add(key)
        return self

    def sealed(self) -> dict:
        """按实际上传数据建立来源摘要，忽略客户端自行声明的摘要。"""
        content = self.model_dump(mode="json", exclude={"source_sha256"})
        return {**content, "source_sha256": [identity_sha256(content)]}


class ResearchDataInput(Contract):
    """新调用只引用数据集；历史观测表和来源数组继续兼容。"""

    observations: ObservationTable | None = None
    data_kind: Literal["synthetic", "user_supplied"] = "user_supplied"
    source_snapshot_ids: Annotated[tuple[UUID, ...], Field(max_length=36)] = ()
    dataset_snapshot_id: UUID | None = None

    @model_validator(mode="after")
    def one_input_channel(self):
        """准确数据集自带可信性质和来源，不接受第二份可冲突的客户端声明。"""
        if self.dataset_snapshot_id is not None and (
            self.observations is not None or self.source_snapshot_ids or "data_kind" in self.model_fields_set
        ):
            raise ValueError("Dataset reference cannot be combined with inline data or source declarations")
        return self


class SavePlan(ResearchDataInput):
    """未完成配置与观测共用一个并发修订，完整校验留给发布执行。"""

    definition: dict
    version_name: VersionName = None
    expected_revision: Annotated[int, Field(strict=True, ge=1)] = 1


class ExecutionCheckRequest(ResearchDataInput):
    """检查当前编辑方案，不创建运行；指定资料与观测输入不能混用。"""

    definition: dict
    design_id: UUID | None = None
    operation: Literal["train", "analyze", "simulate", "calibrate"]


class RuleIssue(Contract):
    """可定位的单条平台规则问题，不包含原始输入。"""

    rule: str
    code: str | None = None
    node: str | None = None
    port: str | None = None
    path: tuple[str | int, ...]
    message: str


class ExecutionCheckResult(Contract):
    """调用方只需判断是否可执行，并在失败时读取规则问题。"""

    can_execute: bool
    issues: tuple[RuleIssue, ...]
    checks: ResearchChecks = Field(default_factory=ResearchChecks)


class TrainingRequest(ResearchDataInput):
    """引用准确草稿修订并提交用户自有观测。"""

    design_id: UUID
    expected_revision: Annotated[int, Field(strict=True, ge=1)]


class ExecutionRequest(TrainingRequest):
    """显式操作的新请求；旧训练请求不新增默认字段以保留幂等身份。"""

    operation: Literal["train", "analyze", "simulate", "calibrate"]


class TemplateExecutionRequest(Contract):
    """只引用已批准案例，不接受客户端替换原生观测或镜像。"""

    design_id: UUID
    expected_revision: Annotated[int, Field(strict=True, ge=1)]
    template_id: str
    template_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class RunView(Contract):
    """面向页面的运行状态，不泄露 Worker 凭据或封存输入。"""

    run_id: UUID
    design_id: UUID
    design_version_id: UUID
    study_id: UUID | None = None
    dataset_snapshot_id: UUID | None = None
    kind: ResearchOperation
    status: Literal[
        "queued",
        "dispatching",
        "submitted",
        "running",
        "succeeded",
        "failed",
        "uncertain",
    ]
    attempt_id: UUID | None
    scheduler_id: str | None
    input_sha256: str
    result_json: dict | None
    result_sha256: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class RunList(Contract):
    """明确列表中每个运行的操作身份与状态。"""

    items: list[RunView]


class PredictionRequest(ResearchDataInput):
    """引用已有训练模型，输入只包含后续预测所需因子。"""

    model_id: UUID


class ModelRequest(Contract):
    """将成功训练结果登记为可重复使用的准确模型。"""

    run_id: UUID
    name: Annotated[str, Field(min_length=1, max_length=128)]


class DispatchRequest(Contract):
    """调度器只传递运行身份和单运行的调度凭据。"""

    run_id: UUID
    dispatch_token: Annotated[str, Field(min_length=32, max_length=128)]


class Attempt(Contract):
    """当前领取与续租使用同一个准确执行尝试身份。"""

    attempt_id: UUID


class Completion(Attempt):
    """当前执行尝试的完整成功成果或明确失败。"""

    result: dict | None = None
    error: Annotated[str, Field(max_length=1000)] | None = None

    @model_validator(mode="after")
    def one_outcome(self):
        """确保一次回传只有成功或失败一种结论。"""
        if (self.result is None) == (self.error is None):
            raise ValueError("A completion requires exactly one outcome")
        return self
