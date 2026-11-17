# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 16:00
# @Author  : Codex
# @File    : entrypoint.py
"""为已冻结的原生纯计算合同提供同一文件协议，不接收动态导入地址。"""

from argparse import ArgumentParser
from functools import partial
import json
from pathlib import Path
from typing import get_type_hints

from pydantic import BaseModel
from mlgrowth_contracts.identifiers import identity_sha256
from mlgrowth_contracts.model_center.component_catalog import load_builtin_components
from mlgrowth_contracts.model_center.components import ComponentReference
from pymlgrowth.model_components.file_protocol import read_invocation, write_result
from pymlgrowth.model_components.registry import resolve_implementation


def run(input_dir: Path, output_dir: Path, binding_path: Path) -> None:
    """核对准确合同和源码，转换已声明模型参数，再输出准确端口。"""
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    reference = ComponentReference.model_validate(binding["component"])
    definition = next(d for d in load_builtin_components() if (d.code, d.revision) == (reference.code, reference.revision))
    if identity_sha256(definition.model_dump(mode="json", exclude_unset=True)) != binding["contract_sha256"]:
        raise ValueError("Native study component contract differs")
    if len(definition.outputs) != 1 or definition.selection_options or any(p.data_type.shape != "bundle" or not p.required for p in definition.inputs):
        raise ValueError("Native study requires an accepted single-bundle pure contract")
    invocation, inputs = read_invocation(input_dir, reference, {p.code for p in definition.inputs})
    operation = resolve_implementation(reference.code, reference.revision)
    function = operation.func if isinstance(operation, partial) else operation
    hints = get_type_hints(function)
    for port, value in inputs.items():
        declared = hints.get(port)
        if isinstance(declared, type) and issubclass(declared, BaseModel):
            inputs[port] = declared.model_validate(value)
    result = operation(**inputs)
    if isinstance(result, BaseModel):
        result = result.model_dump(mode="json")
    if not isinstance(result, dict):
        raise ValueError("Native study output must be a validated JSON object")
    write_result(output_dir, invocation, {definition.outputs[0].code: result})


def main() -> None:
    """仅装配文件目录，科学实现来自镜像内批准绑定。"""
    parser = ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.input_dir, args.output_dir, Path("/app/binding.json"))


if __name__ == "__main__":
    main()
