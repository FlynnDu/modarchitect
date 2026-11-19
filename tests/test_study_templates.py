# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 16:08
# @Author  : Codex
# @File    : test_study_templates.py
"""验证现成方案的真实依赖、来源边界及原生输入封存，保留历史训练接口。"""

from copy import deepcopy
import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from modarchitect.api import create_app
from modarchitect.catalog import catalog
from modarchitect.contracts.research.plans import ResearchPlan
from modarchitect.execution_contracts import compile_execution
from modarchitect.runtime.containers import Artifact, ContainerRunner, archive, invocation_files
from modarchitect.runtime.executor import execute
from modarchitect.study_templates import _template_rows, frozen_inputs, matches_template, template, templates, template_view, validate_native_inputs
from modarchitect.validation import compile_plan

from test_research_runtime import runtime_clients  # noqa: F401


def test_templates_compile_and_public_metadata_excludes_real_case_inputs(monkeypatch):
    """十套准确方案可检查；真实档案不进入公开元数据或可下载静态模板。"""
    rows = templates()
    assert len(rows) == 20
    variants = [template(method["id"]) for row in rows for method in row.get("method_options", [])]
    assert len({row["id"] for row in rows + variants}) == 22
    for variant in variants:
        compile_plan(ResearchPlan.model_validate(variant["definition"]), adopted=True)
        view = template_view(variant, include_definition=True)
        targets = [item for item in view.get("input_requirements", []) if item["kind"] == "target"]
        assert targets and targets[0]["code"] == "canopy_temperature"
    for row in rows:
        compile_plan(ResearchPlan.model_validate(row["definition"]), adopted=True)
        owned = {**deepcopy(row["definition"]), "responsible_user_id": "business-user-17"}
        assert matches_template(row, owned)
        if "bundles" in row:
            validate_native_inputs(row["definition"], frozen_inputs(row))
    survey = template("survey-658b")
    assert survey["source_flow"]["total_steps"] == 28
    assert "0/6" in survey["output_description"]
    assert "bundles" not in survey
    monkeypatch.setenv("MODARCHITECT_WORKSPACE_KEY", "test-templates-" * 4)
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/workspace/study-templates/survey-658b").status_code == 401
        listing = client.get("/api/v1/workspace/study-templates").json()
        assert "geometry" not in json.dumps(listing)
        client.get("/api/v1/workspace/session")
        detail = client.get("/api/v1/workspace/study-templates/survey-658b").json()
        assert "snapshot" not in detail and "bundles" not in detail
        assert detail["definition"]["layout"]["study_template"]["sha256"] == survey["sha256"]
        assert client.get("/api/v1/workspace/study-templates/unknown").status_code == 404


def test_each_template_projects_input_port_details_and_declared_products(monkeypatch):
    """库内方案与历史版本保留可追溯的输入资料组，不公开原始案例。"""
    registered = catalog()
    for filename in ("study-templates-v1.json", "study-templates-archive-v1.json",
                     "study-templates-archive-v2.json", "study-templates-archive-v3.json"):
        for row in _template_rows(filename):
            detail = template_view(row, include_definition=True)
            definition = detail["definition"]
            recipes = definition["input_recipes"]
            expected = {port for port, recipe in recipes.items() if recipe["kind"] == "artifact"}
            descriptors = detail.get("input_requirements", [])
            assert {item["port"] for item in descriptors} == expected, row["id"]
            assert len({(item["port"], item["code"]) for item in descriptors}) == len(descriptors)
            assert all(item["name"] and item["use"] and item["source"] for item in descriptors)
            assert all(set(item) == {"port", "code", "name", "unit", "kind", "use", "source"} for item in descriptors)
            assert "bundles" not in detail
            assert definition["composition"]["outputs"], row["id"]
            nodes = {node["code"]: node["component"] for node in definition["composition"]["nodes"]}
            for output in definition["composition"]["outputs"]:
                source = output["source"]
                component = nodes[source["node"]]
                ports = registered[component["code"], component["revision"]].definition.outputs
                assert any(port.code == source["port"] and port.name for port in ports)

    monkeypatch.setenv("MODARCHITECT_WORKSPACE_KEY", "test-templates-" * 4)
    with TestClient(create_app()) as client:
        client.get("/api/v1/workspace/session")
        detail = client.get("/api/v1/workspace/study-templates/greenhouse-water-use").json()
    projection = {item["code"]: item["port"] for item in detail["input_requirements"]}
    assert projection["net_radiation_mj_m2_d"] == "node_1_request"
    assert projection["ground_area_m2"] == projection["start_mass_g"] == "node_2_request"
    assert projection["kc"] == "node_3_request"
    assert len(detail["definition"]["composition"]["outputs"]) == 3


