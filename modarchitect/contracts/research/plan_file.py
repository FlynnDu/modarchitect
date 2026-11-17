# -*- coding: utf-8 -*-
# @Time    : 2026/11/4 22:35
# @Author  : feidu
# @File    : plan_file.py
"""保存研究方案的版本化配置格式和科学身份。"""

from modarchitect.contracts.identifiers import identity_sha256
from .plans import CollectionRequirement, ResearchPlan


def plan_sha256(plan: ResearchPlan) -> str:
    """科学身份排除画布布局；导入文件完整性另对完整文件计算。"""
    return identity_sha256(plan_payload(plan, include_layout=False))


def plan_payload(plan: ResearchPlan, *, include_layout: bool = True) -> dict:
    """旧1.0不因新可选字段默认值而改变原科学身份或导出格式。"""
    result = plan.model_dump(mode="json")
    result["collection_requirements"] = [
        requirement_payload(requirement) for requirement in plan.collection_requirements
    ]
    if plan.sampling_selection is None:
        result.pop("sampling_selection")
    if plan.schema_version == "1.0":
        result["evaluation"].pop("numeric_gate", None)
    if not include_layout:
        result.pop("layout", None)
    if not include_layout or result["report"] is None:
        result.pop("report")
    return result


def requirement_payload(requirement: CollectionRequirement) -> dict:
    """未选择新来源的历史模板不新增null键，保留原字节语义与摘要。"""
    value = requirement.model_dump(mode="json")
    if requirement.catalog_binding is None:
        value.pop("catalog_binding", None)
    if requirement.requires_sampling_points is None:
        value.pop("requires_sampling_points", None)
    return value


def export_plan(plan: ResearchPlan) -> dict:
    """导出同源配置，不携带真实观测、业务凭据或继承访问权限。"""
    content = {"format": "research_plan", "definition": plan_payload(plan)}
    return {**content, "sha256": identity_sha256(content)}


def import_plan(payload: dict) -> ResearchPlan:
    """按准确格式和摘要恢复设计，不静默升级组件版本或执行任何代码。"""
    if (
        set(payload) != {"format", "definition", "sha256"}
        or payload["format"] != "research_plan"
    ):
        raise ValueError("Research configuration format differs")
    content = {key: payload[key] for key in ("format", "definition")}
    if identity_sha256(content) != payload["sha256"]:
        raise ValueError("Research configuration checksum differs")
    return ResearchPlan.model_validate(payload["definition"])
