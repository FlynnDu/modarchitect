# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 01:10
# @Author  : Codex
# @File    : test_system_inputs.py
"""通过公开输入合同验证固定来源、科学支撑和不可冒用的观测。"""

from copy import deepcopy
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from modarchitect.api import create_app
from modarchitect.contracts.identifiers import identity_sha256
from modarchitect.system_inputs import (
    configure_input, input_catalog, resolve_input, seal_input_sources, validate_input_bindings,
)

ROOT = Path(__file__).parents[1]


def standard_study() -> dict:
    """读取具有准确系统绑定、单独标注合成数据的双目标样例。"""
    return json.loads((ROOT / "modarchitect/web/designer/system-study.json").read_bytes())


def test_public_catalog_has_four_truthful_categories_and_exact_policies():
    """目录共65项，人工录入与准确快照通道分别表达且不宣称资料就绪。"""
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/model-center/research-inputs")
        assert response.status_code == 200
        catalog = response.json()
        assert {c["code"]: c["count"] for c in catalog["categories"]} == {
            "manual": 15, "third_party": 20, "platform_analysis": 21, "iot_platform": 9,
        }
        assert catalog["total"] == 65
        available = [e for e in catalog["items"] if e["execution"]["available"]]
        assert len(available) == 24
        assert {e["variable"]["code"] for e in available if e["execution"]["channel"] == "workspace_manual_entry"} == {"lai", "agb_kg_ha", "tuber_dm_kg_ha", "canopy_cover"}
        assert len([e for e in available if e["execution"]["channel"] == "source_snapshot"]) == 20
        assert all(e["data_available"] is None for e in catalog["items"])
        third_party = [e for e in catalog["items"] if e["category"] == "third_party"]
        assert {e["source"]["binding"]["source_system"] for e in third_party} == {"openmeteo_weather", "soilgrids_reference_normalization", "sentinelhub_s2_l2a_reference"}
        assert all(e["selectable"] for e in catalog["items"])
        assert all(e["source"]["binding"]["kind"] == "planned_source" and e["source"]["method"] for e in catalog["items"] if e["category"] in {"iot_platform", "platform_analysis"})


def test_every_selectable_definition_roundtrips_its_exact_binding():
    """65项已登记定义均可设计采用，计划来源不改变实际通道状态。"""
    items = [e for e in input_catalog()["items"] if e["selectable"]]
    assert len(items) == 65
    for entry in items:
        selectors = {name: schema["enum"][0] for name, schema in entry["source"]["selection_schema"]["properties"].items()}
        configured = configure_input(entry["key"], selectors)
        validate_input_bindings({"variables": [configured["variable"]], "collection_requirements": [configured["requirement"]]}, require_catalog=True)


def test_two_level_categories_cover_every_input_without_changing_scientific_identity(monkeypatch):
    """65项都有明确细分；重命名分类不改已保存合同，缺分类和错归属不能发布。"""
    from modarchitect import input_taxonomy

    catalog = input_catalog()
    expected = {
        "manual": {"manual_morphology": 6, "manual_leaf_cover": 3, "manual_biomass_yield": 6},
        "third_party": {"third_party_weather": 7, "third_party_soil": 11, "third_party_satellite": 2},
        "platform_analysis": {"analysis_growth": 21, "analysis_3d_phenotype": 0},
        "iot_platform": {"iot_greenhouse": 5, "iot_root_water": 1, "iot_water_weighing": 3},
    }
    for parent in catalog["categories"]:
        assert {child["code"]: child["count"] for child in parent["children"]} == expected[parent["code"]]
        assert sum(child["count"] for child in parent["children"]) == parent["count"]
        assert all(row["subcategory"] in expected[parent["code"]] for row in catalog["items"] if row["category"] == parent["code"])
    configured = configure_input("variable_source:temperature_mean_daily@1.0.0", {})
    requirement = configured["requirement"]
    original = resolve_input(requirement["catalog_binding"], requirement["method"])
    taxonomy = deepcopy(input_taxonomy.taxonomy())
    for group in taxonomy["groups"]:
        group["name"] = "调整后的展示名称"
    monkeypatch.setattr(input_taxonomy, "taxonomy", lambda: taxonomy)
    changed = input_catalog()
    assert changed["sha256"] == catalog["sha256"]
    assert configure_input("variable_source:temperature_mean_daily@1.0.0", {}) == configured
    assert resolve_input(requirement["catalog_binding"], requirement["method"]) == original
    assert "subcategory" not in original
    missing = deepcopy(catalog)
    missing["items"].pop()
    with pytest.raises(ValueError, match="cover"):
        input_taxonomy.classified_catalog(missing)
    taxonomy["assignments"][catalog["items"][0]["key"]] = "third_party_weather"
    with pytest.raises(ValueError, match="category differs"):
        input_catalog()


