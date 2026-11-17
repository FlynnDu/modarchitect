# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 17:07
# @Author  : Codex
# @File    : test_designer_demo.py
"""验证模型设计演示的公开校验、配置往返和请求边界。"""

from fastapi.testclient import TestClient

from modarchitect.api import create_app
from modarchitect.catalog import component
from modarchitect.designer import MAX_JSON_BYTES


def test_proxy_prefix_preserves_redirect_docs_assets_and_direct_access() -> None:
    """代理跳转和文档保留部署前缀，静态资源与直连可交替访问。"""
    application = create_app(api_key="engineering", proxy_prefix="/modarchitect")
    headers = {"X-Forwarded-Prefix": "/modarchitect"}
    with TestClient(application, follow_redirects=False) as client:
        assert client.get("/", headers=headers).headers["location"] == "/modarchitect/designer/"
        assert client.get("/designer/", headers=headers).status_code == 200
        assert client.get("/designer/studio.js", headers=headers).status_code == 200
        assert "url: '/modarchitect/openapi.json'" in client.get("/docs", headers=headers).text
        assert client.get("/openapi.json", headers=headers).json()["servers"] == [{"url": "/modarchitect"}]
        assert "url: '/openapi.json'" in client.get("/docs").text
        assert client.get("/openapi.json").json()["servers"] == [{"url": "/"}]
        assert client.get("/").headers["location"] == "/designer/"
        assert client.get("/", headers={"X-Forwarded-Prefix": "//other.invalid"}).headers["location"] == "/designer/"
        assert client.get("/api/v1/research/design-drafts", headers=headers).status_code == 401
        oversized = {"name": "x" * 8_000_000}
        assert client.post("/api/v1/research/design-saves", json=oversized, headers=headers).status_code == 413


def test_forwarded_prefix_requires_explicit_deployment_configuration() -> None:
    """默认部署不采用客户端自行声明的转发前缀。"""
    with TestClient(create_app(), follow_redirects=False) as client:
        assert client.get("/", headers={"X-Forwarded-Prefix": "/modarchitect"}).headers["location"] == "/designer/"


def test_designer_checks_actual_contract_and_round_trips_draft() -> None:
    """通过公开演示从样例读入到校验，再验证错误参数及篡改摘要。"""
    with TestClient(create_app(business_key="engineering")) as client:
        assert client.get("/").url.path == "/designer/"
        page = client.get("/designer/")
        assert page.status_code == 200 and "方案画布" in page.text
        definition = client.get("/designer/example.json").json()["definition"]
        checked = client.post("/designer/validate", json=definition)
        assert checked.status_code == 200
        assert checked.json()["check"]["valid"]
        draft = checked.json()["configuration"]
        assert client.post("/designer/import", json=draft).json() == checked.json()
        definition["input_recipes"]["request"]["value"][
            "axis_kind"
        ] = "growing_degree_days"
        invalid = client.post("/designer/validate", json=definition).json()["check"]
        assert not invalid["valid"]
        assert invalid["issues"][0]["path"][-1] == "x_code"
        draft["definition"]["name"] = "篡改"
        assert client.post("/designer/import", json=draft).status_code == 422
        assert client.get("/api/v1/research/design-drafts").status_code == 401


def test_designer_enforces_json_body_budget() -> None:
    """演示接口拒绝非 JSON 和超限配置。"""
    with TestClient(create_app()) as client:
        assert client.post("/designer/validate", content="{}").status_code == 415
        oversized = {"name": "x" * MAX_JSON_BYTES}
        assert client.post("/designer/validate", json=oversized).status_code == 413


