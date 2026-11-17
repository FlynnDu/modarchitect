# -*- coding: utf-8 -*-
# @Time    : 2026/11/16 15:52
# @Author  : Codex
# @File    : business_scope.py
"""声明可信业务后端传递的企业范围，不重复业务用户登录资料。"""

from typing import Annotated

from pydantic import Field, model_validator

from ..model_center.components import Contract
from .identity import CompanyIdentity


class BusinessScope(Contract):
    """服务Key验证后采用的企业来源与正整数编号。"""

    provider_name: Annotated[str, Field(min_length=1, max_length=128)]
    company_id: Annotated[int, Field(strict=True, gt=0, lt=2**63)]

    @model_validator(mode="after")
    def valid_identity(self):
        """复用数据库主体采用的企业身份不变量。"""
        CompanyIdentity(self.provider_name, self.company_id)
        return self