@pytest.mark.parametrize("selectors", [{}, {"depth": "0-5cm"}, {"depth": "0-5cm", "statistic": "median"}, {"depth": "0-5cm", "statistic": "mean", "url": "https://invalid.example"}])
def test_soil_attributes_cannot_be_missing_or_overridden(selectors):
    """固定来源只接受登记深度和均值，不接受自定义取数地址。"""
    with pytest.raises(ValueError, match="selectors"):
        configure_input("variable_source:soil_phh2o@1.0.0", selectors)


@pytest.mark.parametrize("mutation", ["unit", "name", "minimum", "hash", "source", "support", "method", "unbound"])
def test_fixed_input_contract_cannot_be_impersonated(mutation):
    """后端拒绝改名、改单位、放松边界、伪造来源和删绑定。"""
    plan = standard_study()["definition"]
    variable, requirement = plan["variables"][0], plan["collection_requirements"][0]
    if mutation in {"unit", "name"}:
        variable[mutation] = "forged"
    elif mutation == "minimum":
        variable["minimum"] = None
    elif mutation == "hash":
        requirement["catalog_binding"]["contract_sha256"] = "0" * 64
    elif mutation == "source":
        requirement["source"] = "third_party"
    elif mutation == "support":
        requirement["unit_kind"] = "plant"
    elif mutation == "method":
        requirement["method"]["method_code"] = "forged"
    else:
        requirement.pop("catalog_binding")
    with pytest.raises(ValueError):
        validate_input_bindings(plan, require_catalog=True)


def test_estimated_source_cannot_be_target_or_replaced_with_uploaded_numbers():
    """取数通道不存在时明确拒绝；上传天气数值不能冒充已接通来源。"""
    with pytest.raises(ValueError, match="observed"):
        configure_input("variable_source:temperature_mean_daily@1.0.0", {}, "target")
    study = standard_study()
    configured = configure_input("variable_source:temperature_mean_daily@1.0.0", {})
    plan = study["definition"]
    plan["variables"].append(configured["variable"])
    plan["collection_requirements"].append(configured["requirement"])
    table = deepcopy(study["prediction_observations"])
    table["columns"].append({"code": "temperature_mean_daily", "name": configured["variable"]["name"], "unit": "celsius", "value_kind": "estimated"})
    for row in table["rows"]:
        row["values"]["temperature_mean_daily"] = 20
    with pytest.raises(ValueError, match="channel"):
        seal_input_sources(plan, table, "user_supplied", "owner")


def test_sealed_sources_distinguish_data_content_and_owner_without_reclassifying_demo():
    """来源清单保留标准身份、通道及准确内容；演示明确标注合成。"""
    study = standard_study()
    table = study["observations"]
    first = seal_input_sources(study["definition"], table, "user_supplied", "owner")
    assert {r["channel"] for r in first["inputs"]} == {"workspace_manual_entry"}
    assert first["table_sha256"] == identity_sha256(table)
    assert identity_sha256({k: v for k, v in first.items() if k != "sha256"}) == first["sha256"]
    table["rows"][0]["values"]["lai"] += 0.1
    second = seal_input_sources(study["definition"], table, "user_supplied", "owner")
    assert second["sha256"] != first["sha256"]
    demo = seal_input_sources(study["definition"], table, "synthetic", "owner")
    assert {r["channel"] for r in demo["inputs"]} == {"synthetic_demo"}


def test_bound_column_name_cannot_replace_the_system_metric_in_model_outputs():
    """列名称进入算法和模型，因此必须在运行边界与准确标准一致。"""
    study = standard_study()
    study["observations"]["columns"][0]["name"] = "Another metric"
    with pytest.raises(ValueError, match="name differs"):
        seal_input_sources(study["definition"], study["observations"], "user_supplied", "owner")
