# -*- coding: utf-8 -*-
# @Time    : 2026/11/3 17:33
# @Author  : feidu
# @File    : components.py
"""模型设计的组件和端口合同；不承载科学结果、执行权限或动态代码。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Code = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,95}$")]
Text = Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]
Revision = Annotated[int, Field(strict=True, ge=1, le=2147483647)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DataType(Contract):
    """完整相等才兼容；相同量纲不代表相同指标、支撑尺度或观测性质。"""

    semantic: Code
    version: Revision = 1
    shape: Literal["scalar", "raster", "table", "geometry", "bundle", "model"]
    unit: Text
    alignment: Literal["context", "static", "business_date", "season", "grid", "cutoff"]


OutputView = Literal["daily_series_v1", "relationship_table_v1", "wofost_kpis_v1"]
KernelBlocker = Literal["workflow_assembly", "controlled_runtime_parameters"]


class Port(Contract):
    code: Code
    name: Text
    data_type: DataType
    required: bool = True
    description: Text
    projection: Literal[
        "identity", "tuple_item_0", "tuple_item_1", "attribute_values"
    ] = "identity"
    allow_none: bool = False
    output_view: OutputView | None = None

    @model_validator(mode="after")
    def check_output_view(self):
        """可展示能力是端口的显式承诺；相同JSON形状不能替代语义。"""
        dtype = self.data_type
        actual = (dtype.semantic, dtype.shape, dtype.alignment, dtype.unit)
        expected = {
            "daily_series_v1": (
                "research_observation_table",
                "table",
                "business_date",
                "column_definitions",
            ),
            "relationship_table_v1": (
                "relationship_analysis",
                "bundle",
                "context",
                "native_contract",
            ),
            "wofost_kpis_v1": (
                "wofost_report_kpis",
                "bundle",
                "season",
                "native_contract",
            ),
        }
        versions = {2} if self.output_view == "wofost_kpis_v1" else {1, 2}
        if self.output_view is not None and (
            actual != expected[self.output_view] or dtype.version not in versions
        ):
            raise ValueError("Component output view is incompatible with its data type")
        return self


class Implementation(Contract):
    """受审查源码证据；只是发现资料，不作为客户端可选择的导入地址。"""

    module: Annotated[str, Field(pattern=r"^[a-zA-Z_][\w]*(\.[a-zA-Z_][\w]*)+$")]
    symbol: Annotated[str, Field(pattern=r"^[a-zA-Z_]\w*(\.[a-zA-Z_]\w*)*$")]
    source_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ComponentDefinition(Contract):
    code: Code
    revision: Revision
    name: Text
    summary: Text
    category: Literal[
        "source",
        "transform",
        "mechanistic",
        "learning",
        "rule",
        "training",
        "assessment",
    ]
    execution_mode: Literal["kernel", "workflow_stage", "external_cli"]
    implementation: Implementation
    algorithm: Text
    mechanism: Text
    inputs: tuple[Port, ...]
    outputs: Annotated[tuple[Port, ...], Field(min_length=1)]
    requirements: Annotated[tuple[Text, ...], Field(min_length=1)]
    limitations: Annotated[tuple[Text, ...], Field(min_length=1)]
    # 固定的受审查选择，如光谱指数名或风险规则；用户不能任意更改执行语义。
    configuration: dict = Field(default_factory=dict)
    selection_options: dict[Code, tuple[Code, ...]] = Field(default_factory=dict)
    related_capabilities: tuple[str, ...] = ()
    composable: bool = False
    native_parameters: tuple[dict, ...] = ()
    runtime_parameters: tuple[Code, ...] = ()
    requires_instance: bool = False

    @property
    def kernel_blocker(self) -> KernelBlocker | None:
        """定义直接内核运行的共同边界，目录标记不能覆盖执行前提。"""
        if (
            not self.composable
            or self.execution_mode != "kernel"
            or self.requires_instance
        ):
            return "workflow_assembly"
        if self.runtime_parameters:
            return "controlled_runtime_parameters"
        return None

    @model_validator(mode="after")
    def unique_ports(self):
        """核对同方向端口及运行参数的唯一性。"""
        for ports in (self.inputs, self.outputs):
            if len({port.code for port in ports}) != len(ports):
                raise ValueError("Component port codes must be unique")
        if any(port.output_view is not None for port in self.inputs):
            raise ValueError("Component input ports cannot declare an output view")
        if self.composable:
            declared = {item["code"] for item in self.native_parameters}
            required = {
                item["code"] for item in self.native_parameters if item["required"]
            }
            supplied = (
                {item.code for item in self.inputs}
                | set(self.runtime_parameters)
                | set(self.configuration.get("call_kwargs", {}))
            )
            if self.configuration.get("feature_profile"):
                supplied.add("feature_profile")
            if (
                required - supplied
                or supplied - declared
                or set(self.selection_options) - declared
            ):
                raise ValueError(
                    "Composable ports do not cover the native function contract"
                )
            if any(item.projection != "identity" for item in self.inputs):
                raise ValueError("Input ports cannot project results")
        return self


class ComponentReference(Contract):
    code: Code
    revision: Revision


class SourceReference(Contract):
    """引用图内结果或外部需求；不允许文件路径、URL或脚本作为执行输入。"""

    node: Code | None = None
    port: Code


class InputBinding(Contract):
    port: Code
    source: SourceReference


class DesignNode(Contract):
    code: Code
    component: ComponentReference
    bindings: Annotated[tuple[InputBinding, ...], Field(max_length=32)] = ()
    selections: dict[
        Code, Annotated[tuple[Code, ...], Field(min_length=1, max_length=256)]
    ] = Field(default_factory=dict)


class ExternalInput(Contract):
    code: Code
    name: Text
    data_type: DataType
    role: Literal["context", "driver", "feature", "parameter", "ground_truth", "model"]


class DesignOutput(Contract):
    code: Code
    source: SourceReference


class Composition(Contract):
    """可复用设计，不嵌入真实地块数据；一次执行再绑定授权地块、作物与季节。"""

    schema_version: Literal["1.0"] = "1.0"
    object_scope: Literal["field_crop_season"] = "field_crop_season"
    inputs: Annotated[tuple[ExternalInput, ...], Field(max_length=128)] = ()
    nodes: Annotated[tuple[DesignNode, ...], Field(min_length=1, max_length=64)]
    outputs: Annotated[tuple[DesignOutput, ...], Field(min_length=1, max_length=64)]


class DesignPublication(Contract):
    name: Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]
    description: Annotated[str, Field(max_length=4000)] = ""
    revision: Revision
    composition: Composition
    research_plan: dict | None = None

    @model_validator(mode="after")
    def validate_research_plan(self):
        """新完整配置与原准确组合同源；延迟导入避免合同定义形成循环。"""
        if self.research_plan is not None:
            from modarchitect.contracts.research.plans import ResearchPlan

            plan = ResearchPlan.model_validate(self.research_plan)
            if plan.composition != self.composition or plan.name != self.name:
                raise ValueError("Research plan differs from its published composition")
        return self

    def publication_payload(self) -> dict:
        """旧版本不新增null键，保持原始发布内容及幂等摘要不变。"""
        exclude = {"research_plan"} if self.research_plan is None else set()
        return self.model_dump(mode="json", exclude=exclude)
