# -*- coding: utf-8 -*-
# @Time    : 2026/11/20 14:49
# @Author  : Codex
# @File    : test_growth_research_catalog.py
"""研究目录只采用自有数据可训练并保存预测模型的方案，历史准确版本仍可读。"""

from fastapi.testclient import TestClient
from copy import deepcopy
from datetime import date, timedelta
from uuid import uuid4

import pytest

from modarchitect.api import create_app
from modarchitect.study_templates import _template_rows, template, template_view, templates, training_template_issues
from test_research_runtime import BASE, WRITE, ScientificRunner, calculate_next
from test_research_runtime import runtime_clients as runtime_clients


RETAINED = {"crop-growth-prediction", "soil-weather-lai", "soil-weather-biomass",
            "soil-weather-canopy", "soil-weather-satellite-lai"}
ADDED = {"biomass-growth-curve", "canopy-weather-tuber-dry-matter", "satellite-biomass-prediction"}
PUBLIC = RETAINED | ADDED


def test_new_research_catalog_requires_the_complete_training_prediction_loop():
    """只采用能学习生长关系、存模型并接收自有数据的方案。"""
    rows = templates()
    assert {row["id"] for row in rows} == PUBLIC
    for row in rows:
        detail = template_view(row, include_definition=True)
        assert detail["operation"] == "train"
        assert detail["definition"]["evaluation"]["target_codes"]
        assert detail["input_policy"]["mode"] == "user_observations"


def test_eligibility_uses_the_contract_instead_of_the_template_name():
    """改名称不能令分析伪装训练；缺模型导出或真实来源合同不能入新目录。"""
    statistics = deepcopy(template("field-indicator-summary"))
    statistics["title"] = "作物生长智能训练预测"
    assert "not_training" in training_template_issues(statistics)
    prediction = deepcopy(template("crop-growth-prediction"))
    prediction["definition"]["composition"]["outputs"] = [output for output in prediction["definition"]["composition"]["outputs"] if output["code"] != "trained_model"]
    assert "no_reusable_prediction_outputs" in training_template_issues(prediction)
    prediction = deepcopy(template("crop-growth-prediction"))
    prediction["definition"]["collection_requirements"][0].pop("catalog_binding")
    assert "non_catalog_inputs" in training_template_issues(prediction)


def test_withdrawn_defaults_are_closed_but_exact_history_is_preserved(monkeypatch):
    """业务和工作区新入口一致下架，按旧摘要回读仍保留完整科学定义。"""
    monkeypatch.setenv("MODARCHITECT_WORKSPACE_KEY", "catalog-only-test-" * 4)
    rows = _template_rows("study-templates-v1.json")
    with TestClient(create_app(api_key="catalog-only-test", authentication_mode="api_key")) as client:
        client.headers["X-Modarchitect-Api-Key"] = "catalog-only-test"
        client.get("/api/v1/workspace/session").raise_for_status()
        for prefix in ("/api/v1/research", "/api/v1/workspace"):
            listing = client.get(prefix + "/study-templates").raise_for_status().json()
            assert {row["id"] for row in listing["items"]} == PUBLIC
            for row in rows:
                path = prefix + "/study-templates/" + row["id"]
                response = client.get(path)
                assert response.status_code == (200 if row["id"] in PUBLIC else 404)
                history = client.get(path, params={"sha256": row["sha256"]}).raise_for_status().json()
                assert history["sha256"] == row["sha256"]
                expected = template_view(template(row["id"], row["sha256"]), include_definition=True)
                assert history["definition"] == expected["definition"]


