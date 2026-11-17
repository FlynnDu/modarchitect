# -*- coding: utf-8 -*-
# @Time    : 2026/11/3 17:33
# @Author  : feidu
# @File    : composition.py
"""按已登记的准确组件合同编译组合；验证设计相容性，不代替科学运行资格。"""

from collections.abc import Mapping

from .components import ComponentDefinition, Composition, DataType, SourceReference
from ..violations import ContractViolation


def compatible(output: DataType, input_type: DataType) -> bool:
    """不隐式转换单位、插值日期、栅格化或把模拟值当观测真值。"""
    return output == input_type


def compile_composition(
    composition: Composition,
    components: Mapping[tuple[str, int], ComponentDefinition],
) -> dict:
    """返回拓扑顺序、外部输入和每节点运行门槛；任何未解析连接均拒绝。

    设计的时间/网格合同只证明所需对齐规则一致。实际对象、边界版本、日期、
    数据质量及制品许可必须在绑定数据时再次核验，不能通过设计验证跳过。
    """
    nodes = {item.code: item for item in composition.nodes}
    external = {item.code: item for item in composition.inputs}
    if len(nodes) != len(composition.nodes) or len(external) != len(composition.inputs):
        raise ValueError("Design node and external input codes must be unique")
    if len({item.code for item in composition.outputs}) != len(composition.outputs):
        raise ValueError("Design output codes must be unique")
    definitions = {}
    for index, (code, node) in enumerate(nodes.items()):
        identity = (node.component.code, node.component.revision)
        if identity not in components:
            raise ContractViolation("Component version is not registered: %s@%s" % identity, ["composition", "nodes", index, "component"], "unknown_component", node=code)
        definitions[code] = components[identity]
        for key, values in node.selections.items():
            allowed = definitions[code].selection_options.get(key)
            if (
                allowed is None
                or len(set(values)) != len(values)
                or not set(values) <= set(allowed)
            ):
                raise ValueError(
                    "Component selection is not supported: %s.%s" % (code, key)
                )
    dependencies: dict[str, set[str]] = {code: set() for code in nodes}
    used_inputs: set[str] = set()

    def resolve(source: SourceReference, path: list | None = None, node: str | None = None, port: str | None = None) -> DataType:
        """解析外部输入或上游输出的准确数据类型。"""
        if source.node is None:
            if source.port not in external:
                raise ContractViolation("External input is not declared: %s" % source.port, path or ["composition", "inputs"], "unresolved_source", node=node, port=port)
            used_inputs.add(source.port)
            return external[source.port].data_type
        if source.node not in definitions:
            raise ContractViolation("Source node is not declared: %s" % source.node, path or ["composition", "nodes"], "unresolved_source", node=node, port=port)
        ports = {item.code: item for item in definitions[source.node].outputs}
        if source.port not in ports:
            raise ContractViolation("Source output port is not declared: %s" % source.port, path or ["composition", "outputs"], "unresolved_source", node=node, port=port)
        return ports[source.port].data_type

    for index, (code, node) in enumerate(nodes.items()):
        inputs = {item.code: item for item in definitions[code].inputs}
        bound = set()
        for binding_index, binding in enumerate(node.bindings):
            path = ["composition", "nodes", index, "bindings", binding_index]
            if binding.port in bound or binding.port not in inputs:
                raise ContractViolation("Input binding is duplicated or unknown: %s" % binding.port, path + ["port"], "invalid_port", node=code, port=binding.port)
            bound.add(binding.port)
            source_type = resolve(binding.source, path + ["source"], code, binding.port)
            if not compatible(source_type, inputs[binding.port].data_type):
                raise ContractViolation("Input contract is incompatible: %s.%s" % (code, binding.port), path + ["source"], "incompatible_connection", node=code, port=binding.port)
            if binding.source.node is not None:
                dependencies[code].add(binding.source.node)
        missing = {key for key, port in inputs.items() if port.required} - bound
        if missing:
            raise ContractViolation("Required input bindings are missing: %s.%s" % (code, ",".join(sorted(missing))), ["composition", "nodes", index, "bindings"], "missing_input", node=code, port=sorted(missing)[0])
    roots = set()
    for output in composition.outputs:
        if output.source.node is None:
            raise ValueError("Design outputs must reference a component output")
        resolve(output.source)
        roots.add(output.source.node)
    if used_inputs != set(external):
        raise ValueError("Design contains unused external inputs")
    relevant = set()
    pending = list(roots)
    while pending:
        code = pending.pop()
        if code not in relevant:
            relevant.add(code)
            pending.extend(dependencies[code])
    if relevant != set(nodes):
        raise ValueError("Design contains nodes unrelated to its outputs")
    remaining = {code: set(values) for code, values in dependencies.items()}
    order = []
    while remaining:
        ready = sorted(code for code, deps in remaining.items() if not deps)
        if not ready:
            raise ContractViolation("Design contains a dependency cycle", ["composition", "nodes"], "dependency_cycle")
        order.extend(ready)
        for code in ready:
            del remaining[code]
        for deps in remaining.values():
            deps.difference_update(ready)
    return {
        "validation_scope": "design_contract",
        "compiler_version": "1.0.0",
        "object_scope": composition.object_scope,
        "order": order,
        "external_inputs": [
            item.model_dump(mode="json") for item in composition.inputs
        ],
        "nodes": [
            {
                "node": code,
                "component": nodes[code].component.model_dump(),
                "execution_mode": definitions[code].execution_mode,
                "runtime_parameters": list(definitions[code].runtime_parameters),
                "composable": definitions[code].composable,
                "selections": nodes[code].selections,
                "requirements": list(definitions[code].requirements),
                "limitations": list(definitions[code].limitations),
            }
            for code in order
        ],
        "binding_checks": [
            "verified_company_and_object_access",
            "crop_field_season_and_boundary_version",
            "business_dates_cutoff_and_grid_alignment",
            "source_quality_units_and_ground_truth",
            "artifact_integrity_applicability_and_release_authorization",
        ],
    }
