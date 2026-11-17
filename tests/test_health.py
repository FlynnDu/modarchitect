# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 15:31
# @Author  : Codex
# @File    : test_health.py
"""验证安装后的模型设计服务可响应存活检查。"""

import asyncio

import httpx

from modarchitect.api import app


def test_health_returns_ok() -> None:
    """通过 HTTP 入口取得稳定的存活响应。"""
    async def request_health() -> httpx.Response:
        """通过 ASGI HTTP 传输调用已装配的应用。"""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.get("/health")

    response = asyncio.run(request_health())
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