def test_native_bundle_rejects_tampering_and_false_training(monkeypatch, tmp_path):
    """原生来源不可被客户端数值替代；仅留出评价的内核不可登记为训练。"""
    row = deepcopy(template("greenhouse-random-forest"))
    row["bundles"]["dataset"]["samples"][0]["features"][0] += 1
    with pytest.raises(ValueError, match="checksum"):
        frozen_inputs(row)
    monkeypatch.setenv("MODARCHITECT_STUDY_BUNDLES", str(tmp_path))
    survey = deepcopy(template("survey-658b"))
    (tmp_path / "survey-658b.json").write_text('{"snapshot": {}, "evidence": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        frozen_inputs(survey)
    plan = ResearchPlan.model_validate(template("greenhouse-random-forest")["definition"])
    with pytest.raises(ValueError, match="does not support"):
        compile_execution(plan.composition, "train", {"random_forest@1": {"image": "sha256:" + "a" * 64}})


def test_native_graph_uses_actual_artifacts_without_observation_placeholder():
    """并行支路准确交给下游，运行中不存在伪造的观测行。"""
    row = template("greenhouse-water-balance")
    plan = ResearchPlan.model_validate(row["definition"])
    compiled = compile_plan(plan)
    profiles = {"%s@%s" % (n.component.code, n.component.revision): {"image": "sha256:" + "a" * 64} for n in plan.composition.nodes}
    inputs = frozen_inputs(row)

    class TransportRunner:
        """只检查编排交接；科学计算另在真实制品中验收。"""

        def call(self, component, profile, parameters, artifacts):
            """每次输入与上次输出都保留准确制品身份。"""
            assert parameters == {}
            definition = catalog()[component["code"], component["revision"]].definition
            return {definition.outputs[0].code: Artifact.encode({"component": component["code"]})}

    result = execute({"kind": "simulate", "plan": row["definition"], "order": compiled["order"], "profiles": profiles, "artifact_inputs": inputs}, TransportRunner())
    assert result["pipeline"] is None and result["metrics"] == []
    receipts = {receipt["node"]: receipt for receipt in result["receipts"]}
    for node in plan.composition.nodes:
        for binding in node.bindings:
            if binding.source.node:
                assert receipts[node.code]["inputs"][binding.port] == receipts[binding.source.node]["outputs"][binding.source.port]


def test_native_output_manifest_uses_declared_safe_files_and_checks_exact_bytes():
    """同一协议支持原生 output_0 命名，仍拒绝路径越界、额外文件及错误摘要。"""
    artifact = Artifact.encode({"scientific_result": 2.0})
    outputs = {"answer": {"path": "output_0.json", "sha256": artifact.digest}}
    runner = ContainerRunner.__new__(ContainerRunner)

    def bundle(references, extra=None):
        """构建只在内存中的组件成果归档。"""
        manifest = Artifact.encode({"protocol_version": "1.0", "invocation_id": "invocation", "outputs": references})
        return archive({"output_0.json": artifact.raw, "result.json": manifest.raw, **(extra or {})}, 0o444, "artifacts")

    assert runner._outputs(bundle(outputs), "invocation", ["answer"])["answer"].digest == artifact.digest
    for reference in [{"path": "../output_0.json", "sha256": artifact.digest}, {"path": "output_0.json", "sha256": "a" * 64}]:
        with pytest.raises(ValueError):
            runner._outputs(bundle({"answer": reference}), "invocation", ["answer"])
    with pytest.raises(ValueError):
        runner._outputs(bundle(outputs, {"unexpected.json": b"{}"}), "invocation", ["answer"])
    with pytest.raises(ValueError, match="ports"):
        runner._outputs(bundle(["answer"]), "invocation", ["answer"])
    with pytest.raises(ValueError, match="manifest is missing"):
        runner._outputs(archive({"output_0.json": artifact.raw}, 0o444, "artifacts"), "invocation", ["answer"])


def test_request_named_native_port_cannot_overwrite_protocol_manifest():
    """原生请求、同名衍生端口与清单各有独立文件及真实摘要。"""
    inputs = {port: Artifact.encode({"port": port}) for port in ("request", "request_input", "dataset")}
    files = invocation_files({"code": "random_forest", "revision": 1}, {}, inputs, "invocation")
    manifest = json.loads(files["request.json"])
    assert len(files) == 4
    for port, ref in manifest["inputs"].items():
        assert ref["path"] != "request.json"
        assert Artifact(files[ref["path"]]).digest == inputs[port].digest


def test_native_template_save_reopen_authorization_revision_and_replay(runtime_clients):  # noqa: F811
    """真实低权限库中采用重开、幂等提交、跨工作区和科学配置篡改均有约束。"""
    client, other = runtime_clients
    row = template_view(template("greenhouse-random-forest"), include_definition=True)
    headers = {"X-Workspace-Request": "1", "Idempotency-Key": str(uuid4())}
    saved = client.post("/api/v1/workspace/plans", headers=headers, json={"definition": row["definition"]})
    assert saved.status_code == 200, saved.text
    saved = saved.json()
    assert client.get("/api/v1/workspace/plans/" + saved["design_id"]).json()["configuration"]["definition"] == row["definition"]
    assert other.get("/api/v1/workspace/plans/" + saved["design_id"]).status_code == 404
    body = {"design_id": saved["design_id"], "expected_revision": saved["revision"], "template_id": row["id"], "template_sha256": row["sha256"]}
    assert other.post("/api/v1/workspace/template-runs", headers=headers, json=body).status_code == 404
    bad = {**body, "template_sha256": "a" * 64}
    assert client.post("/api/v1/workspace/template-runs", headers=headers, json=bad).status_code == 404
    stale = {**body, "expected_revision": 999}
    assert client.post("/api/v1/workspace/template-runs", headers=headers, json=stale).status_code == 409
    first = client.post("/api/v1/workspace/template-runs", headers=headers, json=body)
    assert first.status_code == 200, first.text
    assert client.post("/api/v1/workspace/template-runs", headers=headers, json=body).json() == first.json()
    worker = {"X-Research-Worker-Key": "worker-test-" * 8}
    job = client.post("/internal/v1/research/dispatch/next", headers=worker).json()["job"]
    assert job["run_id"] == first.json()["run_id"]
    claimed = client.post("/internal/v1/research/claim", headers=worker, json={"run_id": job["run_id"], "dispatch_token": job["dispatch_token"]}).json()
    completed = client.post("/internal/v1/research/runs/" + job["run_id"] + "/complete", headers=worker, json={"attempt_id": claimed["attempt_id"], "error": "Injected transport test failure"})
    assert completed.status_code == 200
    edited = deepcopy(row["definition"])
    edited["evaluation"]["maximum_runs"] = 2
    update = client.put("/api/v1/workspace/plans/" + saved["design_id"], headers=headers, json={"definition": edited, "expected_revision": saved["revision"]})
    assert update.status_code == 200, update.text
    body["expected_revision"] = update.json()["revision"]
    rejected = client.post("/api/v1/workspace/template-runs", headers={**headers, "Idempotency-Key": str(uuid4())}, json=body)
    assert rejected.status_code == 422 and "scientific definition" in rejected.text


def test_template_updates_preserve_exact_old_versions_and_native_inputs_need_no_dummy_variable(monkeypatch):
    """新版原生输入不重复声明占位变量；旧版仍按已保存摘要读取，普通观测不能省变量。"""
    current = template("survey-658b")
    assert current["revision"] == 2 and current["definition"]["variables"] == []
    from importlib.resources import files

    archive_rows = json.loads(files("modarchitect.contracts").joinpath("study-templates-archive-v1.json").read_text(encoding="utf-8"))
    old = next(row for row in archive_rows if row["id"] == "survey-658b")
    assert template("survey-658b", old["sha256"]) == old
    assert old["revision"] == 1 and old["sha256"] != current["sha256"]
    compile_plan(ResearchPlan.model_validate(old["definition"]), adopted=True)
    ordinary = deepcopy(template("field-multitarget")["definition"])
    ordinary["variables"] = []
    with pytest.raises(ValueError, match="variable definitions"):
        ResearchPlan.model_validate(ordinary)
    monkeypatch.setenv("MODARCHITECT_WORKSPACE_KEY", "test-template-history-" * 3)
    with TestClient(create_app()) as client:
        client.get("/api/v1/workspace/session")
        restored = client.get("/api/v1/workspace/study-templates/survey-658b", params={"sha256": old["sha256"]}).json()
        assert restored["revision"] == 1
        assert restored["definition"]["layout"]["study_template"]["sha256"] == old["sha256"]
