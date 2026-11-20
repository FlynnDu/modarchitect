# -*- coding: utf-8 -*-
# @Time    : 2026/11/20 15:43
# @Author  : Codex
# @File    : test_research_methods.py
"""按正式接口验证统一方法目录、无日期发布和训练预测闭环。"""

from copy import deepcopy
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from modarchitect.execution_contracts import execution_capability, reference_key
from modarchitect.runtime.containers import Artifact
from test_research_runtime import BASE, WRITE, ScientificRunner, calculate_next
from test_research_runtime import runtime_clients  # noqa: F401


DIRECTORY = "/api/v1/model-center/research-methods"
METHODS = (
    "multivariate_linear", "historical_logistic", "random_forest", "xgboost", "gaussian_process",
)


class ReviewedMethodRunner(ScientificRunner):
    """运行仓库真实算法，仅替换容器传输。"""

    def call(self, component, profile, parameters, inputs):
        """复用线性、曲线和日期转换执行，树与高斯过程按共用适配器执行。"""
        algorithm, action = component["code"].rsplit("_", 1)
        if algorithm not in {"random_forest", "xgboost", "gaussian_process"}:
            return super().call(component, profile, parameters, inputs)
        from components.tabular_learning.component import predict, train

        self.calls.append(component["code"])
        execute = train if action == "training" else predict
        result = execute({key: item.value for key, item in inputs.items()}, parameters, algorithm=algorithm)
        return {key: Artifact.encode(value) for key, value in result.items()}


def test_method_directory_uses_exact_contracts_and_reports_missing_artifacts(runtime_clients, monkeypatch):  # noqa: F811
    """复用组件自己的参数、用途及成果，保留历史目录并区分运行资格。"""
    client, _ = runtime_clients
    monkeypatch.delenv("MODARCHITECT_RUNTIME_PROFILES")
    body = client.get(DIRECTORY).raise_for_status().json()
    assert body["schema_version"] == "1.0"
    families = {family["operation"]: family for family in body["families"]}
    assert {entry["name"] for entry in families["simulate"]["planned"] if entry["status"] == "planned"} == {"WOFOST", "APSIM"}
    assert [item["component"]["code"] for item in body["items"]] == [name + "_training" for name in METHODS]
    for item in body["items"]:
        code, revision = item["component"]["code"], item["component"]["revision"]
        assert set(item) == {"component", "name", "relationship", "operation", "execution", "configuration", "settings", "outputs"}
        assert item["operation"] == "train"
        assert item["execution"] == "design_only"
        record = client.get(f"/api/v1/model-center/components/{code}", params={"revision": revision}).raise_for_status().json()
        assert item["configuration"]["input_uses"] == record["research_contract"]["input_uses"]
        assert item["configuration"]["parameter_schema"] == record["research_contract"]["request_schema"]
        assert item["outputs"] == record["definition"]["outputs"]
        assert item["settings"]
        if code == "random_forest_training":
            assert {entry["code"]: entry["value"] for entry in item["settings"]}["n_estimators"] == 64
            assert item["configuration"]["advanced_fields"] == ["seed"]
    assert client.get("/api/v1/model-center/components/research_descriptive_statistics", params={"revision": 1}).status_code == 200


