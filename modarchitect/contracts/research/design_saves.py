# -*- coding: utf-8 -*-
# @Time    : 2026/11/16 14:38
# @Author  : Codex
# @File    : design_saves.py
"""定义企业方案保存请求与可用于业务关联的最小回执。"""

from typing import Annotated
from unicodedata import normalize
from uuid import UUID

from pydantic import AliasChoices, BeforeValidator, Field, model_validator

from ..model_center.components import Contract
from ..enterprise.business_scope import BusinessScope


def _clean_version_name(value: object) -> object:
    """版本名使用规范化的单行文本，留空由平台分配。"""
    if not isinstance(value, str):
        return value
    value = normalize("NFC", value.strip())
    if value and not value.isprintable():
        raise ValueError("Version name must be a single line of printable text")
    return value or None


VersionName = Annotated[
    Annotated[str, Field(strict=True, min_length=1, max_length=128)] | None,
    BeforeValidator(_clean_version_name),
]


class DesignSave(Contract):
    """新建只传配置，更新必须同时指定方案和预期修订。"""

    configuration: dict
    version_name: VersionName = Field(default=None, validation_alias=AliasChoices("version_name", "version"))
    design_id: UUID | None = None
    expected_revision: Annotated[int, Field(strict=True, ge=1)] | None = None
    provider_name: str | None = None
    company_id: Annotated[int, Field(strict=True, gt=0, lt=2**63)] | None = None

    @model_validator(mode="after")
    def update_identity(self):
        """拒绝含糊的创建或更新，不以默认修订覆盖并发修改。"""
        if (self.design_id is None) != (self.expected_revision is None):
            raise ValueError("Design updates require both design_id and expected_revision")
        if (self.provider_name is None) != (self.company_id is None):
            raise ValueError("Business scope requires provider_name and company_id")
        if self.provider_name is not None:
            BusinessScope(provider_name=self.provider_name, company_id=self.company_id)
        return self


class DesignReference(Contract):
    """确认准确保存修订；不重复请求ID、配置正文或外部关联状态。"""

    design_id: UUID
    revision: Annotated[int, Field(strict=True, ge=1)]
    configuration_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
