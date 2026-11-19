# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 16:15
# @Author  : Codex
# @File    : verify_study_templates.py
"""用真实工作区和 DolphinScheduler 验收现成方案、原生数据与模型预测。"""

import argparse
from copy import deepcopy
import json
from pathlib import Path

import httpx

from scripts.verify_input_sources import api, wait_run

BASE = "/api/v1/workspace"


def check_edges(result: dict, plan: dict) -> None:
    """相邻计算节点必须交接相同字节，不以节点成功代替串联正确。"""
    receipts = {item["node"]: item for item in result["receipts"]}
    for node in plan["composition"]["nodes"]:
        for binding in node["bindings"]:
            source = binding["source"]
            if source.get("node"):
                assert receipts[node["code"]]["inputs"][binding["port"]] == receipts[source["node"]]["outputs"][source["port"]]


def verify_rule_boundaries(client: httpx.Client) -> dict:
    """用在线实际资料检查最小合同与非法增删，不产生方案或运行。"""
    schemas = api(client, "GET", "/openapi.json")["components"]["schemas"]
    assert set(schemas["ExecutionCheckRequest"]["properties"]) == {"definition", "operation", "observations", "data_kind"}
    assert set(schemas["ExecutionCheckResult"]["properties"]) == {"can_execute", "issues"}
    assert set(schemas["RuleIssue"]["properties"]) == {"rule", "path", "message"}
    before = {key: api(client, "GET", BASE + "/" + key)["items"] for key in ("plans", "runs")}
    study = api(client, "GET", BASE + "/study-templates/crop-growth-prediction")
    original = {"definition": study["definition"], "operation": "train", "observations": study["observations"], "data_kind": "synthetic"}
    proof = []
    for name in ("no_targets", "wrong_unit", "missing_factor", "missing_required_input"):
        body = deepcopy(original)
        plan, table = body["definition"], body["observations"]
        if name == "no_targets":
            plan["input_recipes"]["regression_config"]["value"]["targets"] = []
        elif name == "wrong_unit":
            table["columns"][0]["unit"] = "cm"
        elif name == "missing_factor":
            code = plan["input_recipes"]["regression_config"]["value"]["features"][0]
            table["columns"] = [column for column in table["columns"] if column["code"] != code]
            for row in table["rows"]:
                row["values"].pop(code)
        else:
            plan["composition"]["inputs"] = [port for port in plan["composition"]["inputs"] if port["code"] != "observations"]
            plan["input_recipes"].pop("observations")
        value = api(client, "POST", BASE + "/check-execution", body)
        assert not value["can_execute"] and value["issues"]
        assert set(value) == {"can_execute", "issues"} and set(value["issues"][0]) == {"rule", "path", "message"}
        proof.append({"case": name, "rule": value["issues"][0]["rule"]})
    study = api(client, "GET", BASE + "/study-templates/growth-water-response")
    for name, selected, allowed in (("valid_subset", ["wofost_lai"], True), ("no_indicators", [], False), ("unknown_indicator", ["unknown_indicator"], False)):
        definition = deepcopy(study["definition"])
        definition["input_recipes"]["settings"]["value"]["variables"] = selected
        value = api(client, "POST", BASE + "/check-execution", {"definition": definition, "operation": study["operation"]})
        assert value["can_execute"] is allowed, value
        proof.append({"case": name, "accepted": allowed})
    after = {key: api(client, "GET", BASE + "/" + key)["items"] for key in ("plans", "runs")}
    assert before == after
    return {"minimal_contracts": True, "no_records_created": True, "cases": proof}


