# -*- coding: utf-8 -*-
# @Time    : 2026/11/19 16:53
# @Author  : Codex
# @File    : inspection.py
"""定义各计算方法共用的资料、节点和规则检查响应。"""

from typing import Literal

from pydantic import Field

from ..model_center.components import (
    ComponentReference, Contract, DataType, InputBinding, Port, SourceReference,
)
from .execution import InputUsage, MethodSetting, ResearchOperation
from .variables import UnitKind


class InspectionIssue(Contract):
    """规则代码和定位对设计及执行检查保持一致。"""

    code: str
    path: tuple[str | int, ...] = ()
    node: str | None = None
    port: str | None = None
    message: str


class RuleCheck(Contract):
    """未检查和未支持不能解释成已通过。"""

    status: Literal["passed", "blocked", "not_checked", "unsupported"] = "not_checked"
    issues: tuple[InspectionIssue, ...] = ()


class ResearchChecks(Contract):
    """分别表达设计完整、操作兼容和当次执行资格。"""

    configuration: RuleCheck = Field(default_factory=RuleCheck)
    operation: RuleCheck = Field(default_factory=RuleCheck)
    execution: RuleCheck = Field(default_factory=RuleCheck)


class SourceExecution(Contract):
    """来源通道已接通不等于本次已取得数据。"""

    available: bool
    reason: str | None = None
    channel: str | None = None


class InspectionSource(Contract):
    """固定来源及取数条件，不返回取数凭据。"""

    variable_code: str
    source_name: str
    category: str | None
    unit_kind: UnitKind
    selectors: dict[str, str]
    execution: SourceExecution
    data_available: bool | None = None


class InspectionIndicator(Contract):
    """原生资料的公开字段说明，不携带数值或受限原文。"""

    port: str
    code: str
    name: str
    unit: str
    use: str
    kind: str
    source: str


class InspectionMaterial(Contract):
    """保留资料准确类型、来源状态和原生变量公开说明。"""

    code: str
    name: str
    data_type: DataType
    kind: Literal["observations", "configuration", "artifact", "deferred"]
    variable_codes: tuple[str, ...] = ()
    sources: tuple[InspectionSource, ...] = ()
    indicators: tuple[InspectionIndicator, ...] = ()


class InspectionNode(Contract):
    """按准确合同解释当前步骤，不返回页面排版。"""

    code: str
    name: str
    component: ComponentReference
    method_name: str | None = None
    relationship: str | None = None
    settings: tuple[MethodSetting, ...] = ()
    operations: tuple[ResearchOperation, ...] = ()
    inputs: tuple[Port, ...] = ()
    bindings: tuple[InputBinding, ...] = ()
    request_input: str | None = None
    parameter_schema: dict | None = None
    parameters: dict | None = None
    runtime_fields: dict[str, str] = Field(default_factory=dict)
    input_usages: tuple[InputUsage, ...] = ()
    outputs: tuple[Port, ...] = ()


class InspectionOutput(Contract):
    """公开成果引用和准确端口定义。"""

    code: str
    source: SourceReference
    definition: Port
    reusable_model: bool = False


class InspectionPrediction(Contract):
    """沿用已训练管线的预测输入和目标，不包含推测数值。"""

    input_codes: tuple[str, ...]
    target_codes: tuple[str, ...]


class InspectionEvaluationMetric(Contract):
    """本次训练能形成的误差指标名称。"""

    code: str
    name: str
    selected: bool = True
    required: bool = False


class InspectionEvaluation(Contract):
    """预览准确切分规则。只有自动比例划分提供训练百分比。"""

    strategy: Literal["automatic_dates", "configured_window", "saved_policy"]
    training_percent: int | None = None
    metrics: tuple[InspectionEvaluationMetric, ...]


class ResearchInspection(Contract):
    """各方法共用的只读投影，不更改方案和冻结摘要。"""

    schema_version: Literal["1.0"] = "1.0"
    operation: ResearchOperation | None = None
    materials: tuple[InspectionMaterial, ...] = ()
    nodes: tuple[InspectionNode, ...] = ()
    outputs: tuple[InspectionOutput, ...] = ()
    prediction: InspectionPrediction | None = None
    evaluation: InspectionEvaluation | None = None
    checks: ResearchChecks = Field(default_factory=ResearchChecks)


def normalize_issue(issue: dict) -> InspectionIssue:
    """将历史 type/rule 问题映射为稳定代码，保留公开定位。"""
    return InspectionIssue(
        code=issue.get("code", issue.get("type", issue.get("rule", "plan_contract"))),
        path=issue.get("path", ()), node=issue.get("node"),
        port=issue.get("port"), message=issue["message"],
    )


def execution_checks(passed: bool, issues: list[dict]) -> ResearchChecks:
    """实际准备结果只确认本次执行检查，不推测其他检查的完成状态。"""
    return ResearchChecks(execution=RuleCheck(
        status="passed" if passed else "blocked",
        issues=tuple(normalize_issue(issue) for issue in issues),
    ))
