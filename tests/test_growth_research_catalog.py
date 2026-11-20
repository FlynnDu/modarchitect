# -*- coding: utf-8 -*-
# @Time    : 2026/11/20 14:49
# @Author  : Codex
# @File    : test_growth_research_catalog.py
"""研究目录只采用自有数据可训练并保存预测模型的方案，历史准确版本仍可读。"""

from fastapi.testclient import TestClient
from copy import deepcopy
from datetime import date, timedelta
import json
import math
import os
from pathlib import Path
from random import Random
from uuid import uuid4
from xml.etree import ElementTree

import pytest

from modarchitect.api import create_app
from modarchitect.execution_contracts import execution_capability, reference_key
from modarchitect.study_templates import _current_template_rows, _template_rows, template, template_view, templates, training_template_issues
from test_research_methods import ReviewedMethodRunner
from test_research_runtime import BASE, WRITE, ScientificRunner, calculate_next
from test_research_runtime import runtime_clients as runtime_clients


RETAINED = {"crop-growth-prediction", "soil-weather-lai", "soil-weather-biomass",
            "soil-weather-canopy", "soil-weather-satellite-lai"}
ADDED = {"biomass-growth-curve", "canopy-weather-tuber-dry-matter", "satellite-biomass-prediction"}
PREVIOUS = RETAINED | ADDED
EXTENSION = {
    "canopy-expansion-curve", "tuber-bulking-curve", "canopy-lai-proxy",
    "phenotype-biomass-prediction", "shoot-to-tuber-dry-matter",
    "temperature-extremes-canopy", "radiation-temperature-lai", "rainfall-soil-retention-biomass",
    "wind-vapour-pressure-cover", "soil-chemistry-tuber", "soil-texture-canopy", "satellite-canopy-cover",
}
PUBLIC = PREVIOUS | EXTENSION


def test_new_research_catalog_requires_the_complete_training_prediction_loop():
    """只采用能学习生长关系、存模型并接收自有数据的方案。"""
    rows = templates()
    assert len(rows) == 20
    assert {row["id"] for row in _template_rows("study-templates-growth-v1.json")} == EXTENSION
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
    rows = _current_template_rows()
    with TestClient(create_app(api_key="catalog-only-test", authentication_mode="api_key")) as client:
        client.headers["X-Modarchitect-Api-Key"] = "catalog-only-test"
        client.get("/api/v1/workspace/session").raise_for_status()
        for prefix in ("/api/v1/research", "/api/v1/workspace"):
            listing = client.get(prefix + "/study-templates").raise_for_status().json()
            assert {row["id"] for row in listing["items"]} == PUBLIC
            assert all(row["icon_name"] == row["id"] for row in listing["items"])
            for row in rows:
                path = prefix + "/study-templates/" + row["id"]
                response = client.get(path)
                assert response.status_code == (200 if row["id"] in PUBLIC else 404)
                if row["id"] in PUBLIC:
                    assert response.json()["icon_name"] == row["id"]
                history = client.get(path, params={"sha256": row["sha256"]}).raise_for_status().json()
                assert history["sha256"] == row["sha256"]
                if row["id"] in PUBLIC:
                    assert history["icon_name"] == row["id"]
                expected = template_view(template(row["id"], row["sha256"]), include_definition=True)
                assert history["definition"] == expected["definition"]
        for template_id in PUBLIC:
            icon = client.get("/designer/study-icons/" + template_id + ".svg").raise_for_status()
            assert icon.headers["content-type"].startswith("image/svg+xml")
            svg = ElementTree.fromstring(icon.content)
            assert svg.attrib["viewBox"] == "0 0 1024 1024"
            path, = svg
            assert path.tag.endswith("}path") and path.attrib["fill"].startswith("#")
            assert path.attrib["fill-rule"] == "nonzero" and "stroke" not in path.attrib
            contours = path.attrib["d"]
            assert contours.startswith("M") and contours.endswith("Z")
            assert contours.count("M") == contours.count("Z")


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


@pytest.mark.parametrize("template_id", sorted(PREVIOUS - {"biomass-growth-curve"}))
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