def verify_template(client: httpx.Client, template_id: str, checksum: str | None = None) -> dict:
    """采用准确模板，保存重开后实际运行，并核对相应科学成果。"""
    study = api(client, "GET", BASE + "/study-templates/" + template_id + ("?sha256=" + checksum if checksum else ""))
    native = study["execution_mode"] == "frozen_case"
    check_body = {"definition": study["definition"], "operation": study["operation"]}
    if not native:
        check_body.update(observations=study["observations"], data_kind="synthetic")
    checked = api(client, "POST", BASE + "/check-execution", check_body)
    assert checked == {"can_execute": True, "issues": []}, checked
    saved = api(client, "POST", BASE + "/plans", {"definition": study["definition"], "observations": study["observations"], "data_kind": "synthetic" if study["data_kind"] == "synthetic" else "user_supplied"})
    reopened = api(client, "GET", BASE + "/plans/" + saved["design_id"])
    assert reopened["configuration"]["definition"] == study["definition"]
    if native:
        body = {"design_id": saved["design_id"], "expected_revision": saved["revision"], "template_id": template_id, "template_sha256": study["sha256"]}
    else:
        assert reopened["observations"]["rows"] == study["observations"]["rows"]
        body = {"design_id": saved["design_id"], "expected_revision": saved["revision"], "observations": study["observations"], "data_kind": "synthetic", "operation": study["operation"]}
    run = wait_run(client, api(client, "POST", BASE + ("/template-runs" if native else "/runs"), body))
    result = run["result_json"]
    assert api(client, "GET", BASE + "/runs/" + run["run_id"] + "/plan") == study["definition"]
    check_edges(result, study["definition"])
    proof = {"template_id": template_id, "template_sha256": study["sha256"], "design_id": saved["design_id"], "run_id": run["run_id"], "scheduler_id": run["scheduler_id"], "operation": run["kind"], "result_sha256": run["result_sha256"], "input_sources_sha256": result["input_sources"]["sha256"], "receipts": result["receipts"], "data_kind": result["data_kind"], "reopened": True, "edges_verified": True}
    if study["operation"] == "train":
        assert result["pipeline"]["states"]
        model = api(client, "POST", BASE + "/models", {"run_id": run["run_id"], "name": study["title"] + " · 现成方案验收"})
        future = study["prediction_observations"]
        assert future
        prediction = wait_run(client, api(client, "POST", BASE + "/predictions", {"model_id": model["model_id"], "observations": future, "data_kind": "synthetic"}))
        assert prediction["result_json"]["pipeline"]["states"] == model["model_json"]["states"]
        assert not any("training" in receipt["component"]["code"] for receipt in prediction["result_json"]["receipts"])
        assert api(client, "GET", BASE + "/models/" + model["model_id"])["model_sha256"] == model["model_sha256"]
        proof.update(model_id=model["model_id"], model_sha256=model["model_sha256"], prediction_run_id=prediction["run_id"], prediction_scheduler_id=prediction["scheduler_id"], state_unchanged=True)
    else:
        assert result["pipeline"] is None
        api(client, "POST", BASE + "/models", {"run_id": run["run_id"], "name": "Non-model result must be refused"}, expected=409)
        proof["not_a_reusable_model"] = True
        if template_id == "survey-658b":
            assessment = result["outputs"]["assessment"]
            assert len(assessment["module_scores"]) == 6
            assert all(module["score"] is None for module in assessment["module_scores"])
            assert result["receipts"][0]["outputs"]["assessment"] == "f8718ee6c82860fb1ee979fd874ce561092770aa78074b61dc6daddab228d595"
            proof["qualified_scored_modules"] = 0
            proof["original_workflow_steps"] = study["source_flow"]["total_steps"]
            proof["frozen_reference_identical"] = True
        elif "comparison" in result["outputs"]:
            proof["scientific_outputs"] = {key: value["payload"] for key, value in result["outputs"].items()}
        elif "holdout" in result["outputs"]:
            holdout = result["outputs"]["holdout"]["payload"]
            assert holdout["training_count"] == 9 and holdout["rmse"] >= holdout["mae"] >= 0
            assert len(holdout["rows"]) == (4 if holdout["algorithm"] in {"lstm", "convlstm"} else 5)
            proof.update(training_count=holdout["training_count"], holdout_count=len(holdout["rows"]), mae=holdout["mae"], rmse=holdout["rmse"])
        elif "report" in result["outputs"]:
            report = result["outputs"]["report"]
            if report["format"] == "research_weather_conditions_v1":
                assert report["rule"]["code"] == study["definition"]["input_recipes"]["settings"]["value"]["rule"]
                proof.update(qualification=report["rule"]["qualification"], condition=report["rule"]["result"], valid_days=report["rule"]["window"]["valid_days"], expected_days=report["rule"]["window"]["expected_days"])
            else:
                assert report["format"] == "agronomic_indicator_analysis_v1" and report["row_count"] > 0
                proof.update(row_count=report["row_count"], value_kinds=sorted({item["value_kind"] for item in report["indicators"]}))
    print("Verified template %s" % template_id, flush=True)
    return proof


