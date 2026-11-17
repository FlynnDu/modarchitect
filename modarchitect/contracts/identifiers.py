# -*- coding: utf-8 -*-
# @Time    : 2026/8/26 11:37
# @Author  : feidu
# @File    : identifiers.py
"""API 与 Worker 共用的平台标识符生成和校验规则。"""

import hashlib
import json
import secrets
import time
from typing import Any
from uuid import UUID

_MAX_UNIX_MILLISECONDS = (1 << 48) - 1


def new_uuid7(*, unix_milliseconds: int | None = None) -> UUID:
    """生成 RFC 9562 UUIDv7，不向机器主键写入任何业务语义。"""

    timestamp_ms = (
        time.time_ns() // 1_000_000 if unix_milliseconds is None else unix_milliseconds
    )
    if (
        isinstance(timestamp_ms, bool)
        or not isinstance(timestamp_ms, int)
        or not 0 <= timestamp_ms <= _MAX_UNIX_MILLISECONDS
    ):
        raise ValueError("unix_milliseconds must be a 48-bit non-negative integer")
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (
        (timestamp_ms << 80) | (0x7 << 76) | (random_a << 64) | (0b10 << 62) | random_b
    )
    return UUID(int=value)


def canonical_json(value: Any) -> str:
    """输出用于身份摘要的规范 JSON；不接受 NaN 或 Infinity。"""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def identity_sha256(value: Any) -> str:
    """计算规范身份载荷的完整 SHA-256。"""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
