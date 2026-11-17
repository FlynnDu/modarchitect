# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 12:43
# @Author  : Codex
# @File    : execution.py
"""声明研究操作、准确组件的执行能力及节点输入用途。"""

from typing import Literal

from pydantic import Field, model_validator

from ..model_center.components import Code, ComponentReference, Contract

ResearchOperation = Literal["train", "predict", "analyze", "simulate", "calibrate"]
UsagePhase = Literal["training", "application", "analysis", "evaluation"]


class FieldUsage(Contract):
    """请求字段的科学用途；用途不改变变量本体、单位或来源性质。"""

    role: Literal["feature", "label", "driver", "derived", "analysis"]
    phases: tuple[UsagePhase, ...]

    @model_validator(mode="after")
    def valid_phases(self):
        """阶段必须明确且不重复。"""
        if not self.phases or len(set(self.phases)) != len(self.phases):
            raise ValueError("Variable usage phases must be unique and nonempty")
        return self


class ExecutionCapability(Contract):
    """版本化执行声明；部署镜像资格仍由服务端准确制品登记决定。"""

    operations: tuple[ResearchOperation, ...]
    state_output: Code | None = None
    inference: ComponentReference | None = None
    input_uses: dict[Code, FieldUsage] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_capability(self):
        """禁止空操作、重复操作和无法独立推理的半个训练状态声明。"""
        if not self.operations or len(set(self.operations)) != len(self.operations):
            raise ValueError(
                "Component execution operations must be unique and nonempty"
            )
        if (self.state_output is None) != (self.inference is None):
            raise ValueError("Reusable state requires its exact inference component")
        if (
            self.state_output
            and "train" not in self.operations
            and "calibrate" not in self.operations
        ):
            raise ValueError(
                "Reusable state requires training or calibration capability"
            )
        return self

    def validate_bindings(
        self, schema: dict, inputs: set[str], outputs: set[str]
    ) -> None:
        """能力必须指向真实请求字段、表端口和状态输出。"""
        if self.state_output and self.state_output not in outputs:
            raise ValueError("Declared model state is not a component output")
        for field in self.input_uses:
            binding = (
                schema.get("properties", {})
                .get(field, {})
                .get("x-research-variables", {})
            )
            if binding.get("table_port") not in inputs:
                raise ValueError(
                    "Declared variable usage requires its actual request binding"
                )


class InputUsage(Contract):
    """从权威图和请求推导的节点级用途，不另存第二份因素配置。"""

    node: Code
    port: Code
    field: Code
    variable_code: Code
    role: Literal["feature", "label", "driver", "derived", "analysis"]
    phases: tuple[UsagePhase, ...]
    observed_required: bool