def observed_relationship(row: dict) -> dict:
    """用独立已知关系构造多地块验收观测，合成数据不宣称农业精度。"""
    plan = row["definition"]
    parameters = plan["input_recipes"]["regression_config"]["value"]
    raw = {code for recipe in plan["input_recipes"].values() if recipe["kind"] == "observations"
           for code in recipe["variable_codes"]}
    requirements = {item["variable_code"]: item for item in plan["collection_requirements"]}
    columns = [{"code": variable["code"], "name": variable["name"], "unit": variable["unit"],
                "value_kind": requirements[variable["code"]]["catalog_binding"]["value_nature"]}
               for variable in plan["variables"] if variable["code"] in raw]
    cutoff = date.fromisoformat(parameters.get("training_end", "2026-06-20"))
    rows = []
    for field in range(4):
        for step in range(1, 13):
            values = {"temperature_mean_daily": 12 + step * 0.5, "solar_radiation_daily": 12 + step**2 * 0.2,
                      "precipitation_daily": step**3 * 0.03, "soil_clay": 10 + field * 3,
                      "soil_soc": 10 + field**2, "soil_phh2o": 5.5 + field * 0.2,
                      "soil_bdod": 1.05 + field**2 * 0.03, "canopy_cover": 0.1 + step * 0.015 + field * 0.02,
                      "tuber_dm_kg_ha": step**2 * 3 + field * 5,
                      "sentinel2_red_reflectance": 0.1 + step * 0.002 + field * 0.001,
                      "sentinel2_nir_reflectance": 0.3 + step**2 * 0.001 + field**2 * 0.003}
            values["sentinel_ndvi"] = (values["sentinel2_nir_reflectance"] - values["sentinel2_red_reflectance"]) / (values["sentinel2_nir_reflectance"] + values["sentinel2_red_reflectance"])
            for target in parameters["targets"]:
                scale = {"lai": 0.01, "agb_kg_ha": 5, "canopy_cover": 0.001, "tuber_dm_kg_ha": 2}[target]
                values[target] = (100 if target == "agb_kg_ha" else 0.1) + sum(
                    (index + 1) * scale * values[feature] for index, feature in enumerate(parameters["features"]))
            rows.append({"object": {"field_ref": "field-%s" % field, "crop_code": "potato", "season_ref": "season-1"},
                         "business_date": (cutoff + timedelta(days=step - 8)).isoformat(),
                         "values": {code: values[code] for code in raw}})
    return {"columns": columns, "rows": rows}


@pytest.mark.parametrize("template_id", sorted(PUBLIC - {"biomass-growth-curve"}))
def test_every_retained_research_learns_validates_and_reuses_its_relationship(runtime_clients, template_id):
    """多因素方案逐一经 HTTP 训练、留出验证、保存模型和改因素预测，预测不重训。"""
    client, _ = runtime_clients
    detail = client.get(BASE + "/study-templates/" + template_id).raise_for_status().json()
    table = observed_relationship(detail)
    saved = client.post(BASE + "/plans", headers={**WRITE, "Idempotency-Key": str(uuid4())},
                        json={"definition": detail["definition"], "observations": table, "data_kind": "synthetic"}).raise_for_status().json()
    submitted = client.post(BASE + "/runs", headers={**WRITE, "Idempotency-Key": str(uuid4())},
                json={"design_id": saved["design_id"], "expected_revision": saved["revision"],
                      "operation": "train", "observations": table, "data_kind": "synthetic"})
    assert submitted.status_code == 200, submitted.text
    runner = ScientificRunner()
    completed, _ = calculate_next(client, runner)
    assert completed["status"] == "succeeded"
    metrics = completed["result_json"]["metrics"]
    holdout_rows = 12 if template_id in ADDED else 16
    assert metrics and all(metric["status"] == "evaluated" and metric["rows"] == holdout_rows and metric["rmse"] < 1e-6 for metric in metrics)
    model = client.post(BASE + "/models", headers=WRITE, json={"run_id": completed["run_id"], "name": detail["title"]}).raise_for_status().json()
    model = client.get(BASE + "/models/" + model["model_id"]).raise_for_status().json()
    frozen = deepcopy(model["model_json"]["states"])
    assert any(state.get("format") == "linear_state_v1" and state["state"]["coefficients"] for state in frozen.values())
    targets = set(detail["definition"]["evaluation"]["target_codes"])
    prediction = {"columns": [column for column in table["columns"] if column["code"] not in targets],
                  "rows": [{**deepcopy(table["rows"][-1]), "values": {code: value for code, value in table["rows"][-1]["values"].items() if code not in targets}}]}
    results = []
    for altered in (False, True):
        if altered:
            feature = "canopy_cover" if template_id == "crop-growth-prediction" else "temperature_mean_daily"
            prediction["rows"][0]["values"][feature] += 0.01 if feature == "canopy_cover" else 1
        runner.calls.clear()
        client.post(BASE + "/predictions", headers={**WRITE, "Idempotency-Key": str(uuid4())},
                    json={"model_id": model["model_id"], "observations": prediction, "data_kind": "synthetic"}).raise_for_status()
        result, _ = calculate_next(client, runner)
        assert "multivariate_linear_training" not in runner.calls and "multivariate_linear_predict" in runner.calls
        assert result["result_json"]["pipeline"]["states"] == frozen
        assert result["design_version_id"] == model["design_version_id"]
        results.append(result["result_json"]["outputs"]["predictions"]["rows"][0]["values"])
    assert any(results[0][code] != results[1][code] for code in targets)