def verify_parameters(client: httpx.Client, baseline: dict, updates: dict) -> dict:
    """改研究参数后实际重算，原输入制品和来源保持同一份。"""
    saved = api(client, "GET", BASE + "/plans/" + baseline["design_id"])
    definition = saved["configuration"]["definition"]
    definition["input_recipes"]["settings"]["value"].update(updates)
    saved = api(client, "PUT", BASE + "/plans/" + baseline["design_id"], {"definition": definition, "expected_revision": saved["revision"]})
    run = wait_run(client, api(client, "POST", BASE + "/template-runs", {"design_id": saved["design_id"], "expected_revision": saved["revision"], "template_id": baseline["template_id"], "template_sha256": baseline["template_sha256"]}))
    result = run["result_json"]
    assert result["receipts"][0]["inputs"] == baseline["receipts"][0]["inputs"]
    assert result["receipts"][0]["outputs"] != baseline["receipts"][0]["outputs"]
    report = result["outputs"]["report"]
    for key, value in updates.items():
        if key == "variables":
            assert [item["code"] for item in report["indicators"]] == value
        else:
            assert report[key] == value
    return {"template_id": baseline["template_id"], "run_id": run["run_id"], "scheduler_id": run["scheduler_id"], "updates": updates, "same_data_new_calculation": True}


def main() -> None:
    """逐方案落盘进度；报告不保存 Cookie、实际业务快照或登录凭据。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    proof = {"service": args.base_url, "scenarios": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        api(client, "GET", BASE + "/session")
        proof["rule_checks"] = verify_rule_boundaries(client)
        items = api(client, "GET", BASE + "/study-templates")["items"]
        assert len(items) == 16
        assert not any(row["id"] == "survey-658b" for row in items)
        for row in items:
            proof["scenarios"].append(verify_template(client, row["id"]))
            args.output.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        proof["method_variants"] = [verify_template(client, code) for code in ("canopy-temperature-xgboost", "canopy-temperature-gp")]
        by_id = {row["template_id"]: row for row in proof["scenarios"]}
        proof["parameter_experiments"] = [verify_parameters(client, by_id["crop-low-temperature"], {"as_of": "2026-10-20"}), verify_parameters(client, by_id["growth-water-response"], {"variables": ["wofost_water_stress_factor", "wofost_lai"], "start_date": "2026-10-01"})]
        archive = json.loads((Path(__file__).parents[1] / "modarchitect/contracts/study-templates-archive-v1.json").read_text(encoding="utf-8"))
        legacy = next(row for row in archive if row["id"] == "survey-658b")
        proof["historical_template"] = verify_template(client, "survey-658b", legacy["sha256"])
        assert proof["historical_template"]["template_sha256"] == legacy["sha256"]
        with httpx.Client(base_url=args.base_url, timeout=30) as other:
            api(other, "GET", BASE + "/session")
            api(other, "GET", BASE + "/plans/" + proof["scenarios"][0]["design_id"], expected=404)
            api(other, "GET", BASE + "/runs/" + proof["scenarios"][0]["run_id"], expected=404)
            proof["cross_workspace_rejected"] = True
    args.output.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("All public research themes, method choices and parameter experiments passed", flush=True)


if __name__ == "__main__":
    main()
