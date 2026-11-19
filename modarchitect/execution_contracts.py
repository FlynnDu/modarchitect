# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 12:43
# @Author  : Codex
# @File    : execution_contracts.py
"""集中解释准确组件操作及输入用途，并核验冻结执行声明。"""

from importlib.resources import files
import json

from .catalog import catalog, research_request_schema
from .contracts.model_center.components import Composition
from .contracts.model_center.composition import compile_composition
from .contracts.research.table_lineage import TableColumns, project_tables
from .contracts.research.execution import (
    ExecutionCapability,
    InputUsage,
    ResearchOperation,
)
from .contracts.violations import ContractViolation


def reference_key(reference: dict) -> str:
    """准确组件身份是声明和执行制品共同的索引。"""
    return "%s@%s" % (reference["code"], reference["revision"])


def execution_capability(reference: dict) -> ExecutionCapability | None:
    """新合同读取自身声明，历史合同按准确摘要读取兼容清单。"""
    entry = catalog().get((reference["code"], reference["revision"]))
    if entry is None:
        raise ValueError("Unknown component execution identity")
    raw = entry.definition.configuration.get("research_model", {}).get("execution")
    if raw is None:
        resource = files("modarchitect.contracts").joinpath(
            "execution-compatibility-v1.json"
        )
        declarations = json.loads(resource.read_text(encoding="utf-8"))
        native = files("modarchitect.contracts").joinpath(
            "native-study-execution-v1.json"
        )
        declarations.update(json.loads(native.read_text(encoding="utf-8")))
        legacy = declarations.get(reference_key(reference))
        if legacy is None:
            return None
        if legacy["contract_sha256"] != entry.contract_sha256:
            raise ValueError("Historical execution declaration checksum differs")
        raw = legacy["capability"]
    capability = ExecutionCapability.model_validate(raw)
    capability.validate_bindings(
        entry.definition.configuration.get("research_model", {}).get(
            "request_schema", {}
        ),
        {port.code for port in entry.definition.inputs},
        {port.code for port in entry.definition.outputs},
    )
    return capability


def compile_execution(
    composition: Composition, operation: ResearchOperation, profiles: dict
) -> dict:
    """核验每个节点支持操作及制品一致性；训练必须存在可复用状态。"""
    validate_operation(composition, operation)
    result = {}
    for node in composition.nodes:
        reference = node.component.model_dump(mode="json")
        key = reference_key(reference)
        capability = execution_capability(reference)
        profile = profiles.get(key)
        if profile is None:
            raise ValueError("Component execution is not available: %s" % key)
        inference = (
            reference_key(capability.inference.model_dump(mode="json"))
            if capability.inference
            else None
        )
        if (
            profile.get("state_output") != capability.state_output
            or profile.get("inference") != inference
        ):
            raise ValueError(
                "Execution artifact state or inference differs from its declaration"
            )
        if inference and inference not in profiles:
            raise ValueError("Exact inference artifact is unavailable")
        result[key] = capability.model_dump(mode="json")
    return result


def validate_operation(composition: Composition, operation: ResearchOperation) -> None:
    """设计说明与实际执行共用操作兼容规则，不要求部署制品已就绪。"""
    states = 0
    for index, node in enumerate(composition.nodes):
        capability = execution_capability(node.component.model_dump(mode="json"))
        if capability is None or operation not in capability.operations:
            raise ContractViolation(
                "Component does not support research operation %s: %s"
                % (operation, reference_key(node.component.model_dump(mode="json"))),
                ["composition", "nodes", index],
                "execution_capability_missing" if capability is None else "operation_incompatible",
                node=node.code,
            )
        states += bool(capability.state_output)
    if operation == "train" and not states:
        raise ContractViolation(
            "Training requires a declared reusable model state",
            ["composition", "outputs"], "model_state_required",
        )