@pytest.mark.parametrize("method", METHODS)
def test_reviewed_method_publishes_without_dates_and_reuses_the_trained_model(runtime_clients, method):  # noqa: F811
    """无观测也能固定方案版本，运行才确定截止日且独立预测不拟合。"""
    client, _ = runtime_clients
    code = method + "_training"
    selection = {"code": code, "revision": 1}
    capability = execution_capability(selection)
    profile_path = Path(os.environ["MODARCHITECT_RUNTIME_PROFILES"])
    profiles = json.loads(profile_path.read_text(encoding="utf-8"))
    profiles[reference_key(selection)].update(
        state_output=capability.state_output,
        inference=reference_key(capability.inference.model_dump(mode="json")),
    )
    profile_path.write_text(json.dumps(profiles), encoding="utf-8")
    chosen = next(item for item in client.get(DIRECTORY).raise_for_status().json()["items"] if item["component"] == selection)
    assert chosen["execution"] == "available"
    config = chosen["configuration"]
    kind = "calendar" if method == "historical_logistic" else "multivariable"
    sample = client.get(f"{BASE}/examples/{kind}").raise_for_status().json()
    definition = (
        client.get(BASE + "/study-templates/biomass-growth-curve").raise_for_status().json()["definition"]
        if method == "historical_logistic" else sample["definition"]
    )
    node = definition["composition"]["nodes"][-1]
    node["component"] = selection
    request = next(item["source"]["port"] for item in node["bindings"] if item["port"] == "request")
    recipe = definition["input_recipes"][request]
    recipe["value"] = {**config["defaults"], **recipe["value"]}
    recipe["runtime_fields"] = config["runtime_fields"]
    cutoff_field = next(iter(recipe["runtime_fields"]))
    recipe["value"].pop(cutoff_field, None)
    custom_evaluation = method == "multivariate_linear"
    percent = 65 if custom_evaluation else 80
    if custom_evaluation:
        definition["evaluation"].update(training_percent=percent, metrics=["mae"])
        invalid_policies = (
            {"training_percent": 100}, {"training_percent": 65.5},
            {"metrics": []}, {"metrics": ["mae", "mae"]}, {"metrics": ["mape"]},
        )
        for fields in invalid_policies:
            invalid = {**definition, "evaluation": {**definition["evaluation"], **fields}}
            response = client.post("/designer/validate", json=invalid).raise_for_status().json()
            assert not response["check"]["valid"]
    headers = {**WRITE, "Idempotency-Key": str(uuid4())}
    saved = client.post(BASE + "/plans", headers=headers, json={
        "definition": definition, "data_kind": "synthetic",
    }).raise_for_status().json()
    path = BASE + "/plans/" + saved["design_id"]
    published = client.post(path + "/publish", headers=WRITE, json={
        "expected_revision": saved["revision"],
    }).raise_for_status().json()
    assert published["design_version_id"]
    reopened = client.get(path).raise_for_status().json()
    assert reopened["configuration"]["definition"] == definition
    prediction = reopened["inspection"]["prediction"]
    assert prediction["target_codes"] == definition["evaluation"]["target_codes"]
    assert set(prediction["input_codes"]) == {column["code"] for column in sample["prediction_observations"]["columns"]}
    evaluation = reopened["inspection"]["evaluation"]
    assert evaluation["strategy"] == "automatic_dates"
    assert evaluation["training_percent"] == percent
    selected_metrics = {metric["code"] for metric in evaluation["metrics"] if metric["selected"]}
    assert selected_metrics == ({"mae"} if custom_evaluation else {"r2", "rmse", "mae", "bias"})

    observations = sample["observations"]
    days = sorted({row["business_date"] for row in observations["rows"]})
    expected_cutoff = days[len(days) * percent // 100 - 1]
    training = {
        "design_id": saved["design_id"], "expected_revision": saved["revision"],
        "observations": observations, "data_kind": "synthetic",
    }
    if method == "multivariate_linear":
        invalid = {**observations, "rows": observations["rows"][:1]}
        blocked = client.post(BASE + "/check-execution", headers=WRITE, json={
            "definition": definition, "operation": "train", "data_kind": "synthetic", "observations": invalid,
        }).raise_for_status().json()
        assert not blocked["can_execute"]
        assert blocked["issues"][0]["rule"] == "input_data"
        rejected = client.post(BASE + "/runs", headers={**WRITE, "Idempotency-Key": str(uuid4())},
                               json={**training, "observations": invalid})
        assert rejected.status_code == 422
        forged = deepcopy(definition)
        forged["input_recipes"][request]["value"][cutoff_field] = "2026-03-02"
        result = client.post("/designer/validate", json=forged).raise_for_status().json()
        assert not result["check"]["valid"]
    launched = client.post(BASE + "/runs", headers={**WRITE, "Idempotency-Key": str(uuid4())}, json=training)
    assert launched.status_code == 200, launched.text
    runner = ReviewedMethodRunner()
    completed, _ = calculate_next(client, runner)
    result = completed["result_json"]
    assert completed["status"] == "succeeded"
    assert result["pipeline"]["cutoffs"][node["code"]] == expected_cutoff
    eligible = sum(row["business_date"] > expected_cutoff for row in observations["rows"])
    assert result["metrics"] and all(
        metric["status"] == "evaluated" and metric["rows"] == eligible
        for metric in result["metrics"]
    )
    assert all(row.keys() & {"r2", "rmse", "mae", "bias"} == selected_metrics for row in result["metrics"])
    model = client.post(BASE + "/models", headers=WRITE, json={
        "run_id": completed["run_id"], "name": method,
    }).raise_for_status().json()
    runner.calls.clear()
    client.post(BASE + "/predictions", headers={**WRITE, "Idempotency-Key": str(uuid4())}, json={
        "model_id": model["model_id"], "observations": sample["prediction_observations"], "data_kind": "synthetic",
    }).raise_for_status()
    predicted, _ = calculate_next(client, runner)
    assert predicted["status"] == "succeeded"
    assert runner.calls[-1] == capability.inference.code and code not in runner.calls