def test_designer_checks_multiple_targets_and_open_ended_observation_columns() -> None:
    """验证多输入双目标及观测列缺失时的错误定位。"""
    with TestClient(create_app()) as client:
        plan = client.get("/designer/example.json").json()["definition"]
        plan["purpose"] = "train"
        plan["evaluation"]["numeric_gate"] = None
        roles = {"height": "target", "leaf_area": "target"}
        features = ["ndvi", "soil_water", "temperature"]
        features.extend("variable_%d" % index for index in range(145))
        for code in features:
            roles[code] = "covariate"
        plan["variables"] = [
            {**plan["variables"][0], "code": code, "name": code, "unit": "1", "role": role}
            for code, role in roles.items()
        ]
        plan["collection_requirements"] = [
            {**plan["collection_requirements"][0], "code": code, "variable_code": code, "required_for": ["train"]}
            for code in roles
        ]
        targets = ["height", "leaf_area"]
        plan["evaluation"]["target_codes"] = targets
        graph = plan["composition"]
        model = component("multivariate_linear_regression").definition
        graph["nodes"][0]["component"] = {"code": model.code, "revision": model.revision}
        graph["inputs"][1]["data_type"] = model.inputs[1].data_type.model_dump(mode="json")
        graph["outputs"] = [
            {"code": port.code, "source": {"node": "method", "port": port.code}}
            for port in model.outputs
        ]
        plan["input_recipes"]["observations"]["variable_codes"] = list(roles)
        plan["input_recipes"]["request"].update(
            value={"features": features, "targets": targets, "training_end": "2026-07-01"},
            runtime_fields={},
        )
        result = client.post("/designer/validate", json=plan).json()
        assert result["check"]["valid"], result["check"]
        assert client.post("/designer/import", json=result["configuration"]).json() == result
        plan["input_recipes"]["observations"]["variable_codes"].remove("soil_water")
        check = client.post("/designer/validate", json=plan).json()["check"]
        assert not check["valid"]
        assert check["issues"][0]["path"] == ["input_recipes", "request", "value", "features"]


def test_design_checks_prediction_lineage_and_cutoffs() -> None:
    """验证可运行串联的顺序，以及日期和标签来源的拒绝路径。"""
    with TestClient(create_app()) as client:
        plan = client.get("/designer/chain-example.json").json()
        check = client.post("/designer/validate", json=plan).json()["check"]
        assert check["valid"]
        assert check["compiled"]["order"] == ["baseline", "merge", "regression"]
        request = plan["input_recipes"]["regression_config"]["value"]
        request["training_end"] = "2026-06-12"
        check = client.post("/designer/validate", json=plan).json()["check"]
        assert not check["valid"]
        assert check["issues"][0]["path"][-1] == "training_end"
        request.update(training_end="2026-06-16", features=["ndvi"], targets=["prior_height"])
        plan["variables"][-1]["role"] = "target"
        plan["evaluation"]["target_codes"] = ["height", "prior_height"]
        # 新列仍需先满足合并节点声明的候选因子约束。
        check = client.post("/designer/validate", json=plan).json()["check"]
        assert not check["valid"]
        assert check["issues"][0]["path"][-1] == "output_code"


def test_legacy_logistic_curve_cannot_supply_observed_training_labels() -> None:
    """旧曲线的表结构仍能读取，预测值作为实测训练目标时校验失败。"""
    with TestClient(create_app()) as client:
        plan = client.get("/designer/chain-example.json").json()
        sample = client.get("/designer/example.json").json()["definition"]
        graph = plan["composition"]
        baseline = graph["nodes"][0]
        baseline["component"] = sample["composition"]["nodes"][0]["component"]
        graph["inputs"][1]["data_type"] = sample["composition"]["inputs"][1]["data_type"]
        plan["input_recipes"]["baseline_config"]["value"] = {
            **sample["input_recipes"]["request"]["value"], "x_code": "day", "target_code": "height",
        }
        graph["inputs"] = [item for item in graph["inputs"] if item["code"] != "merge_config"]
        plan["input_recipes"].pop("merge_config")
        graph["nodes"].pop(1)
        graph["nodes"][1]["bindings"][0]["source"] = {"node": "baseline", "port": "curve"}
        plan["input_recipes"]["regression_config"]["value"]["features"] = ["day"]
        check = client.post("/designer/validate", json=plan).json()["check"]
        assert not check["valid"]
        assert check["issues"][0]["path"][-1] == "targets"
        assert "requires an observed column" in check["issues"][0]["message"]
