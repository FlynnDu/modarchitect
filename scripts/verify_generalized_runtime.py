# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 13:02
# @Author  : Codex
# @File    : verify_generalized_runtime.py
"""在专属工作区核对非训练运行与旧训练串联的真实调度兼容。"""

import argparse
import json
from pathlib import Path

import httpx

from scripts.verify_input_sources import api, scenario, wait_run


def analyze(client: httpx.Client) -> dict:
    """分析工程算例，重开成果，错误操作和模型登记均应明确拒绝。"""
    base = "/api/v1/workspace"
    study = api(client, "GET", base + "/examples/analysis")
    study["definition"]["name"] += " · 通用运行工程验收"
    saved = api(
        client,
        "POST",
        base + "/plans",
        {
            "definition": study["definition"],
            "observations": study["observations"],
            "data_kind": "synthetic",
        },
    )
    assert (
        api(client, "GET", base + "/plans/" + saved["design_id"])["configuration"][
            "definition"
        ]
        == study["definition"]
    )
    body = {
        "design_id": saved["design_id"],
        "expected_revision": saved["revision"],
        "observations": study["observations"],
        "data_kind": "synthetic",
    }
    for operation in ("train", "simulate", "calibrate"):
        api(
            client,
            "POST",
            base + "/runs",
            {**body, "operation": operation},
            expected=422,
        )
    run = wait_run(
        client, api(client, "POST", base + "/runs", {**body, "operation": "analyze"})
    )
    result = run["result_json"]
    assert (
        run["kind"] == "analyze"
        and result["pipeline"] is None
        and not result["metrics"]
    )
    summary = result["outputs"]["summary"]
    assert (
        summary["format"] == "research_descriptive_summary_v1"
        and summary["row_count"] == 60
    )
    assert {v["code"] for v in summary["variables"]} == {"lai", "canopy_cover"}
    assert (
        api(client, "GET", base + "/runs/" + run["run_id"])["result_sha256"]
        == run["result_sha256"]
    )
    api(
        client,
        "POST",
        base + "/models",
        {"run_id": run["run_id"], "name": "分析不能冒充模型"},
        expected=409,
    )
    return {
        "design_id": saved["design_id"],
        "run_id": run["run_id"],
        "scheduler_id": run["scheduler_id"],
        "result_sha256": run["result_sha256"],
        "summary": summary,
        "no_fake_model": True,
        "wrong_operations_rejected": True,
        "sources_sha256": result["input_sources"]["sha256"],
    }


def main() -> None:
    """只写不含 Cookie 的验收记录，明确所有科学数据均为工程构造。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://192.168.3.249:18925")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        api(client, "GET", "/api/v1/workspace/session")
        proof = {
            "engineering_fixture_only": True,
            "service": args.base_url,
            "analysis": analyze(client),
            "legacy_scenarios": [
                scenario(client, "system", "user_supplied"),
                scenario(client, "chain", "synthetic"),
            ],
        }
        with httpx.Client(base_url=args.base_url, timeout=30) as other:
            api(other, "GET", "/api/v1/workspace/session")
            api(
                other,
                "GET",
                "/api/v1/workspace/runs/" + proof["analysis"]["run_id"],
                expected=404,
            )
            proof["cross_workspace_rejected"] = True
        proof["node_usage_scenario"] = scenario(
            client, "system", "user_supplied", contextual=True
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Generalized runtime acceptance passed", flush=True)


if __name__ == "__main__":
    main()
