# -*- coding: utf-8 -*-
# @Time    : 2026/11/6 19:40
# @Author  : feidu
# @File    : component_packages.py
"""独立组件包首期声明合同，审核与实际执行资格由应用层管理。"""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .components import ComponentReference, Contract, DataType, Port, Text
from ..research.execution import ExecutionCapability

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class PackageComponent(ComponentReference):
    name: Text
    category: Literal[
        "source",
        "transform",
        "mechanistic",
        "learning",
        "rule",
        "training",
        "assessment",
    ]


class PackageDataType(DataType):
    shape: Literal["bundle", "table"]


class PackagePort(Port):
    """声明首期运行器与对外 Schema 共用的必填 JSON 对象端口。"""

    data_type: PackageDataType
    required: Literal[True] = True
    allow_none: Literal[False] = False
    projection: Literal["identity"] = "identity"


class PackageContract(Contract):
    summary: Text
    method: Text
    requirements: Annotated[tuple[Text, ...], Field(min_length=1, max_length=32)]
    limitations: Annotated[tuple[Text, ...], Field(min_length=1, max_length=32)]
    inputs: Annotated[tuple[PackagePort, ...], Field(min_length=1, max_length=32)]
    outputs: Annotated[tuple[PackagePort, ...], Field(min_length=1, max_length=64)]
    request_schema: dict
    execution: ExecutionCapability | None = None

    @model_validator(mode="after")
    def validate_file_ports(self):
        """首期文件执行协议限定必填 JSON 对象端口。"""
        for ports in (self.inputs, self.outputs):
            if len({port.code for port in ports}) != len(ports):
                raise ValueError(
                    "Package port codes must be unique within their direction"
                )
        if any(port.output_view is not None for port in self.inputs):
            raise ValueError("Package input ports cannot declare output views")
        if self.execution:
            self.execution.validate_bindings(
                self.request_schema,
                {p.code for p in self.inputs},
                {p.code for p in self.outputs},
            )
        return self


class PackageArtifact(Contract):
    kind: Literal["oci_image"]
    manifest_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class PackageRuntime(Contract):
    protocol_version: Literal["1.0"]
    profile_code: Literal["offline_cpu"]


class ComponentPackageManifest(Contract):
    manifest_version: Literal["1.0", "1.1"]
    component: PackageComponent
    contract: PackageContract
    artifact: PackageArtifact
    runtime: PackageRuntime

    @model_validator(mode="after")
    def versioned_execution(self):
        """新版本声明操作，旧清单保持原合同及原规范摘要。"""
        if (self.manifest_version == "1.1") != (self.contract.execution is not None):
            raise ValueError(
                "Component execution capability requires manifest version 1.1"
            )
        return self


class ComponentPackageValidation(Contract):
    schema_version: Literal["1.0"] = "1.0"
    validation_scope: Literal["manifest_contract"] = "manifest_contract"
    component: ComponentReference
    manifest_sha256: Sha256
    execution_authorized: Literal[False] = False


class ComponentPackagePortTypes(Contract):
    """供方可从目录读取的准确 JSON 端口类型，不表达执行资格。"""

    schema_version: Literal["1.0"] = "1.0"
    items: tuple[PackageDataType, ...]
    total: int
