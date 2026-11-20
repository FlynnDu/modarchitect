# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 16:14
# @Author  : Codex
# @File    : test_design_api.py
"""通过 HTTP 验收历史合同、设计发布、租户隔离和实时点位核权。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
from threading import Thread
import time
from uuid import uuid4

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from modarchitect.api import create_app
from modarchitect.business import BusinessGateway, BusinessSettings

FILES = Path(__file__).parents[1] / "coding/model-designer-fixtures"
ROOT = "/api/v1/research"
CATALOG = "/api/v1/model-center"
AUTH = {
    "X-MLGrowth-Business-Key": "engineering-only",
    "X-Enterprise-Delegation": "owner",
}
GEOMETRY = {
    "type": "Polygon",
    "coordinates": [[[116, 39], [117, 39], [117, 40], [116, 39]]],
}
SELECTION = {
    "geometry": GEOMETRY,
    "crop_code": "wheat",
    "season_start": "2025-04-01",
    "season_end": "2025-08-10",
}


def test_designer_assets_revalidate_browser_cache_without_affecting_api():
    """更新后静态模块必须重新校验；304仍保留缓存规则，API协议不受影响。"""
    with TestClient(create_app()) as client:
        for path in ("/designer/", "/designer/schema-fields.js", "/designer/request-schema.js"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers.get("cache-control") == "no-cache"
            cached = client.get(path, headers={"If-None-Match": response.headers["etag"]})
            assert cached.status_code == 304
            assert cached.headers.get("cache-control") == "no-cache"
        assert client.get("/api/v1/workspace/study-templates").status_code == 200


def test_platform_template_reads_use_service_key_without_company_scope():
    """业务模式按公共目录查询，企业参数与 OpenAPI 均不参与模板检索。"""
    key = {"X-Modarchitect-Api-Key": "template-read-test-key"}
    with TestClient(create_app(api_key=key["X-Modarchitect-Api-Key"], authentication_mode="api_key")) as client:
        paths = client.get("/openapi.json").json()["paths"]
        for suffix, parameters in (("", set()), ("/crop-growth-prediction", {"template_id", "sha256"})):
            path = ROOT + "/study-templates" + suffix
            result = client.get(path, headers=key)
            assert result.status_code == 200
            assert client.get(path).status_code == 401
            assert client.get(path, headers={"X-Modarchitect-Api-Key": "wrong"}).status_code == 401
            for company_id in (1, 2):
                scoped = client.get(path, headers=key, params={"provider_name": "test-catalog", "company_id": company_id})
                assert scoped.status_code == 200 and scoped.json() == result.json()
            schema_path = ROOT + "/study-templates" + ("/{template_id}" if suffix else "")
            operation = paths[schema_path]["get"]
            assert {item["name"] for item in operation.get("parameters", [])} == parameters
            assert {"ModarchitectApiKey": []} in operation["security"]
        definition = result.json()
        assert "bundles" not in definition
        exact = client.get(path, headers=key, params={"sha256": definition["sha256"]})
        assert exact.json() == definition
        assert client.get(path, headers=key, params={"sha256": "0" * 64}).status_code == 404


def fit_file(revision: int = 4) -> dict:
    """读取迁移基线固定的实际文件。"""
    return json.loads((FILES / ("research-fit-v%s.json" % revision)).read_bytes())


def new_draft(client: TestClient, definition: dict) -> dict:
    """让实际 API 生成草稿和摘要。"""
    response = client.post(
        ROOT + "/configurations/draft", json=definition, headers=AUTH
    )
    assert response.status_code == 200, response.text
    return response.json()


def create_draft(
    client: TestClient, configuration: dict, key: str | None = None
) -> httpx.Response:
    """使用固定授权上下文创建草稿。"""
    return client.post(
        ROOT + "/design-drafts",
        json=configuration,
        headers={**AUTH, "Idempotency-Key": key or str(uuid4())},
    )


def test_import_keeps_exact_v3_and_v4_and_tampering_fails() -> None:
    """历史定义可解析，篡改载荷后原摘要失效。"""
    with TestClient(create_app(business_key=AUTH["X-MLGrowth-Business-Key"], authentication_mode="delegation")) as client:
        for revision in (3, 4):
            value = fit_file(revision)
            imported = client.post(
                ROOT + "/configurations/import", json=value, headers=AUTH
            )
            assert imported.status_code == 200, imported.text
            assert imported.json() == value
            component = client.get(
                CATALOG + "/components/logistic_growth_curve",
                params={"revision": revision},
            )
            assert component.status_code == 200
            assert component.json()["available_for_new_design"] == (revision == 4)
            value["definition"]["name"] = "Tampered"
            rejected = client.post(
                ROOT + "/configurations/import", json=value, headers=AUTH
            )
            assert rejected.status_code == 422


def test_validation_locates_wrong_logistic_axis_and_preserves_layout_identity() -> None:
    """画布布局与科学身份独立，错误单位定位到绑定字段。"""
    with TestClient(create_app(business_key=AUTH["X-MLGrowth-Business-Key"], authentication_mode="delegation")) as client:
        plan = fit_file()["definition"]
        baseline = client.post(ROOT + "/plans/validate", json=plan, headers=AUTH)
        assert baseline.status_code == 200, baseline.text
        plan["layout"] = {"method": {"x": 42}}
        after = client.post(ROOT + "/plans/validate", json=plan, headers=AUTH)
        assert after.json()["plan_sha256"] == baseline.json()["plan_sha256"]
        plan["variables"][0]["unit"] = "cm"
        response = client.post(
            ROOT + "/configurations/check", json=new_draft(client, plan), headers=AUTH
        )
        issue = response.json()["issues"][0]
        assert (issue["node"], issue["port"], issue["path"][-1]) == (
            "method",
            "observations",
            "x_code",
        )


def test_responsible_user_reference_round_trips_without_changing_scientific_identity() -> None:
    """业务用户ID随配置往返，人员调整不改变科学身份，非法引用准确定位。"""
    with TestClient(create_app(api_key="responsible-reference")) as client:
        headers = {"X-Modarchitect-Api-Key": "responsible-reference"}
        definition = fit_file()["definition"]
        baseline = client.post(ROOT + "/plans/validate", json=definition, headers=headers).json()
        definition["responsible_user_id"] = "9007199254740993"
        configuration = client.post(ROOT + "/configurations/draft", json=definition, headers=headers)
        assert configuration.status_code == 200, configuration.text
        checked = client.post(ROOT + "/configurations/check", json=configuration.json(), headers=headers).json()
        assert checked["valid"], checked
        imported = client.post(ROOT + "/configurations/import", json=configuration.json(), headers=headers)
        assert imported.json() == configuration.json()
        after = client.post(ROOT + "/plans/validate", json=definition, headers=headers)
        assert after.status_code == 200, after.text
        assert after.json()["plan_sha256"] == baseline["plan_sha256"]
        for value in ("", " ", " user", "user\n", "u" * 129, 123, True):
            definition["responsible_user_id"] = value
            bad = client.post(ROOT + "/configurations/draft", json=definition, headers=headers).json()
            issues = client.post(ROOT + "/configurations/check", json=bad, headers=headers).json()["issues"]
            assert issues[0]["path"] == ["responsible_user_id"]


def test_package_preflight_checks_registered_ports_and_local_schemas() -> None:
    """同一模板可预检，外部引用及未知端口被拒绝。"""
    path = FILES.parents[1] / "components/template/component.json"
    manifest = json.loads(path.read_bytes())
    manifest["artifact"]["manifest_digest"] = "sha256:" + "a" * 64
    endpoint = CATALOG + "/component-packages/validate"
    with TestClient(create_app(business_key=AUTH["X-MLGrowth-Business-Key"], authentication_mode="delegation")) as client:
        response = client.post(endpoint, json=manifest, headers=AUTH)
        assert response.status_code == 200, response.text
        assert response.json()["execution_authorized"] is False
        properties = manifest["contract"]["request_schema"]["properties"]
        properties["minimum_valid_rows"] = {
            "$ref": "https://engineering.invalid/remote-schema.json"
        }
        assert client.post(endpoint, json=manifest, headers=AUTH).status_code == 422
        properties["minimum_valid_rows"] = {"type": "integer"}
        manifest["contract"]["inputs"][0]["data_type"]["version"] = 99
        assert client.post(endpoint, json=manifest, headers=AUTH).status_code == 422


def test_enterprise_design_writes_reject_oversized_streams_before_processing() -> None:
    """配置生成和新旧保存入口统一限制实际正文，不依赖Content-Length。"""
    with TestClient(create_app(business_key=AUTH["X-MLGrowth-Business-Key"], authentication_mode="delegation")) as client:
        for method, path in (("POST", ROOT + "/design-saves"), ("POST", ROOT + "/configurations/draft"),
                             ("POST", ROOT + "/design-drafts"), ("PUT", ROOT + "/design-drafts/" + str(uuid4())),
                             ("POST", CATALOG + "/designs")):
            response = client.request(method, path, headers=AUTH,
                                      content=iter([b" " * 4_000_000, b" " * 4_000_001]))
            assert response.status_code == 413, path


def test_modarchitect_key_openapi_and_trusted_company_save(live_design_api, monkeypatch):
    """新项目只验自身Key，企业来自业务请求，范围冲突和跨企业读取均拒绝。"""
    client, _ = live_design_api
    client.app.state.authentication_mode = "api_key"

    def unexpected_identity(*args, **kwargs):
        """本部署禁止调用业务登录身份端。"""
        raise AssertionError("Identity gateway must not be called in API-key mode")

    monkeypatch.setattr(client.app.state.gateway, "identify", unexpected_identity)
    headers = {"X-Modarchitect-Api-Key": AUTH["X-MLGrowth-Business-Key"]}
    scope = {"provider_name": "biology-institute", "company_id": 17}
    definition = client.get("/designer/example.json").json()["definition"]
    configuration = client.post(ROOT + "/configurations/draft", headers=headers, json=definition)
    assert configuration.status_code == 200
    body = {**scope, "configuration": configuration.json()}
    key = str(uuid4())
    saved = client.post(ROOT + "/design-saves", headers={**headers, "Idempotency-Key": key}, json=body)
    assert saved.status_code == 200, saved.text
    for content_type in ("Application/JSON", "application/vnd.modarchitect+json"):
        typed = client.post(ROOT + "/design-saves", headers={**headers, "Content-Type": content_type,
                            "Idempotency-Key": str(uuid4())}, json=body)
        assert typed.status_code == 200, typed.text
    receipt = saved.json()
    assert client.post(ROOT + "/design-saves", headers={**headers, "Idempotency-Key": key}, json=body).json() == receipt
    path = ROOT + "/design-drafts/" + receipt["design_id"]
    assert client.get(path, headers=headers, params=scope).status_code == 200
    assert client.get(path, headers=headers, params={**scope, "company_id": 18}).status_code == 404
    assert client.get(path, headers=headers, params={**scope, "provider_name": "another-provider"}).status_code == 404
    assert client.get(path, headers=AUTH, params=scope).status_code == 401
    assert client.get(path, headers=headers).status_code == 422
    assert client.get(path, headers=headers, params={**scope, "company_id": 0}).status_code == 422
    assert client.post(ROOT + "/design-saves", params={**scope, "company_id": 18},
                       headers={**headers, "Idempotency-Key": str(uuid4())}, json=body).status_code == 422
    client.app.state.api_key = "rotated-key"
    assert client.get(path, params=scope, headers={"X-Modarchitect-Api-Key": "rotated-key"}).status_code == 200
    schema = client.get("/openapi.json").json()["components"]["securitySchemes"]["ModarchitectApiKey"]
    assert schema == {"type": "apiKey", "in": "header", "name": "X-Modarchitect-Api-Key"}


def _candidate(ref: str, *, point: bool) -> dict:
    """生成与查询匹配的业务测试地块及点位。"""
    field = {
        "unit_ref": ref,
        "kind": "field_season",
        "field_ref": ref,
        "season_ref": "season",
        "crop_code": "wheat",
        "experimental_unit_ref": ref,
        "parent_ref": None,
        "assignments": {},
    }
    units = [field]
    if point:
        units.append(
            {**field, "unit_ref": ref + "-point", "kind": "point", "parent_ref": ref}
        )
    return {
        "field_name": ref,
        "boundary_ref": "boundary-" + ref,
        "geometry": GEOMETRY,
        "context": {
            "project_ref": "project",
            "units": units,
            "season_start": SELECTION["season_start"],
            "season_end": SELECTION["season_end"],
        },
    }


@pytest.fixture
def live_design_api():
    """通过原生低权限角色访问专用数据库，业务端使用 HTTP 协议替身。"""
    url = os.getenv("MODARCHITECT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires the dedicated modarchitect PostgreSQL test database")
    state = {"second_point": False, "calls": 0, "bad_query_digest": False}

    def respond(request: httpx.Request) -> httpx.Response:
        """模拟可信业务端按原协议签发身份和候选。"""
        now = datetime.now(timezone.utc)
        freshness = {
            "verified_at": (now - timedelta(seconds=1)).isoformat(),
            "expires_at": (now + timedelta(minutes=1)).isoformat(),
        }
        body = json.loads(request.content)
        assert body["schema_version"] == "1.0"
        if request.url.path == "/identity":
            token = request.headers["X-Enterprise-Delegation"]
            if token == "revoked":
                return httpx.Response(403)
            return httpx.Response(
                200,
                json={
                    "schema_version": "1.0",
                    "decision": "allowed",
                    "principal": {
                        "company_source": "engineering",
                        "company_id": 2 if token == "other-company" else 1,
                        "subject": (
                            "other-subject" if token == "colleague" else "研究者"
                        ),
                        "audience": body["audience"],
                        "policy_revision": "1",
                        **freshness,
                    },
                },
            )
        assert request.url.path == "/selection"
        state["calls"] += 1
        digest = "0" * 64 if state["bad_query_digest"] else body["query_sha256"]
        return httpx.Response(
            200,
            json={
                "schema_version": "1.0",
                "audience": body["audience"],
                "company": body["company"],
                "subject": body["subject"],
                "query_sha256": digest,
                **freshness,
                "candidates": [
                    _candidate("field-a", point=True),
                    _candidate("field-b", point=state["second_point"]),
                ],
            },
        )

    gateway = BusinessGateway(
        BusinessSettings(
            "https://engineering.invalid/identity",
            "design",
            "identity-test",
            "https://engineering.invalid/selection",
            "business",
            "selection-test",
        ),
        transport=httpx.MockTransport(respond),
    )
    with TestClient(
        create_app(
            database_url=url,
            authentication_mode="delegation",
            business_key=AUTH["X-MLGrowth-Business-Key"],
            gateway=gateway,
        )
    ) as client:
        yield client, state


def test_draft_replay_concurrent_update_publish_and_private_reads(
    live_design_api,
) -> None:
    """同键并发只创建一次，修订冲突可见，发布和读取保留准确身份。"""
    client, _ = live_design_api
    plan = fit_file()["definition"]
    configuration = new_draft(client, plan)
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda _: create_draft(client, configuration, key), range(2))
        )
    assert sorted(response.status_code for response in responses) == [200, 201]
    draft, replay = [response.json() for response in responses]
    assert draft["design_id"] == replay["design_id"]
    path = ROOT + "/design-drafts/" + draft["design_id"]
    plan["layout"] = {"method": {"x": 5}}
    updated = new_draft(client, plan)
    change = {"expected_revision": 1, "configuration": updated}
    assert create_draft(client, updated, key).status_code == 409
    assert client.put(path, json=change, headers=AUTH).json()["revision"] == 2
    assert client.put(path, json=change, headers=AUTH).status_code == 409
    assert create_draft(client, configuration, key).json()["revision"] == 2
    assert client.get(path, headers=AUTH).json()["configuration"] == updated
    publish = {"expected_revision": 2}
    with ThreadPoolExecutor(max_workers=2) as pool:
        versions = list(
            pool.map(
                lambda _: client.post(path + "/publish", json=publish, headers=AUTH),
                range(2),
            )
        )
    assert all(version.status_code == 200 for version in versions), [
        item.text for item in versions
    ]
    assert versions[0].json() == versions[1].json()
    version_id = versions[0].json()["design_version_id"]
    exported_path = ROOT + "/design-versions/" + version_id + "/configuration"
    exported = client.get(exported_path, headers=AUTH).json()
    assert exported["definition"]["layout"] == plan["layout"]
    for token in ("other-company", "colleague"):
        headers = {**AUTH, "X-Enterprise-Delegation": token}
        assert client.get(path, headers=headers).status_code == 404
        assert client.get(exported_path, headers=headers).status_code == 404
        assert client.put(path, json=change, headers=headers).status_code == 404
    assert (
        client.get(
            path, headers={**AUTH, "X-Enterprise-Delegation": "revoked"}
        ).status_code
        == 403
    )


def test_business_save_receipt_survives_later_edits_and_association_retry(live_design_api):
    """业务登记失败后按原请求恢复，后续编辑不能改变原保存回执。"""
    client, _ = live_design_api
    plan = fit_file()["definition"]
    configuration = new_draft(client, plan)
    key = str(uuid4())
    endpoint = ROOT + "/design-saves"
    headers = {**AUTH, "Idempotency-Key": key}
    body = {"configuration": configuration}
    response = client.post(endpoint, headers=headers, json=body)
    assert response.status_code == 200, response.text
    receipt = response.json()
    assert set(receipt) == {"design_id", "revision", "configuration_sha256"}
    assert receipt["revision"] == 1
    changed = json.loads(json.dumps(plan))
    changed["question"] = "修改后的研究问题"
    update = {"design_id": receipt["design_id"], "expected_revision": 1,
              "configuration": new_draft(client, changed)}
    updated = client.post(endpoint, headers={**AUTH, "Idempotency-Key": str(uuid4())}, json=update)
    assert updated.status_code == 200 and updated.json()["revision"] == 2
    assert client.get(endpoint + "/" + key, headers=AUTH).json() == receipt
    assert client.post(endpoint, headers=headers, json=body).json() == receipt
    assert client.get(ROOT + "/design-drafts/" + receipt["design_id"], headers=AUTH).json()["revision"] == 2
    assert client.post(endpoint, headers=headers, json=update).status_code == 409


def test_business_save_concurrency_conflicts_and_owner_isolation(live_design_api):
    """同键并发只存一份，不同更新竞争不丢修改；回执不能跨主体读取。"""
    client, _ = live_design_api
    endpoint = ROOT + "/design-saves"
    configuration = new_draft(client, fit_file()["definition"])
    key = str(uuid4())
    headers = {**AUTH, "Idempotency-Key": key}
    body = {"configuration": configuration}
    before = len(client.get(ROOT + "/design-drafts", headers=AUTH).json()["items"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(endpoint, headers=headers, json=body), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert responses[0].json() == responses[1].json()
    receipt = responses[0].json()
    assert len(client.get(ROOT + "/design-drafts", headers=AUTH).json()["items"]) == before + 1
    changes = []
    for question in ("并发修改甲", "并发修改乙"):
        plan = json.loads(json.dumps(configuration["definition"]))
        plan["question"] = question
        changes.append((str(uuid4()), {"configuration": new_draft(client, plan),
                                      "design_id": receipt["design_id"], "expected_revision": 1}))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda value: client.post(endpoint,
            headers={**AUTH, "Idempotency-Key": value[0]}, json=value[1]), changes))
    assert sorted(r.status_code for r in results) == [200, 409]
    failed = next(i for i, r in enumerate(results) if r.status_code == 409)
    assert client.get(endpoint + "/" + changes[failed][0], headers=AUTH).status_code == 404
    for actor in ("other-company", "colleague"):
        other = {**AUTH, "X-Enterprise-Delegation": actor}
        assert client.get(endpoint + "/" + key, headers=other).status_code == 404
        denied = client.post(endpoint, headers={**other, "Idempotency-Key": str(uuid4())}, json=changes[0][1])
        assert denied.status_code == 404
    invalid = client.post(endpoint, headers={**AUTH, "Idempotency-Key": str(uuid4())},
                          json={**body, "design_id": receipt["design_id"]})
    assert invalid.status_code == 422


def test_enterprise_catalogs_use_business_identity_without_workspace_cookie(live_design_api, monkeypatch, tmp_path):
    """企业读取准确模板及实际训练模型，同企业其他用户也无法读取私有模型。"""
    from uuid import UUID

    from sqlalchemy import select

    from modarchitect.runtime.contracts import SavePlan, TrainingRequest
    from modarchitect.runtime.executor import execute
    from modarchitect.runtime.store import queue
    from test_research_runtime import ScientificRunner, profiles_file

    client, _ = live_design_api
    assert not client.cookies.get("modarchitect_workspace")
    listed = client.get(ROOT + "/study-templates", headers=AUTH)
    assert listed.status_code == 200 and len(listed.json()["items"]) == 20
    detail = client.get(ROOT + "/study-templates/crop-growth-prediction", headers=AUTH)
    assert detail.status_code == 200 and detail.json()["definition"]["composition"]["nodes"]
    assert "bundles" not in detail.json()
    models = client.get(ROOT + "/models", headers=AUTH)
    assert models.status_code == 200 and isinstance(models.json()["items"], list)
    assert client.get(ROOT + "/models/" + str(uuid4()), headers=AUTH).status_code == 404
    assert client.get(ROOT + "/study-templates").status_code == 401
    assert client.get(ROOT + "/study-templates", headers={**AUTH, "X-Enterprise-Delegation": "revoked"}).status_code == 403
    monkeypatch.setenv("MODARCHITECT_RUNTIME_PROFILES", str(profiles_file(tmp_path / "profiles.json")))
    owner = client.app.state.gateway.identify("owner")
    runtime = client.app.state.research_runtime
    sample = client.get("/api/v1/workspace/examples/multivariable").json()
    saved = runtime.save_plan(owner, SavePlan.model_validate({
        "definition": sample["definition"], "observations": sample["observations"], "data_kind": "synthetic",
    }), key=str(uuid4()))
    run = runtime.train(owner, TrainingRequest.model_validate({
        "design_id": saved["design_id"], "expected_revision": saved["revision"],
        "observations": sample["observations"], "data_kind": "synthetic",
    }), str(uuid4()))
    run_id = UUID(str(run["run_id"]))
    with runtime.store.store.transaction(owner) as tx:
        token = tx.connection.execute(select(queue.c.dispatch_token).where(queue.c.run_id == run_id)).scalar_one()
    claimed = runtime.store.claim(run_id, token)
    completed = runtime.store.complete(run_id, UUID(claimed["attempt_id"]), execute(claimed["input"], ScientificRunner()), None)
    assert completed["status"] == "succeeded"
    trained = runtime.store.save_model(owner, run_id, "Enterprise trained model")
    model_id = str(trained["model_id"])
    assert any(item["model_id"] == model_id for item in client.get(ROOT + "/models", headers=AUTH).json()["items"])
    reopened = client.get(ROOT + "/models/" + model_id, headers=AUTH)
    assert reopened.status_code == 200 and reopened.json()["model_json"] == trained["model_json"]
    for delegation in ("other-company", "colleague"):
        headers = {**AUTH, "X-Enterprise-Delegation": delegation}
        assert client.get(ROOT + "/models/" + model_id, headers=headers).status_code == 404
        assert all(item["model_id"] != model_id for item in client.get(ROOT + "/models", headers=headers).json()["items"])


def test_real_curl_and_business_reference_failure_recover_without_duplicate_design(live_design_api, tmp_path):
    """真实curl访问HTTP与独立研究库，业务引用事务失败后恢复同一保存结果。"""
    client, _ = live_design_api
    executable = shutil.which("curl")
    assert executable, "curl is required for business API acceptance"
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(client.app, log_level="error", access_log=False))
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    exchanges = []

    def curl(method, path, body=None, key=None, authorized=True):
        """凭据经标准输入传给curl，产物只记录路径和状态。"""
        config = []
        if authorized:
            config.extend("header = " + json.dumps(k + ": " + v) for k, v in AUTH.items())
        if key:
            config.append("header = " + json.dumps("Idempotency-Key: " + key))
        args = [executable, "--silent", "--show-error", "--noproxy", "*", "--max-time", "15",
                "--config", "-", "--request", method,
                "--write-out", "\n%{http_code}", "http://127.0.0.1:%s%s" % (port, path)]
        if body is not None:
            payload = tmp_path / ("payload-%s.json" % len(exchanges))
            payload.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
            args.extend(["--header", "Content-Type: application/json", "--data-binary", "@" + payload.as_posix()])
        result = subprocess.run(args, input="\n".join(config), text=True, encoding="utf-8", capture_output=True)
        assert result.returncode == 0, "curl transport failed"
        raw, _, status = result.stdout.rpartition("\n")
        exchanges.append({"method": method, "path": path, "status": int(status)})
        return int(status), json.loads(raw)

    try:
        assert curl("GET", ROOT + "/study-templates", authorized=False)[0] == 401
        assert curl("GET", CATALOG + "/components", authorized=False)[0] == 200
        assert curl("GET", CATALOG + "/research-inputs", authorized=False)[0] == 200
        assert curl("GET", CATALOG + "/components/logistic_growth_curve?revision=4", authorized=False)[0] == 200
        assert curl("POST", CATALOG + "/research-inputs/configure", {
            "key": "variable_source:temperature_mean_daily@1.0.0"}, authorized=False)[0] == 200
        assert curl("GET", ROOT + "/models")[0] == 200
        status, listed = curl("GET", ROOT + "/study-templates")
        assert status == 200 and len(listed["items"]) == 20
        status, study = curl("GET", ROOT + "/study-templates/crop-growth-prediction")
        assert status == 200
        status, configuration = curl("POST", ROOT + "/configurations/draft", study["definition"])
        assert status == 200
        assert curl("POST", ROOT + "/configurations/check", configuration)[0] == 200
        assert curl("POST", ROOT + "/configurations/import", configuration) == (200, configuration)
        key = str(uuid4())
        connection = sqlite3.connect(tmp_path / "business-references.sqlite")
        connection.execute("CREATE TABLE links (business_id TEXT PRIMARY KEY, request_id TEXT UNIQUE, design_id TEXT, revision INTEGER, configuration_sha256 TEXT, state TEXT, pending_payload TEXT)")
        connection.execute("INSERT INTO links (business_id, request_id, state, pending_payload) VALUES ('research-1', ?, 'pending', ?)",
                           (key, json.dumps({"configuration": configuration})))
        connection.commit()
        connection.close()  # 模拟业务进程在HTTP发送之前退出，恢复不依赖页面存活。
        connection = sqlite3.connect(tmp_path / "business-references.sqlite")
        restored_key, payload = connection.execute("SELECT request_id,pending_payload FROM links").fetchone()
        assert restored_key == key and curl("GET", ROOT + "/design-saves/" + key)[0] == 404
        status, receipt = curl("POST", ROOT + "/design-saves", json.loads(payload), restored_key)
        assert status == 200 and receipt["revision"] == 1
        values = (receipt["design_id"], receipt["revision"], receipt["configuration_sha256"])
        connection.execute("UPDATE links SET design_id=?, revision=?, configuration_sha256=?, state='saved', pending_payload=NULL WHERE business_id='research-1'", values)
        connection.rollback()  # 模拟业务关联事务未能提交，权威保存已成功。
        assert connection.execute("SELECT state,design_id FROM links").fetchone() == ("pending", None)
        assert connection.execute("SELECT pending_payload FROM links").fetchone()[0] == payload
        assert curl("GET", ROOT + "/design-saves/" + key) == (200, receipt)
        assert curl("POST", ROOT + "/design-saves", {"configuration": configuration}, key) == (200, receipt)
        connection.execute("UPDATE links SET design_id=?, revision=?, configuration_sha256=?, state='saved', pending_payload=NULL WHERE business_id='research-1'", values)
        connection.commit()
        assert connection.execute("SELECT design_id,revision,configuration_sha256 FROM links").fetchone() == values
        assert connection.execute("SELECT state,pending_payload FROM links").fetchone() == ("saved", None)
        connection.close()
        status, saved = curl("GET", ROOT + "/design-drafts/" + receipt["design_id"])
        assert status == 200 and saved["configuration"] == configuration
        assert saved["configuration_sha256"] == receipt["configuration_sha256"]
        status, drafts_list = curl("GET", ROOT + "/design-drafts")
        assert status == 200 and sum(d["design_id"] == receipt["design_id"] for d in drafts_list["items"]) == 1
        definition = saved["configuration"]["definition"]
        definition["name"] = "Updated through real HTTP"
        status, updated_configuration = curl("POST", ROOT + "/configurations/draft", definition)
        assert status == 200
        update = {"configuration": updated_configuration, "design_id": receipt["design_id"], "expected_revision": 1}
        update_key = str(uuid4())
        status, updated_receipt = curl("POST", ROOT + "/design-saves", update, update_key)
        assert status == 200 and updated_receipt["revision"] == 2
        assert curl("POST", ROOT + "/design-saves", update, update_key) == (200, updated_receipt)
        assert curl("POST", ROOT + "/design-saves", update, str(uuid4()))[0] == 409
        assert curl("GET", ROOT + "/design-saves/" + key) == (200, receipt)
        status, reopened = curl("GET", ROOT + "/design-drafts/" + receipt["design_id"])
        assert status == 200 and reopened["revision"] == 2 and reopened["configuration"] == updated_configuration
        proof = {"method": "real curl / real HTTP / isolated PostgreSQL / SQLite business-reference transaction",
                 "identity": "business identity HTTP contract adapter; not production authorization",
                 "business_database_retains_configuration_after_confirmation": False,
                 "pre_send_restart_recovered": True, "reference_failure_recovered": True,
                 "update_replay_stable": True, "stale_update_rejected": True,
                 "duplicate_designs": 0, "receipt": receipt, "exchanges": exchanges}
        evidence = Path(".ops/business-curl-acceptance.json")
        evidence.parent.mkdir(exist_ok=True)
        evidence.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()


def test_point_authorization_is_checked_for_each_field_and_rechecked_at_publish(
    live_design_api,
) -> None:
    """第二块地缺点位、响应串租户或摘要失配时均不能发布新版本。"""
    client, state = live_design_api
    plan = fit_file()["definition"]
    requirement = {
        **plan["collection_requirements"][1],
        "code": "height_collection",
        "unit_kind": "point",
        "requires_sampling_points": True,
    }
    # 附加点位变量独立于字段级拟合输入。
    plan["variables"].append(
        {**plan["variables"][1], "code": "point_height", "role": "covariate"}
    )
    plan["collection_requirements"].append(
        {**requirement, "variable_code": "point_height"}
    )
    assert create_draft(client, new_draft(client, plan)).status_code == 422
    plan["sampling_selection"] = {
        "selection": SELECTION,
        "field_refs": ["field-a", "field-b"],
    }
    configuration = new_draft(client, plan)
    missing = create_draft(client, configuration)
    assert missing.status_code == 422 and "sampling points" in missing.json()["detail"]
    state["second_point"] = True
    state["bad_query_digest"] = True
    assert create_draft(client, configuration).status_code == 503
    state["bad_query_digest"] = False
    created = create_draft(client, configuration)
    assert created.status_code == 201, created.text
    path = ROOT + "/design-drafts/" + created.json()["design_id"]
    revision = {"expected_revision": 1}
    state["second_point"] = False
    refused = client.post(path + "/publish", json=revision, headers=AUTH)
    assert (
        refused.status_code == 422 and "sampling points" in refused.json()["detail"]
    ), refused.text
    assert (
        client.put(
            path, json={**revision, "configuration": configuration}, headers=AUTH
        ).status_code
        == 422
    )
    direct = {
        "name": plan["name"],
        "revision": 1,
        "composition": plan["composition"],
        "research_plan": plan,
    }
    headers = {**AUTH, "Idempotency-Key": str(uuid4())}
    assert (
        client.post(CATALOG + "/designs", json=direct, headers=headers).status_code
        == 422
    )
    state["second_point"] = True
    published = client.post(path + "/publish", json=revision, headers=AUTH)
    assert published.status_code == 200, published.text
    state["second_point"] = False
    assert (
        client.post(path + "/publish", json=revision, headers=AUTH).json()
        == published.json()
    )


def test_legacy_direct_publication_retains_exact_version_history(
    live_design_api,
) -> None:
    """旧直接发布可重放，追加后仍可按原修订读取首版。"""
    client, _ = live_design_api
    plan = fit_file()["definition"]
    body = {
        "name": plan["name"],
        "revision": 1,
        "composition": plan["composition"],
        "research_plan": plan,
    }
    headers = {**AUTH, "Idempotency-Key": str(uuid4())}
    created = client.post(CATALOG + "/designs", json=body, headers=headers)
    assert created.status_code == 201, created.text
    v1 = created.json()
    replay = client.post(CATALOG + "/designs", json=body, headers=headers)
    assert replay.status_code == 200 and replay.json() == v1
    path = CATALOG + "/designs/" + v1["design_id"]
    next_version = {**body, "revision": 2, "description": "Second version"}
    created = client.post(path + "/versions", json=next_version, headers=AUTH)
    assert created.status_code == 201, created.text
    assert (
        client.post(path + "/versions", json=next_version, headers=AUTH).status_code
        == 200
    )
    assert client.get(path + "/versions/1", headers=AUTH).json() == v1
    history = client.get(path + "/versions", headers=AUTH).json()
    assert [item["revision"] for item in history["items"]] == [2, 1]
    listing = client.get(CATALOG + "/designs", headers=AUTH)
    assert listing.status_code == 200, listing.text
    assert any(
        item["design_version_id"] == created.json()["design_version_id"]
        for item in listing.json()["items"]
    )
