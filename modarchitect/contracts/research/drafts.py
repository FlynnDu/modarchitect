# -*- coding: utf-8 -*-
# @Time    : 2026/11/4 23:56
# @Author  : feidu
# @File    : drafts.py
"""未完成研究配置的无执行导入合同；完整科学校验只在检查或发布时执行。"""

from modarchitect.contracts.identifiers import canonical_json, identity_sha256
from .plans import ResearchPlan


def draft_file(definition: dict) -> dict:
    """只接受研究字段和有限JSON，不接收部署凭据，不加载任何导入路径。"""
    if not set(definition) <= set(ResearchPlan.model_fields):
        raise ValueError("Research draft contains unknown top-level fields")

    def check(value):
        """逐层检查配置字段，拒绝把部署凭据存入方案文件。"""
        if isinstance(value, dict):
            if {str(k).casefold() for k in value} & {
                "password",
                "secret",
                "access_token",
                "authorization",
                "service_key",
                "api_key",
            }:
                raise ValueError(
                    "Research configuration cannot contain service credentials"
                )
            for child in value.values():
                check(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                check(child)

    try:
        check(definition)
        body = {"format": "research_plan_draft", "definition": definition}
        size = len(canonical_json(body).encode("utf-8"))
    except (RecursionError, UnicodeError) as exc:
        raise ValueError(
            "Research draft contains invalid or excessive nesting"
        ) from exc
    if size > 1000000:
        raise ValueError("Research draft exceeds its size budget")
    return {**body, "sha256": identity_sha256(body)}


def import_draft(value: dict) -> dict:
    """校验文件完整性，但缺字段和未知组件仍作为草稿保留，绝不静默升级。"""
    if (
        set(value) != {"format", "definition", "sha256"}
        or value["format"] != "research_plan_draft"
        or not isinstance(value["definition"], dict)
    ):
        raise ValueError("Research draft file format differs")
    expected = draft_file(value["definition"])
    if expected != value:
        raise ValueError("Research draft file checksum differs")
    return expected