def synthetic_growth_data(definition: dict) -> dict:
    """地块间土壤特征固定，业务日期和因素独立变化，生成留出验收资料。"""
    limits = {
        "temperature_minimum_daily": (7, 17), "temperature_maximum_daily": (22, 33),
        "temperature_mean_daily": (14, 24), "solar_radiation_daily": (7500, 21000),
        "precipitation_daily": (0, 36), "wind_speed_2m_daily": (0.5, 5),
        "vapour_pressure_daily": (0.7, 2.3), "soil_wv0033": (0.16, 0.34),
        "soil_phh2o": (5.5, 7.3), "soil_cec": (7, 24), "soil_cfvo": (3, 22),
        "soil_bdod": (1.1, 1.6), "soil_clay": (10, 38), "soil_soc": (12, 38),
        "sentinel2_red_reflectance": (0.08, 0.19), "sentinel2_nir_reflectance": (0.27, 0.48),
        "lai": (0.8, 4.6), "agb_kg_ha": (250, 4300), "tuber_dm_kg_ha": (100, 3200),
        "canopy_cover": (0.14, 0.85),
    }
    requirements = {item["variable_code"]: item for item in definition["collection_requirements"]}
    columns = [{
        "code": item["code"], "name": item["name"], "unit": item["unit"],
        "value_kind": requirements[item["code"]]["catalog_binding"]["value_nature"],
    } for item in definition["variables"] if item["code"] in requirements]
    target, = definition["evaluation"]["target_codes"]
    features = sorted(set(requirements) - {target})
    rng = Random(20261120)
    rows = []
    for field in range(6 if features else 1):
        soil = {code: rng.uniform(*limits[code]) for code in features if code.startswith("soil_")}
        for day in range(30):
            values = {code: rng.uniform(*limits[code]) for code in features if code not in soil}
            values.update(soil)
            low, high = limits[target]
            if features:
                scaled = [(values[code] - limits[code][0]) / (limits[code][1] - limits[code][0]) for code in features]
                share = sum((i + 1) * value for i, value in enumerate(scaled)) / (len(features) * (len(features) + 1) / 2)
                values[target] = low + (high - low) * share
            else:
                values[target] = high / (1 + math.exp(-0.38 * (day - 10)))
            rows.append({
                "object": {"field_ref": "field-%s" % field, "crop_code": "potato", "season_ref": "season-1"},
                "business_date": (date(2026, 4, 1) + timedelta(days=day)).isoformat(),
                "values": values,
            })
    return {"columns": columns, "rows": rows}


@pytest.mark.parametrize("template_id", sorted(EXTENSION))
def test_extended_template_can_publish_train_and_predict(runtime_clients, template_id):
    """逐套走正常入口验证封存、留出及原模型复用。"""
    client, _ = runtime_clients
    detail = client.get(BASE + "/study-templates/" + template_id).raise_for_status().json()
    plan = detail["definition"]
    node = plan["composition"]["nodes"][-1]
    capability = execution_capability(node["component"])
    inference = capability.inference.model_dump(mode="json")
    profile_path = Path(os.environ["MODARCHITECT_RUNTIME_PROFILES"])
    profiles = json.loads(profile_path.read_text(encoding="utf-8"))
    profiles[reference_key(node["component"])].update(
        state_output=capability.state_output, inference=reference_key(inference),
    )
    profile_path.write_text(json.dumps(profiles), encoding="utf-8")
    saved = client.post(BASE + "/plans", headers={**WRITE, "Idempotency-Key": str(uuid4())},
                        json={"definition": plan, "data_kind": "synthetic"}).raise_for_status().json()
    path = BASE + "/plans/" + saved["design_id"]
    published = client.post(path + "/publish", headers=WRITE,
                            json={"expected_revision": saved["revision"]}).raise_for_status().json()
    reopened = client.get(path).raise_for_status().json()
    assert reopened["draft_state"] == "published"
    assert reopened["inspection"]["evaluation"]["strategy"] == "automatic_dates"
    target, = plan["evaluation"]["target_codes"]
    assert reopened["inspection"]["prediction"]["target_codes"] == [target]
    table = synthetic_growth_data(plan)
    response = client.post(BASE + "/runs", headers={**WRITE, "Idempotency-Key": str(uuid4())},
                           json={"design_id": saved["design_id"], "expected_revision": saved["revision"],
                                 "operation": "train", "observations": table, "data_kind": "synthetic"})
    assert response.status_code == 200, response.text
    runner = ReviewedMethodRunner()
    completed, _ = calculate_next(client, runner)
    assert completed["status"] == "succeeded"
    assert completed["design_version_id"] == published["design_version_id"]
    results = completed["result_json"]
    cutoff = results["pipeline"]["cutoffs"][node["code"]]
    assert cutoff == "2026-04-24"
    metric, = results["metrics"]
    assert metric["target"] == target and metric["status"] == "evaluated"
    assert metric["rows"] == sum(row["business_date"] > cutoff for row in table["rows"])
    assert metric["coverage"] == 1 and math.isfinite(metric["mae"])
    model = client.post(BASE + "/models", headers=WRITE, json={"run_id": completed["run_id"],
                        "name": detail["title"]}).raise_for_status().json()
    record = deepcopy(table["rows"][-1])
    record["values"].pop(target)
    prediction = {"columns": [col for col in table["columns"] if col["code"] != target], "rows": [record]}
    runner.calls.clear()
    client.post(BASE + "/predictions", headers={**WRITE, "Idempotency-Key": str(uuid4())},
                json={"model_id": model["model_id"], "observations": prediction, "data_kind": "synthetic"}).raise_for_status()
    result, _ = calculate_next(client, runner)
    assert result["status"] == "succeeded" and runner.calls[-1] == inference["code"]
    assert node["component"]["code"] not in runner.calls
    assert result["result_json"]["pipeline"]["states"] == results["pipeline"]["states"]
    output = next(value for value in result["result_json"]["outputs"].values() if value.get("rows"))
    assert math.isfinite(output["rows"][0]["values"][target])
