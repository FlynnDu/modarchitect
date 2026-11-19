# -*- coding: utf-8 -*-
# @Time    : 2026/11/19 16:53
# @Author  : Codex
# @File    : inspection.py
"""从准确方案和组件合同投影资料、参数、节点用途及规则结果。"""

from pydantic import ValidationError

from .catalog import catalog, research_request_schema
from .contracts.research.inspection import (
    InspectionMaterial, InspectionNode, InspectionOutput, ResearchInspection,
    ResearchChecks, RuleCheck, normalize_issue,
)
from .contracts.research.plans import ResearchPlan
from .contracts.research.execution import PURPOSE_OPERATIONS
from .contracts.research.drafts import import_draft
from .contracts.violations import ContractViolation
from .execution_contracts import execution_capability, input_usages, validate_operation
from .study_templates import matches_template, native_input_requirements, template
from .system_inputs import input_readiness
from .validation import _requests, check_definition, compile_graph

def inspect_configuration(configuration: dict) -> dict:
    """草稿检查的旧回执附加统一投影，保证同一次检查解释相同正文。"""
    definition = import_draft(configuration)["definition"]
    check = check_definition(definition)
    return {**check, "inspection": inspect_definition(definition, check).model_dump(mode="json")}


def inspect_definition(definition: dict, check: dict | None = None) -> ResearchInspection:
    """只读检查不取数、不授予运行资格；非法草稿仍返回相同响应形状。"""
    check = check if check is not None else check_definition(definition)
    configuration = RuleCheck(
        status="passed" if check["valid"] else "blocked",
        issues=tuple(normalize_issue(issue) for issue in check["issues"]),
    )
    checks = ResearchChecks(configuration=configuration)
    result = ResearchInspection(checks=checks)
    try:
        plan = ResearchPlan.model_validate(definition)
    except ValidationError:
        return result
    operation = PURPOSE_OPERATIONS[plan.purpose]
    registered = catalog()
    # 图引用未成立时不推测端口或使用历史上一次检查结果。
    if any((node.component.code, node.component.revision) not in registered for node in plan.composition.nodes):
        return result
    try:
        compile_graph(plan.composition)
    except ValueError:
        return result
    try:
        validate_operation(plan.composition, operation)
    except ContractViolation as exc:
        compatibility = RuleCheck(status="unsupported" if exc.rule == "execution_capability_missing" else "blocked",
                                  issues=(normalize_issue(exc.issue()),))
    else:
        compatibility = RuleCheck(status="passed")
    checks = ResearchChecks(configuration=configuration, operation=compatibility)
    try:
        requests = _requests(plan, for_execution=False)
        usages = input_usages(plan.composition, requests)
    except ValueError:
        # 配置错误由 configuration 中的准确问题表达，不能伪造已推导用途。
        usages = []
    sources = input_readiness(definition) if check["valid"] else []
    indicators = []
    marker = plan.layout.get("study_template")
    if isinstance(marker, dict):
        try:
            row = template(marker["id"], marker["sha256"])
        except (LookupError, KeyError):
            row = None
        if row is not None and matches_template(row, definition) and "bundle_sha256" in row:
            indicators = native_input_requirements(row)
            for node in plan.composition.nodes:
                selected = next((plan.input_recipes[b.source.port].value for b in node.bindings
                                 if b.port == "request" and b.source.node is None
                                 and plan.input_recipes[b.source.port].kind == "configuration"), None)
                if not isinstance(selected, dict) or not isinstance(selected.get("variables"), list):
                    continue
                series = {b.source.port for b in node.bindings if b.port == "series" and b.source.node is None}
                indicators = [item for item in indicators if item["port"] not in series or item["code"] in selected["variables"]]
    materials = tuple(
        InspectionMaterial(
            code=port.code, name=port.name, data_type=port.data_type,
            kind=plan.input_recipes[port.code].kind,
            variable_codes=plan.input_recipes[port.code].variable_codes,
            sources=tuple(source for source in sources if source["variable_code"] in plan.input_recipes[port.code].variable_codes),
            indicators=tuple(item for item in indicators if item["port"] == port.code),
        )
        for port in plan.composition.inputs
        if plan.input_recipes[port.code].kind != "configuration"
        and not any(binding.port == "request" and binding.source.node is None and binding.source.port == port.code for node in plan.composition.nodes for binding in node.bindings)
    )
    nodes = []
    for node in plan.composition.nodes:
        component = registered[node.component.code, node.component.revision].definition
        capability = execution_capability(node.component.model_dump(mode="json"))
        binding = next((binding for binding in node.bindings if binding.port == "request" and binding.source.node is None), None)
        recipe = plan.input_recipes[binding.source.port] if binding else None
        nodes.append(InspectionNode(
            code=node.code, name=component.name, component=node.component,
            operations=capability.operations if capability else (), inputs=component.inputs, bindings=node.bindings,
            request_input=binding.source.port if binding else None,
            parameter_schema=research_request_schema(component),
            parameters=recipe.value if recipe else None,
            runtime_fields=recipe.runtime_fields if recipe else {},
            input_usages=tuple(use for use in usages if use["node"] == node.code),
            outputs=component.outputs,
        ))
    outputs = []
    by_code = {node.code: node for node in nodes}
    for output in plan.composition.outputs:
        node = by_code.get(output.source.node)
        port = next((port for port in node.outputs if port.code == output.source.port), None) if node else None
        if port is not None:
            outputs.append(InspectionOutput(code=output.code, source=output.source, definition=port))
    return ResearchInspection(operation=operation, materials=materials, nodes=tuple(nodes),
                              outputs=tuple(outputs), checks=checks)
