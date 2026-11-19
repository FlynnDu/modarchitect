# -*- coding: utf-8 -*-
# @Time    : 2026/11/19 20:58
# @Author  : Codex
# @File    : test_draft_lifecycle.py
"""发布关闭当前草稿，显式新草稿的编辑不改变旧版本和研究引用。"""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from modarchitect.contracts.enterprise.identity import CompanyIdentity, VerifiedPrincipal

from test_api_design_loop import API
from test_api_design_loop import business_client as business_client


def saved_version(client, scope):
    """通过业务正式保存和发布建立可复用版本。"""
    plan = client.get(API + "/study-templates/crop-growth-prediction").raise_for_status().json()["definition"]
    configuration = client.post(API + "/configurations/draft", json=plan).raise_for_status().json()
    receipt = client.post(API + "/design-saves", headers={"Idempotency-Key": str(uuid4())},
                          json={**scope, "configuration": configuration}).raise_for_status().json()
    path = API + "/design-drafts/" + receipt["design_id"]
    version = client.post(path + "/publish", params=scope,
                          json={"expected_revision": receipt["revision"]}).raise_for_status().json()
    return path, receipt, version


def test_published_configuration_requires_explicit_new_draft(business_client):
    """发布关闭后拒绝原草稿写入，新草稿和新版本保留原版本完整内容。"""
    client, scope = business_client
    path, receipt, original = saved_version(client, scope)
    current = client.get(path, params=scope).raise_for_status().json()
    changed = current["configuration"]
    changed["definition"]["name"] = "新草稿里的改名"
    changed = client.post(API + "/configurations/draft", json=changed["definition"]).raise_for_status().json()
    update = {**scope, "design_id": receipt["design_id"], "expected_revision": receipt["revision"], "configuration": changed}
    denied = client.post(API + "/design-saves", headers={"Idempotency-Key": str(uuid4())}, json=update)
    assert denied.status_code == 409, denied.text
    assert current["draft_state"] == "published"
    assert current["published_version_id"] == original["design_version_id"]
    key = str(uuid4())
    endpoint = API + "/design-versions/" + original["design_version_id"] + "/drafts"
    opened = client.post(endpoint, params=scope, headers={"Idempotency-Key": key}).raise_for_status().json()
    assert opened["draft_id"] != current["draft_id"]
    assert opened["base_version_id"] == original["design_version_id"]
    assert opened["revision"] > receipt["revision"]
    assert client.post(endpoint, params=scope, headers={"Idempotency-Key": key}).json() == opened
    update["expected_revision"] = opened["revision"]
    saved = client.post(API + "/design-saves", headers={"Idempotency-Key": str(uuid4())}, json=update).raise_for_status().json()
    second = client.post(path + "/publish", params=scope,
                         json={"expected_revision": saved["revision"]}).raise_for_status().json()
    assert second["design_version_id"] != original["design_version_id"]
    assert second["definition"]["research_plan"]["name"] == "新草稿里的改名"
    assert client.get(API + "/design-versions/" + original["design_version_id"], params=scope).json() == original
    assert client.post(endpoint, params=scope, headers={"Idempotency-Key": key}).json() == opened
    assert client.get(path, params=scope).json()["draft_state"] == "published"


def test_database_rejects_closed_draft_rewrite_and_session_reopen(business_client):
    """应用角色直接写库同样不能改正式配置、重开旧草稿或修改正式版本。"""
    client, scope = business_client
    _, receipt, version = saved_version(client, scope)
    now = datetime.now(timezone.utc)
    owner = VerifiedPrincipal(CompanyIdentity(scope["provider_name"], scope["company_id"]),
                              "business_api", "modarchitect_api", "api_key_v1", now, now + timedelta(minutes=10))
    store = client.app.state.design_service.store
    statements = [
        "UPDATE research_design_drafts SET revision=revision+1 WHERE design_id=:design",
        "UPDATE research_design_draft_sessions SET published_version_id=NULL,closed_at=NULL WHERE design_id=:design",
    ]
    for statement in statements:
        with pytest.raises(IntegrityError):
            with store.transaction(owner) as tx:
                tx.connection.execute(text(statement), {"design": receipt["design_id"]})
    assert client.get(API + "/design-versions/" + version["design_version_id"], params=scope).json() == version


def test_new_draft_is_idempotent_exclusive_and_requires_original_company(business_client):
    """并发开启只有一个活动草稿，旧请求重放不会重新开启已关闭草稿。"""
    client, scope = business_client
    path, receipt, version = saved_version(client, scope)
    endpoint = API + "/design-versions/" + version["design_version_id"] + "/drafts"
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda _: client.post(endpoint, params=scope, headers={"Idempotency-Key": key}), range(2)))
    assert all(reply.status_code == 200 for reply in replies), [reply.text for reply in replies]
    assert replies[0].json() == replies[1].json()
    opened = replies[0].json()
    assert client.post(endpoint, params=scope, headers={"Idempotency-Key": str(uuid4())}).status_code == 409
    assert client.post(endpoint, params={**scope, "company_id": 2}, headers={"Idempotency-Key": key}).status_code == 404
    new_version = client.post(path + "/publish", params=scope,
                             json={"expected_revision": opened["revision"]}).raise_for_status().json()
    assert new_version["design_version_id"] != version["design_version_id"]
    assert new_version["definition"]["research_plan"] == version["definition"]["research_plan"]
    assert client.get(API + "/design-versions/" + version["design_version_id"], params=scope).json() == version
    assert client.post(path + "/publish", params=scope, json={"expected_revision": opened["revision"]}).json() == new_version
    assert client.get(path, params=scope).json()["draft_state"] == "published"
