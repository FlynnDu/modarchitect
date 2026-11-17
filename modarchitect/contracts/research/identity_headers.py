# -*- coding: utf-8 -*-
# @Time    : 2026/11/05 02:02
# @Author  : feidu
# @File    : identity_headers.py
"""不改写上游用户标识；HTTP头用显式UTF-8编码传送任意合法opaque ID。"""

import base64
import binascii

SUBJECT_ENCODING = "base64url_utf8"


def validate_subject(subject: str) -> str:
    """数据库、CLI和HTTP共用边界；保留原值，拒绝空白、NUL和非法Unicode。"""
    if (
        not isinstance(subject, str)
        or not subject.strip()
        or len(subject) > 256
        or "\x00" in subject
    ):
        raise ValueError("Research subject is invalid")
    try:
        subject.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("Research subject is invalid") from exc
    return subject


def encode_subject(subject: str) -> str:
    """无填充的规范base64url，身份只在编码前后校验而不归一化。"""
    return (
        base64.urlsafe_b64encode(validate_subject(subject).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )


def decode_subject(value: str, encoding: str | None) -> str:
    """兼容已有plain头；未知编码和非规范值拒绝，避免ID前缀误判。"""
    if encoding is None:
        return validate_subject(value)
    if encoding != SUBJECT_ENCODING or len(value) > 2048:
        raise ValueError("Research subject encoding is invalid")
    try:
        raw = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
        subject = validate_subject(raw.decode("utf-8"))
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise ValueError("Research subject encoding is invalid") from exc
    if encode_subject(subject) != value:
        raise ValueError("Research subject encoding is not canonical")
    return subject
