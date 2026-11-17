# -*- coding: utf-8 -*-
# @Time    : 2026/10/24 20:49
# @Author  : feidu
# @File    : identity.py
"""云端验证后的企业声明和资源空间规则；声明不是本地订阅真理源。"""

from dataclasses import dataclass
from datetime import datetime


class EnterpriseAccessError(ValueError):
    """可信身份、归属或用途不满足，禁止扩大为默认平台权限。"""


def require_aware(value: datetime) -> None:
    """授权时钟必须有时区；不接受依赖机器默认时区的期限。"""
    if value.tzinfo is None or value.utcoffset() is None:
        raise EnterpriseAccessError("Authorization timestamp requires a timezone")


@dataclass(frozen=True, slots=True)
class CompanyIdentity:
    """来源保留云平台原代码；编号保留原整数，禁止布尔值和0号平台。"""

    source: str
    company_id: int

    def __post_init__(self) -> None:
        """仅约束传输边界，不把来源改写成资源ID或拼进随机UUID。"""
        if (
            not isinstance(self.source, str)
            or not self.source
            or self.source != self.source.strip()
            or len(self.source) > 128
            or "\x00" in self.source
        ):
            raise EnterpriseAccessError("Company source is invalid")
        if type(self.company_id) is not int or not 0 < self.company_id < 2**63:
            raise EnterpriseAccessError("Company identifier is invalid")


@dataclass(frozen=True, slots=True)
class VerifiedPrincipal:
    """由服务Key验证后的业务范围、受信身份端或项目签名工作区构造。"""

    company: CompanyIdentity
    subject: str
    audience: str
    policy_revision: str
    verified_at: datetime
    expires_at: datetime

    def validate(
        self, *, audience: str, now: datetime, company: CompanyIdentity | None = None
    ) -> None:
        """验证接收者、期限及正文公司一致性，失败不触发资源读取。"""
        for value in (now, self.verified_at, self.expires_at):
            require_aware(value)
        if (
            not self.subject
            or not isinstance(self.policy_revision, str)
            or not self.policy_revision
            or self.audience != audience
        ):
            raise EnterpriseAccessError("Verified principal audience or policy differs")
        if not self.verified_at <= now < self.expires_at:
            raise EnterpriseAccessError(
                "Verified principal is expired or not yet valid"
            )
        if company is not None and company != self.company:
            raise EnterpriseAccessError(
                "Requested company differs from verified principal"
            )
