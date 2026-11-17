# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 21:47
# @Author  : Codex
# @File    : transport.py
"""限制第三方网络端点、响应预算与重试，并保留准确原文证据。"""

import base64
from collections.abc import Callable
from hashlib import sha256
from importlib.resources import files
import json
from time import monotonic, sleep
from urllib.parse import urlsplit

import httpx


class SourceUnavailable(RuntimeError):
    """固定提供方暂不可访问，错误不包含响应正文或调用凭据。"""


class ProviderSession:
    """一次采集共享有界连接和原文缓存，不能被研究请求修改目标端点。"""

    def __init__(self, transport: httpx.BaseTransport | None = None, *, heartbeat: Callable[[], None] | None = None):
        """允许工程验收替换传输，真实请求保留相同的端点与预算校验。"""
        self.client = httpx.Client(
            transport=transport,
            timeout=httpx.Timeout(30, connect=10),
            follow_redirects=False,
            trust_env=False,
        )
        self.cache: dict[tuple, tuple[bytes, dict]] = {}
        self.deadline = monotonic() + 600
        self.heartbeat = heartbeat
        self.last_renewed = monotonic()

    def checkpoint(self) -> None:
        """长单项下载定期续租及检查取消，不能等全部付费请求结束才发现失权。"""
        current = monotonic()
        if current >= self.deadline:
            raise SourceUnavailable("Provider acquisition exceeded its time budget")
        if self.heartbeat is not None and current-self.last_renewed >= 30:
            self.heartbeat()
            self.last_renewed = current

    def close(self) -> None:
        """释放客户端连接。"""
        self.client.close()

    def get(self, url: str, params: list[tuple[str, str]]) -> tuple[bytes, dict]:
        """仅固定公开 HTTPS 服务；限流/临时错误最多重试一次，保留原文摘要。"""
        parsed = urlsplit(url)
        configuration = json.loads(files("modarchitect.contracts").joinpath("source-provider-settings-v1.json").read_text(encoding="utf-8"))
        allowed = {urlsplit(endpoint).hostname for values in configuration["endpoints"].values() for endpoint in values}
        if (
            parsed.scheme != "https"
            or parsed.hostname not in allowed
            or parsed.query
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Provider endpoint is not registered")
        cache_key = (url, tuple(params))
        if cache_key in self.cache:
            return self.cache[cache_key]
        for attempt in range(2):
            self.checkpoint()
            try:
                with self.client.stream("GET", url, params=params) as response:
                    if response.status_code in {429, 502, 503, 504} and attempt == 0:
                        retry = response.headers.get("Retry-After", "1")
                        if not retry.isdigit() or int(retry) > 3:
                            raise SourceUnavailable(
                                "Provider retry delay exceeds the acquisition budget"
                            )
                        sleep(int(retry))
                        continue
                    if response.status_code != 200:
                        raise SourceUnavailable(
                            "Provider request failed with HTTP %s"
                            % response.status_code
                        )
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        self.checkpoint()
                        if len(raw) + len(chunk) > 2_000_000:
                            raise SourceUnavailable(
                                "Provider response exceeds its resource budget"
                            )
                        raw.extend(chunk)
                    body = bytes(raw)
                    evidence = {
                        "url": url,
                        "parameters": [[k, v] for k, v in params if k != "apikey"],
                        "sha256": sha256(body).hexdigest(),
                        "body_base64": base64.b64encode(body).decode("ascii"),
                        "content_type": response.headers.get("Content-Type", ""),
                    }
                    self.cache[cache_key] = (body, evidence)
                    return body, evidence
            except httpx.HTTPError as exc:
                if attempt:
                    raise SourceUnavailable(
                        "Provider transport is unavailable"
                    ) from exc
        raise SourceUnavailable("Provider transport is unavailable")
