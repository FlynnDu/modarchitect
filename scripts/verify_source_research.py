# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 22:46
# @Author  : Codex
# @File    : verify_source_research.py
"""通过公开 API 和真实调度验收来源采集、保存、训练及新资料预测。"""

import argparse
from copy import deepcopy
import json
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

import httpx


def main() -> None:
    """新建独立验收空间，使用真实平台因素及明确构造的工程标签。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proof = {"label_data": "constructed_engineering_labels_not_field_measurements", "base": args.base, "acquisitions": [], "runs": []}
    with httpx.Client(base_url=args.base, timeout=30, headers={"X-Workspace-Request": "1"}) as client:

        def call(path: str, body: dict | None = None, *, method: str | None = None) -> dict:
            """凭据留在客户端内存，只保存状态和必要科学证据。"""
            headers = {"Idempotency-Key": str(uuid4())} if body is not None else {}
            response = client.request(method or ("POST" if body is not None else "GET"), path, json=body, headers=headers)
            if response.status_code >= 400:
                raise RuntimeError("Acceptance request failed: %s HTTP %s %s" % (path, response.status_code, response.text[:500]))
            return response.json()

        def wait(path: str) -> dict:
            """逐次短查询等待实际完成，不把队列接受当作成功。"""
            deadline = monotonic() + 600
            while monotonic() < deadline:
                value = call(path)
                if value["status"] == "succeeded":
                    return value
                if value["status"] in {"failed", "cancelled", "uncertain"}:
                    raise RuntimeError("Acceptance task did not succeed: %s" % value.get("error"))
                sleep(1)
            raise TimeoutError("Source acceptance task exceeded its time budget")

        call("/api/v1/workspace/session")
        root = "/api/v1/workspace"
        original = call(root + "/examples/system")["definition"]
        directory = call("/api/v1/model-center/research-inputs")
        assert directory["total"] == 63
        third_party = [e for e in directory["items"] if e["category"] == "third_party"]

        def configure(entry: dict, role: str = "covariate") -> dict:
            """通过公开目录采用，属性不由验收脚本重新发明。"""
            selectors = {name: values["enum"][0] for name, values in entry["source"]["selection_schema"]["properties"].items()}
            return call("/api/v1/model-center/research-inputs/configure", {"key": entry["key"], "selectors": selectors, "role": role})

        def definition(entries: list[dict]) -> dict:
            """构建同一真实可执行回归合同，不注册私有变量。"""
            plan = deepcopy(original)
            label = next(e for e in directory["items"] if e["variable"]["code"] == "lai")
            configs = [configure(label, "target")] + [configure(e) for e in entries]
            plan["name"] = "天气与叶面积指数关系研究"
            plan["question"] = "真实平台资料与构造标签的工程闭环验收，不用于农业精度结论"
            plan["variables"] = [c["variable"] for c in configs]
            plan["collection_requirements"] = [c["requirement"] for c in configs]
            plan["input_recipes"]["observations"]["variable_codes"] = [v["code"] for v in plan["variables"]]
            plan["input_recipes"]["regression_config"]["value"] = {"features": [e["variable"]["code"] for e in entries], "targets": ["lai"], "training_end": "2025-05-10"}
            plan["evaluation"]["target_codes"] = ["lai"]
            return plan

        def acquire(saved: dict, start: str, end: str) -> tuple[list[str], list[dict]]:
            """来源、范围由准确草稿绑定；真实采集经海豚和 Worker。"""
            created = call(root + "/plans/" + saved["design_id"] + "/input-acquisitions", {
                "expected_revision": saved["revision"], "object": {"field_ref": "provider-study-reference", "crop_code": "potato", "season_ref": "2025"},
                "reference_point": {"latitude": 50.46, "longitude": 119.85}, "start_date": start, "end_date": end})
            identity = created["acquisition_id"]
            value = wait(root + "/input-acquisitions/" + identity)
            records = [call(root + "/input-snapshots/" + reference) for reference in value["snapshot_ids"]]
            proof["acquisitions"].append({"acquisition_id": identity, "snapshot_ids": value["snapshot_ids"], "columns": [r["observations"]["columns"][0]["code"] for r in records]})
            print("Collected %s exact input snapshots" % len(records), flush=True)
            return value["snapshot_ids"], records

        diagnostic = call(root + "/plans", {"definition": definition(third_party)})
        _, all_records = acquire(diagnostic, "2025-04-01", "2025-04-01")
        assert len(all_records) == 18
        proof["third_party_inputs_collected"] = 18
        factors = [e for e in third_party if e["variable"]["code"] in {"temperature_mean_daily", "solar_radiation_daily"}]
        plan = definition(factors)
        saved = call(root + "/plans", {"definition": plan})
        source_ids, records = acquire(saved, "2025-04-01", "2025-05-30")
        table = deepcopy(records[0]["observations"])
        for item in records[1:]:
            other = item["observations"]
            table["columns"].extend(other["columns"])
            for row, extra in zip(table["rows"], other["rows"], strict=True):
                assert row["object"] == extra["object"] and row["business_date"] == extra["business_date"]
                row["values"].update(extra["values"])
        label = next(v for v in plan["variables"] if v["code"] == "lai")
        table["columns"].append({"code": "lai", "name": label["name"], "unit": label["unit"], "value_kind": "observed"})
        for row in table["rows"]:
            row["values"]["lai"] = 1 + .01 * row["values"]["temperature_mean_daily"] + .00001 * row["values"]["solar_radiation_daily"]
        common = {"observations": table, "source_snapshot_ids": source_ids, "data_kind": "user_supplied"}
        checked = call(root + "/check-execution", {"definition": plan, "design_id": saved["design_id"], "operation": "train", **common})
        assert checked["can_execute"], checked
        saved = call(root + "/plans/" + saved["design_id"], {"definition": plan, "expected_revision": saved["revision"], **common}, method="PUT")
        reopened = call(root + "/plans/" + saved["design_id"])
        assert reopened["source_snapshot_ids"] == source_ids
        run = call(root + "/runs", {"design_id": saved["design_id"], "expected_revision": saved["revision"], **common})
        run = wait(root + "/runs/" + run["run_id"])
        proof["runs"].append({k: run[k] for k in ("run_id", "kind", "status", "scheduler_id", "result_sha256")})
        model = call(root + "/models", {"run_id": run["run_id"], "name": "天气因素与叶面积指数关系模型"})
        training_refs = [i["source_snapshot"]["snapshot_id"] for i in model["model_json"]["input_sources"]["inputs"] if i["channel"] == "source_snapshot"]
        assert set(training_refs) == set(source_ids)
        prediction_ids, predicted_records = acquire(saved, "2025-06-01", "2025-06-05")
        prediction = deepcopy(predicted_records[0]["observations"])
        for item in predicted_records[1:]:
            prediction["columns"].extend(item["observations"]["columns"])
            for row, extra in zip(prediction["rows"], item["observations"]["rows"], strict=True):
                row["values"].update(extra["values"])
        outcome = call(root + "/predictions", {"model_id": model["model_id"], "observations": prediction, "source_snapshot_ids": prediction_ids})
        outcome = wait(root + "/runs/" + outcome["run_id"])
        proof["runs"].append({k: outcome[k] for k in ("run_id", "kind", "status", "scheduler_id", "result_sha256")})
        assert call(root + "/models/" + model["model_id"])["model_sha256"] == model["model_sha256"]
        assert all(r["component"]["code"] != "multivariate_linear_training" for r in outcome["result_json"]["receipts"])
        proof.update(design_id=saved["design_id"], model_id=model["model_id"], model_sha256=model["model_sha256"],
                     training_source_ids=source_ids, prediction_source_ids=prediction_ids, prediction_rows=5,
                     metrics=run["result_json"]["metrics"], all_success=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Source acquisition, saved study, trained model and new-input prediction succeeded", flush=True)


if __name__ == "__main__":
    main()
