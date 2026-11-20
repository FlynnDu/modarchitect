# -*- coding: utf-8 -*-
# @Time    : 2026/11/20 15:39
# @Author  : Codex
# @File    : research_methods.py
"""以准确组件合同生成可采用的研究方法目录。"""

from functools import cache
from importlib.resources import files
from typing import Literal

from pydantic import TypeAdapter

from .catalog import catalog, research_request_schema
from .contracts.model_center.components import Code, ComponentReference, Contract, Port
from .contracts.research.execution import FieldUsage, MethodSetting
from .contracts.research.plans import TRAINING_CUTOFF
from .execution_contracts import execution_capability, reference_key, validate_execution_profile


MethodOperation = Literal["train", "simulate"]


class MethodDeclaration(Contract):
    """普通研究的版本化采用声明，其余事实来自对应组件合同。"""

    component: ComponentReference
    name: str
    relationship: str
    operation: MethodOperation = "train"
    cutoff_field: Code | None = None
    settings: tuple[MethodSetting, ...]
    advanced_fields: tuple[Code, ...] = ()


class MethodConfiguration(Contract):
    """固定默认、观测用途和运行时值沿用组件的参数名称。"""

    parameter_schema: dict
    input_uses: dict[str, FieldUsage]
    defaults: dict
    runtime_fields: dict[str, Literal[TRAINING_CUTOFF]]
    advanced_fields: tuple[Code, ...] = ()


class ResearchMethod(Contract):
    """从采用声明投影的固定方法卡片。"""

    component: ComponentReference
    name: str
    relationship: str
    operation: MethodOperation
    execution: Literal["available", "design_only"]
    configuration: MethodConfiguration
    settings: tuple[MethodSetting, ...]
    outputs: tuple[Port, ...]


class PlannedMethod(Contract):
    """待接入项有明确状态，避免作为已登记组件参与方案。"""

    code: Code
    name: str
    status: Literal["planned"] = "planned"


class MethodFamily(Contract):
    """按研究操作组织可采用方法及待接入项。"""

    operation: MethodOperation
    name: str
    planned: tuple[PlannedMethod, ...] = ()


class ResearchMethodDirectory(Contract):
    """新研究方法选择的版本化响应。"""

    schema_version: Literal["1.0"] = "1.0"
    items: tuple[ResearchMethod, ...]
    families: tuple[MethodFamily, ...]


@cache
def method_declarations() -> dict[tuple[str, int], MethodDeclaration]:
    """加载准确采用版本，拒绝重复登记。"""
    source = files("modarchitect.contracts").joinpath("research-methods-v1.json")
    rows = TypeAdapter(list[MethodDeclaration]).validate_json(source.read_bytes())
    declarations = {(row.component.code, row.component.revision): row for row in rows}
    if len(declarations) != len(rows):
        raise ValueError("Research method component is registered more than once")
    return declarations


def _training_fields(declaration, capability, definition, properties) -> dict[str, str]:
    """学习组件额外验证实测标签、切分时点和独立推理。"""
    cutoff = declaration.cutoff_field
    if (
        not capability.inference
        or properties.get(cutoff, {}).get("format") != "date"
        or not any(
            usage.role == "label" and "training" in usage.phases
            and properties[field]["x-research-variables"].get("observed")
            for field, usage in capability.input_uses.items()
        )
    ):
        raise ValueError("Training method requires observed labels and independent inference")
    inference = catalog()[capability.inference.code, capability.inference.revision].definition
    prediction = execution_capability(capability.inference.model_dump(mode="json"))
    state = next(port.data_type for port in definition.outputs if port.code == capability.state_output)
    if (
        not prediction
        or "predict" not in prediction.operations
        or not any(port.data_type == state for port in inference.inputs)
        or not any(output.data_type.shape == "table" and output in inference.outputs for output in definition.outputs)
    ):
        raise ValueError("Training method requires independent inference and comparable predictions")
    return {cutoff: TRAINING_CUTOFF}


def method_directory(profiles: dict) -> ResearchMethodDirectory:
    """把同一版本化端口和参数合同投影到不同研究操作。"""
    methods = []
    for key, declaration in method_declarations().items():
        entry = catalog()[key]
        definition = entry.definition
        if not entry.available_for_new_design or not definition.composable:
            continue
        reference = declaration.component.model_dump(mode="json")
        capability = execution_capability(reference)
        schema = research_request_schema(definition)
        properties = (schema or {}).get("properties", {})
        if (
            not capability or declaration.operation not in capability.operations or schema is None
            or any(field not in properties or "const" in properties[field] or field == declaration.cutoff_field
                   for field in declaration.advanced_fields)
        ):
            raise ValueError("Research method requires its declared operation and parameter schema")
        runtime_fields = _training_fields(declaration, capability, definition, properties) if declaration.operation == "train" else {}
        try:
            validate_execution_profile(reference_key(reference), capability, profiles)
            execution = "available"
        except ValueError:
            execution = "design_only"
        defaults = {
            key: field["default"] if "default" in field else field["const"]
            for key, field in properties.items() if "default" in field or "const" in field
        }
        methods.append(ResearchMethod(
            component=declaration.component,
            name=declaration.name,
            relationship=declaration.relationship,
            operation=declaration.operation,
            execution=execution,
            settings=declaration.settings,
            outputs=definition.outputs,
            configuration=MethodConfiguration(
                parameter_schema=schema, input_uses=capability.input_uses,
                defaults=defaults, runtime_fields=runtime_fields,
                advanced_fields=declaration.advanced_fields,
            ),
        ))
    registered = {method.component.code for method in methods if method.operation == "simulate"}
    candidates = (PlannedMethod(code="wofost", name="WOFOST"), PlannedMethod(code="apsim", name="APSIM"))
    return ResearchMethodDirectory(items=tuple(methods), families=(
        MethodFamily(operation="train", name="关系训练与预测"),
        MethodFamily(operation="simulate", name="作物生长机理模拟",
                     planned=tuple(method for method in candidates if method.code not in registered)),
    ))
