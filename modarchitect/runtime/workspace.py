# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 21:15
# @Author  : Codex
# @File    : workspace.py
"""为独立项目的自有数据工作区签发和核验持久 Cookie。"""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import re
import time
from uuid import uuid4

from fastapi import HTTPException, Request, Response

from ..contracts.enterprise.identity import CompanyIdentity, VerifiedPrincipal

COOKIE = "modarchitect_workspace"
MAX_AGE = 365 * 24 * 60 * 60


def signing_key() -> bytes:
    """签名密钥只来自部署环境，缺配置时关闭工作区入口。"""
    key = os.getenv("MODARCHITECT_WORKSPACE_KEY", "")
    if len(key) < 32:
        raise HTTPException(503, "Workspace identity is not configured")
    return key.encode("utf-8")


def principal(token: str) -> VerifiedPrincipal:
    """核对服务器签名和期限后形成仅属本地工作区的可信主体。"""
    try:
        subject, issued, signature = token.split(".")
        message = (subject + "." + issued).encode("ascii")
        expected = hmac.new(signing_key(), message, hashlib.sha256).hexdigest()
        if (
            not re.fullmatch(r"[a-f0-9]{32}", subject)
            or not hmac.compare_digest(signature, expected)
            or not 0 <= time.time() - int(issued) < MAX_AGE
        ):
            raise ValueError("Invalid workspace identity")
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(401, "Workspace session has expired") from exc
    now = datetime.now(timezone.utc)
    return VerifiedPrincipal(
        CompanyIdentity("modarchitect_workspace", 1),
        subject,
        "modarchitect_workspace",
        "signed_cookie_v1",
        now,
        now + timedelta(minutes=10),
    )


def session(request: Request, response: Response) -> dict:
    """重新访问时复用个人空间，首次访问只创建无企业权限的空间。"""
    token = request.cookies.get(COOKIE)
    if not token:
        message = uuid4().hex + "." + str(int(time.time()))
        signature = hmac.new(
            signing_key(), message.encode("ascii"), hashlib.sha256
        ).hexdigest()
        token = message + "." + signature
    owner = principal(token)
    response.set_cookie(
        COOKIE,
        token,
        max_age=MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )
    return {
        "workspace": owner.subject,
        "data_scope": "user_supplied",
        "persistent": True,
    }


def owner(request: Request) -> VerifiedPrincipal:
    """所有工作区写操作要求同源自定义请求头，避免跨站表单提交。"""
    if request.method != "GET" and request.headers.get("X-Workspace-Request") != "1":
        raise HTTPException(403, "A workspace request header is required")
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Open the workspace session first")
    return principal(token)
