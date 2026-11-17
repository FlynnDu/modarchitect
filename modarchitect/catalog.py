# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 16:03
# @Author  : Codex
# @File    : catalog.py
"""从安装制品提供可校验的首批组件目录及新设计采用规则。"""

from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
import json

from .contracts.identifiers import identity_sha256
from .contracts.model_center.components import ComponentDefinition


class CatalogConflict(ValueError):
    """组件代码与版本已被目录占用。"""


def research_request_schema(definition: ComponentDefinition) -> dict | None:
    """兼容原生工具和研究模型两种已冻结配置位置。"""
    config = definition.configuration
    return config.get("research_model", {}).get("request_schema", config.get("request_schema"))


@dataclass(frozen=True)
class ComponentVersion:
    """准确合同和独立的新设计采用资格。"""

    definition: ComponentDefinition
    contract_sha256: str
    available_for_new_design: bool

    def record(self) -> dict:
        """输出目录合同和表单所需的准确请求 Schema。"""
        from .execution_contracts import execution_capability

        definition = self.definition
        configuration = definition.configuration
        capability = execution_capability({"code": definition.code, "revision": definition.revision})
        return {
            "definition": definition.model_dump(mode="json"),
            "contract_sha256": self.contract_sha256,
            "available_for_new_design": self.available_for_new_design,
            "research_contract": {
                "request_schema": research_request_schema(definition),
                "execution": {"status": "design_only"},
                "input_uses": capability.model_dump(mode="json")["input_uses"] if capability else {},
            },
            "designer": configuration.get("designer"),
        }


def frozen_contracts() -> list[dict]:
    """读取初始迁移使用的版本化原始定义。"""
    resource = files("modarchitect").joinpath(
        "contracts", "logistic-growth-contracts-v1.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))


def regression_contract() -> dict:
    """读取独立回归组件的第一版冻结定义。"""
    resource = files("modarchitect").joinpath(
        "contracts", "multivariate-regression-v1.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))


def chain_contracts() -> list[dict]:
    """读取串联预测与合并节点的第一版冻结合同。"""
    resource = files("modarchitect").joinpath("contracts", "chain-components-v1.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def runtime_contracts() -> list[dict]:
    """读取训练状态与独立推理组件的准确合同。"""
    resource = files("modarchitect").joinpath("contracts", "runtime-components-v1.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def analysis_contracts() -> list[dict]:
    """读取声明非训练操作的独立分析组件合同。"""
    resource = files("modarchitect").joinpath(
        "contracts", "analysis-components-v1.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))


def native_contracts() -> list[dict]:
    """迁入已冻结科学制品的原合同，保持原定义和摘要。"""
    resource = files("modarchitect.contracts").joinpath("native-study-components-v1.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def agronomic_contracts() -> list[dict]:
    """读取可分别研究气象条件和指标过程的准确合同。"""
    resource = files("modarchitect.contracts").joinpath("agronomic-research-components-v1.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def field_research_contracts() -> list[dict]:
    """新增标准输入方法单独登记，既有科学合同和历史采用身份保持。"""
    resource = files("modarchitect.contracts").joinpath("field-research-components-v1.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def tabular_learning_contracts() -> list[dict]:
    """读取标准观测表的回归训练及独立推理合同，保留旧评估身份。"""
    resource = files("modarchitect.contracts").joinpath("tabular-learning-components-v1.json")
    return json.loads(resource.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def catalog() -> dict[tuple[str, int], ComponentVersion]:
    """以稳定代码与修订索引版本，同时验证制品中的定义。"""
    rows = [
        *frozen_contracts(),
        regression_contract(),
        *chain_contracts(),
        *runtime_contracts(),
        *analysis_contracts(),
        *native_contracts(),
        *agronomic_contracts(),
        *field_research_contracts(),
        *tabular_learning_contracts(),
    ]
    latest: dict[str, int] = {}
    for row in rows:
        latest[row["code"]] = max(row["revision"], latest.get(row["code"], 0))
    entries = {}
    for row in rows:
        definition = ComponentDefinition.model_validate(row)
        identity = (definition.code, definition.revision)
        if identity in entries:
            raise ValueError("Duplicate component version")
        entries[identity] = ComponentVersion(
            definition,
            identity_sha256(row),
            latest[definition.code] == definition.revision,
        )
    return entries


def component(code: str, revision: int | None = None) -> ComponentVersion:
    """解析准确版本或当前采用版本。"""
    if revision is None:
        entry = next(
            (
                entry
                for (key, _), entry in catalog().items()
                if key == code and entry.available_for_new_design
            ),
            None,
        )
    else:
        entry = catalog().get((code, revision))
    if entry is None:
        raise LookupError("Component version was not found")
    return entry
