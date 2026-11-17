# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 16:11
# @Author  : Codex
# @File    : settings.py
"""投影实际取数所需环境项，不执行脚本、不导入旧应用配置或个人账户。"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib.resources import files
import json
import re
import shlex
from types import MappingProxyType
from urllib.parse import urlsplit

from .transport import SourceUnavailable

ENVIRONMENT_GROUPS = {
    "sentinelhub_s2_l2a": frozenset({"SH_CLIENT_ID", "SH_CLIENT_SECRET", "SH_BASE_URL", "SH_TOKEN_URL", "SH_PROFILE"}),
    "openmeteo_archive": frozenset({"MODARCHITECT_OPENMETEO_KEY", "MODARCHITECT_WEATHER_ACCESS", "MODARCHITECT_OPENMETEO_ARCHIVE_URL", "MODARCHITECT_OPENMETEO_CUSTOMER_ARCHIVE_URL"}),
    "soilgrids_wcs": frozenset({"MODARCHITECT_SOIL_WCS_BASE_URL"}),
}
SOURCE_ENVIRONMENT_KEYS = frozenset().union(*ENVIRONMENT_GROUPS.values())


def environment_keys(adapters: frozenset[str]) -> frozenset[str]:
    """只读取本次真实采用的提供方设置，其他账户缺失不影响独立来源。"""
    if adapters-set(ENVIRONMENT_GROUPS):
        raise SourceUnavailable("Source environment contract is not registered")
    return frozenset().union(*(ENVIRONMENT_GROUPS[code] for code in adapters))


def provider_configuration() -> dict:
    """公开提供方默认地址集中登记，部署可选获准地址，科学合同不由URL改写。"""
    return json.loads(files("modarchitect.contracts").joinpath("source-provider-settings-v1.json").read_text(encoding="utf-8"))


@dataclass(frozen=True)
class SourceSettings:
    """每次采集独立的只读配置；异常和repr均不含账户值。"""

    values: Mapping[str, str] = field(repr=False)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "SourceSettings":
        """只取明确允许的取数项，旧PG、OSS及业务端点不进入执行上下文。"""
        selected = {key: value for key, value in values.items() if key in SOURCE_ENVIRONMENT_KEYS and value}
        if any(not isinstance(value, str) or len(value) > 8192 or "\x00" in value for value in selected.values()):
            raise SourceUnavailable("Source environment values are invalid")
        return cls(MappingProxyType(selected))

    @classmethod
    def from_exports(cls, content: str, names: frozenset[str] | None = None) -> "SourceSettings":
        """仅解析静态赋值，不执行export、命令替换或读取环境里的其他服务配置。"""
        selected = {}
        allowed = SOURCE_ENVIRONMENT_KEYS if names is None else SOURCE_ENVIRONMENT_KEYS & names
        if len(content) > 1_000_000:
            raise SourceUnavailable("Source environment exceeds its byte budget")
        for line in content.splitlines():
            match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$", line)
            if match is None or match[1] not in allowed:
                continue
            expression = match[2].strip()
            if not expression.startswith("'") and any(mark in expression for mark in ("$", "`")):
                raise SourceUnavailable("Source environment requires literal account settings")
            try:
                parts = shlex.split(expression, comments=True) if expression else [""]
            except ValueError as exc:
                raise SourceUnavailable("Source environment assignment is invalid") from exc
            if len(parts) != 1 or match[1] in selected:
                raise SourceUnavailable("Source environment assignment is missing or ambiguous")
            selected[match[1]] = parts[0]
        return cls.from_mapping(selected)

    def get(self, name: str) -> str | None:
        """适配器显式请求自身配置，不向调用者返回整个环境。"""
        return self.values.get(name)

    def endpoint(self, name: str) -> str:
        """地址必须属于该提供方登记范围，不能通过环境变量静默更换科学来源。"""
        config = provider_configuration()
        value = self.values.get(name) or config["defaults"].get(name)
        allowed = config["endpoints"].get(name)
        if not value or not allowed:
            raise SourceUnavailable("Source provider endpoint is not configured")
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment or value.rstrip("/") not in allowed:
            raise SourceUnavailable("Source provider endpoint is not adopted")
        return value.rstrip("/")
