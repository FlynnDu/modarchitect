# -*- coding: utf-8 -*-
# @Time    : 2026/11/17 22:46
# @Author  : Codex
# @File    : test_workspace_access.py
"""验证匿名工作区隔离与明确启用的本地单人跨浏览器回读。"""

import json
import os
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from modarchitect.api import create_app


def test_local_workspace_reopens_definition_from_new_browser_and_app(monkeypatch):
    """真实隔离库保存定义后，两个浏览器及新应用复用同一本地主体。"""
    database = os.getenv("MODARCHITECT_TEST_DATABASE_URL")
    if not database:
        pytest.skip("Requires the dedicated modarchitect PostgreSQL test database")
    monkeypatch.setenv("MODARCHITECT_WORKSPACE_KEY", "local-workspace-test-" * 4)
    monkeypatch.setenv("MODARCHITECT_LOCAL_WORKSPACE_SUBJECT", uuid4().hex)
    sample = json.loads((Path(__file__).parents[1] / "modarchitect/web/designer/calendar-study.json").read_text(encoding="utf-8"))
    app = create_app(database_url=database)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as first, TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50001)) as other:
        first_owner = first.get("/api/v1/workspace/session").json()
        other_owner = other.get("/api/v1/workspace/session").json()
        assert first_owner["workspace"] == other_owner["workspace"]
        saved = first.post("/api/v1/workspace/plans", json={"definition": sample["definition"]}, headers={"X-Workspace-Request": "1", "Idempotency-Key": str(uuid4())})
        assert saved.status_code == 200, saved.text
        record = saved.json()
        read = other.get("/api/v1/workspace/plans/" + record["design_id"])
        assert read.status_code == 200, read.text
        assert read.json()["configuration_sha256"] == record["configuration_sha256"]
        assert read.json()["observations"] is None
        assert other.post("/api/v1/workspace/models", json={"run_id": str(uuid4()), "name": "test"}).status_code == 403
        other.cookies.clear()
        other.cookies.set("modarchitect_workspace", "forged.1.signature")
        assert other.get("/api/v1/workspace/plans/" + record["design_id"]).status_code == 401
    with TestClient(create_app(database_url=database), base_url="http://127.0.0.1", client=("127.0.0.1", 50002)) as reopened:
        reopened.get("/api/v1/workspace/session").raise_for_status()
        assert reopened.get("/api/v1/workspace/plans/" + record["design_id"]).json()["configuration_sha256"] == record["configuration_sha256"]


@pytest.mark.parametrize(("subject", "base", "client_host"), [("invalid", "http://127.0.0.1", "127.0.0.1"), ("a" * 32, "https://example.org", "127.0.0.1"), ("a" * 32, "http://127.0.0.1", "192.0.2.1")])
def test_local_workspace_rejects_invalid_configuration_or_remote_host(monkeypatch, subject, base, client_host):
    """本地入口必须明确合法配置，不能通过非回环地址对外开放。"""
    monkeypatch.setenv("MODARCHITECT_WORKSPACE_KEY", "local-workspace-test-" * 4)
    monkeypatch.setenv("MODARCHITECT_LOCAL_WORKSPACE_SUBJECT", subject)
    with TestClient(create_app(), base_url=base, client=(client_host, 50000)) as client:
        assert client.get("/api/v1/workspace/session").status_code == 503


def test_default_workspace_keeps_browsers_separate(monkeypatch):
    """正式默认行为继续为两个独立匿名会话分配不同主体。"""
    monkeypatch.delenv("MODARCHITECT_LOCAL_WORKSPACE_SUBJECT", raising=False)
    monkeypatch.setenv("MODARCHITECT_WORKSPACE_KEY", "local-workspace-test-" * 4)
    app = create_app()
    with TestClient(app) as first, TestClient(app) as other:
        assert first.get("/api/v1/workspace/session").json()["workspace"] != other.get("/api/v1/workspace/session").json()["workspace"]
