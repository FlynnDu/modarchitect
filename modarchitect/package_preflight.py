# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 16:16
# @Author  : Codex
# @File    : package_preflight.py
"""复用旧清单校验，检查当前目录端口和候选版本。"""

import re

from jsonschema import Draft202012Validator, SchemaError

from .catalog import CatalogConflict, catalog
from .contracts.identifiers import identity_sha256
from .contracts.model_center.components import ComponentReference
from .contracts.model_center.component_packages import (
    ComponentPackageManifest,
    ComponentPackageValidation,
    PackageDataType,
)

_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_LOCAL_DEFINITION = re.compile(r"#/\$defs/([a-zA-Z_][a-zA-Z_0-9]{0,95})")
_REFERENCE_KEYWORDS = {
    "$id",
    "$anchor",
    "$dynamicAnchor",
    "$dynamicRef",
    "$recursiveAnchor",
    "$recursiveRef",
}


def _validate_request_schema(schema: dict) -> None:
    """只接受离线参数表单所需的封闭对象与无环的根定义引用。"""
    if (
        schema.get("type") != "object"
        or schema.get("additionalProperties") is not False
    ):
        raise ValueError("Package request schema must declare a closed object")
    definitions = schema.get("$defs", {})
    if not isinstance(definitions, dict):
        raise ValueError("Package request schema definitions must be an object")

    pending = [(schema, 0, False)]
    visited = 0
    while pending:
        node, depth, in_definition = pending.pop()
        visited += 1
        if visited > 4096 or depth > 24:
            raise ValueError("Package request schema exceeds its complexity budget")
        if isinstance(node, dict):
            if _REFERENCE_KEYWORDS.intersection(node):
                raise ValueError(
                    "Package request schema cannot change its reference scope"
                )
            if "$schema" in node and (
                node is not schema or node["$schema"] != _DIALECT
            ):
                raise ValueError("Package request schema must use Draft 2020-12")
            if "$ref" in node:
                reference = node["$ref"]
                local = (
                    _LOCAL_DEFINITION.fullmatch(reference)
                    if isinstance(reference, str)
                    else None
                )
                if in_definition or local is None or local.group(1) not in definitions:
                    raise ValueError(
                        "Package request schema requires a local root definition reference"
                    )
            pending.extend(
                (value, depth + 1, in_definition or key == "$defs")
                for key, value in node.items()
            )
        elif isinstance(node, list):
            pending.extend((value, depth + 1, in_definition) for value in node)

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(
            "Package request schema is invalid under Draft 2020-12"
        ) from exc


def registered_port_types() -> tuple[PackageDataType, ...]:
    """公布可供新组件清单引用的准确文件端口类型。"""
    ports = {}
    for entry in catalog().values():
        if entry.available_for_new_design:
            for port in (*entry.definition.inputs, *entry.definition.outputs):
                if port.data_type.shape in {"bundle", "table"}:
                    value = port.data_type.model_dump()
                    ports[identity_sha256(value)] = PackageDataType.model_validate(
                        value
                    )
    return tuple(ports.values())


def validate_manifest(manifest: ComponentPackageManifest) -> ComponentPackageValidation:
    """校验清单及端口，返回摘要和候选身份。"""
    _validate_request_schema(manifest.contract.request_schema)
    ref = ComponentReference(
        code=manifest.component.code, revision=manifest.component.revision
    )
    if any(
        code == ref.code and revision >= ref.revision for code, revision in catalog()
    ):
        raise CatalogConflict("Component revision must advance the catalog")
    registered = registered_port_types()
    for port in (*manifest.contract.inputs, *manifest.contract.outputs):
        if port.data_type not in registered:
            raise ValueError("Package port contract is not registered: %s" % port.code)
    return ComponentPackageValidation(
        component=ref,
        manifest_sha256=identity_sha256(
            manifest.model_dump(mode="json", exclude_unset=True)
        ),
    )