def input_usages(composition: Composition, requests: dict) -> list[dict]:
    """从真实请求字段投影用途与阶段，未知用途不自行猜测。"""
    uses = []
    for node in composition.nodes:
        request = requests.get(node.code)
        if request is None:
            continue
        capability = execution_capability(node.component.model_dump(mode="json"))
        if capability is None:
            continue
        recipe, value, schema = request
        sources = {binding.port: (binding.source.node, binding.source.port) for binding in node.bindings}
        training_inputs, training_labels = set(), []
        for field, usage in capability.input_uses.items():
            spec = (
                schema.get("properties", {}).get(field, {}).get("x-research-variables")
            )
            if not spec or field not in value:
                continue
            codes = value[field] if isinstance(value[field], list) else [value[field]]
            for code in codes:
                if "training" in usage.phases:
                    column = (*sources.get(spec["table_port"], (None, spec["table_port"])), code)
                    if usage.role in {"feature", "driver"}:
                        training_inputs.add(column)
                    elif usage.role == "label":
                        training_labels.append((column, field, spec["table_port"]))
                uses.append(
                    InputUsage(
                        node=node.code,
                        port=spec["table_port"],
                        field=field,
                        variable_code=code,
                        role=usage.role,
                        phases=usage.phases,
                        observed_required=bool(spec.get("observed")),
                    ).model_dump(mode="json")
                )
        for column, field, port in training_labels:
            if column in training_inputs:
                raise ContractViolation(
                    "A training input cannot include its own target: %s" % column[-1],
                    ["input_recipes", recipe, "value", field], "input_target_overlap",
                    node=node.code, port=port,
                )
    return uses


def external_input_codes(plan, operation: str) -> set[str]:
    """按准确节点合同及操作阶段选择真正外部输入，预测不再要求训练标签。"""
    requests = {}
    for node in plan.composition.nodes:
        for binding in node.bindings:
            if binding.source.node is not None:
                continue
            recipe = plan.input_recipes[binding.source.port]
            if recipe.kind == "configuration":
                definition = catalog()[
                    node.component.code, node.component.revision
                ].definition
                requests[node.code] = (
                    binding.source.port,
                    recipe.value,
                    research_request_schema(definition) or {},
                )
    external = {
        code
        for recipe in plan.input_recipes.values()
        if recipe.kind == "observations"
        for code in recipe.variable_codes
    }
    usages = input_usages(plan.composition, requests)
    phase = {
        "train": "training",
        "predict": "application",
        "analyze": "analysis",
        "simulate": "application",
        "calibrate": "training",
    }[operation]
    if usages:
        registered = catalog()
        order = compile_composition(
            plan.composition, {key: item.definition for key, item in registered.items()}
        )["order"]
        nodes = {node.code: node for node in plan.composition.nodes}
        columns = {
            (None, port): TableColumns(
                {code: True for code in recipe.variable_codes},
                external={code: frozenset({code}) for code in recipe.variable_codes},
            )
            for port, recipe in plan.input_recipes.items()
            if recipe.kind == "observations"
        }
        required = set()
        for code in order:
            node = nodes[code]
            inputs = {
                b.port: columns.get((b.source.node, b.source.port))
                for b in node.bindings
            }
            request = requests.get(code)
            if request is None:
                continue
            _, value, schema = request
            for use in usages:
                if use["node"] != code or phase not in use["phases"]:
                    continue
                spec = schema["properties"][use["field"]]["x-research-variables"]
                if spec.get("new_column"):
                    continue
                parent = inputs.get(use["port"])
                if parent is None or use["variable_code"] not in parent.observed:
                    raise ValueError(
                        "Research input lineage is not declared for %s.%s"
                        % (code, use["port"])
                    )
                required.update(parent.external.get(use["variable_code"], ()))
            declarations = (
                registered[node.component.code, node.component.revision]
                .definition.configuration.get("research_model", {})
                .get("table_outputs", {})
            )
            for port, table in project_tables(declarations, inputs, value).items():
                columns[code, port] = table
        return external & required
    if operation == "predict":
        return external & {
            v.code for v in plan.variables if v.role in {"covariate", "driver"}
        }
    return external
