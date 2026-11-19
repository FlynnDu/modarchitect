# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 01:18
# @Author  : Codex
# @File    : verify_input_sources.py
"""在独立服务创建专属验收空间，复跑系统来源和真实调度闭环。"""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import time
from uuid import uuid4

import httpx


def api(
    client: httpx.Client,
    method: str,
    path: str,
    body: dict | None = None,
    *,
    expected: int = 200,
) -> dict:
    """向专属验收会话提交有限请求，错误不输出数据正文或凭据。"""
    headers = {"X-Workspace-Request": "1", "Idempotency-Key": str(uuid4())}
    response = client.request(method, path, json=body, headers=headers)
    if response.status_code != expected:
        raise AssertionError(
            "Acceptance HTTP %s %s: expected %s, received %s"
            % (method, path, expected, response.status_code)
        )
    return response.json()


def wait_run(client: httpx.Client, run: dict) -> dict:
    """等待本次真实调度，保留海豚身份，失败和超时均不记为通过。"""
    deadline = time.monotonic() + 240
    previous = None
    while time.monotonic() < deadline:
        run = api(client, "GET", "/api/v1/workspace/runs/" + run["run_id"])
        if run["status"] != previous:
            print("Acceptance run %s: %s" % (run["run_id"], run["status"]), flush=True)
            previous = run["status"]
        if run["status"] == "succeeded":
            assert run["scheduler_id"]
            return run
        if run["status"] in {"failed", "uncertain"}:
            raise AssertionError("Acceptance execution failed: %s" % run["status"])
        time.sleep(2)
    raise AssertionError("Acceptance execution timed out")


def scenario(
    client: httpx.Client, kind: str, data_kind: str, *, contextual: bool = False
) -> dict:
    """保存并重开指定演示，执行训练、保存模型和独立推理。"""
    base = "/api/v1/workspace"
    study = api(client, "GET", base + "/examples/" + kind)
    if contextual:
        study["definition"]["schema_version"] = "1.5"
        for variable in study["definition"]["variables"]:
            variable["role"] = "covariate"
    study["definition"]["name"] += " · 输入来源工程验收"
    saved = api(
        client,
        "POST",
        base + "/plans",
        {
            "definition": study["definition"],
            "observations": study["observations"],
            "data_kind": data_kind,
        },
    )
    reopened = api(client, "GET", base + "/plans/" + saved["design_id"])
    assert reopened["configuration"]["definition"] == study["definition"]
    assert reopened["observations"]["rows"] == study["observations"]["rows"]
    trained = wait_run(
        client,
        api(
            client,
            "POST",
            base + "/runs",
            {
                "design_id": saved["design_id"],
                "expected_revision": saved["revision"],
                "observations": study["observations"],
                "data_kind": data_kind,
                **({"operation": "train"} if contextual else {}),
            },
        ),
    )
    result = trained["result_json"]
    assert max(m["rmse"] for m in result["metrics"]) < 0.0001
    assert result["input_sources"] == result["pipeline"]["input_sources"]
    expected_channel = (
        "workspace_manual_entry" if data_kind == "user_supplied" else "synthetic_demo"
    )
    assert all(
        s["channel"] == expected_channel for s in result["input_sources"]["inputs"]
    )
    model = api(
        client,
        "POST",
        base + "/models",
        {
            "run_id": trained["run_id"],
            "name": study["definition"]["name"],
        },
    )
    assert model["model_json"]["input_sources"] == result["input_sources"]
    predicted = wait_run(
        client,
        api(
            client,
            "POST",
            base + "/predictions",
            {
                "model_id": model["model_id"],
                "observations": study["prediction_observations"],
                "data_kind": data_kind,
            },
        ),
    )
    prediction = predicted["result_json"]
    assert prediction["pipeline"]["states"] == model["model_json"]["states"]
    assert prediction["input_sources"]["row_count"] == len(
        study["prediction_observations"]["rows"]
    )
    assert not any("training" in r["component"]["code"] for r in prediction["receipts"])
    if kind == "system":
        table = prediction["outputs"]["predictions"]
        inputs = {
            r["business_date"]: r["values"]
            for r in study["prediction_observations"]["rows"]
        }
        for row in table["rows"]:
            x = inputs[row["business_date"]]
            assert (
                abs(
                    row["values"]["lai"]
                    - (0.5 + 3 * x["canopy_cover"] + 0.0003 * x["tuber_dm_kg_ha"])
                )
                < 0.0001
            )
            assert (
                abs(
                    row["values"]["agb_kg_ha"]
                    - (300 + 1000 * x["canopy_cover"] + 2 * x["tuber_dm_kg_ha"])
                )
                < 0.0001
            )
    return {
        "kind": kind,
        "data_kind": data_kind,
        "contextual_usages": contextual,
        "design_id": saved["design_id"],
        "training_run_id": trained["run_id"],
        "training_scheduler_id": trained["scheduler_id"],
        "prediction_run_id": predicted["run_id"],
        "prediction_scheduler_id": predicted["scheduler_id"],
        "model_id": model["model_id"],
        "model_sha256": model["model_sha256"],
        "training_sources_sha256": result["input_sources"]["sha256"],
        "prediction_sources_sha256": prediction["input_sources"]["sha256"],
        "metrics": result["metrics"],
        "state_unchanged": True,
    }


def refusals(client: httpx.Client) -> dict:
    """证明删绑定、伪造单位及上传第三方数值不会获得执行资格。"""
    base = "/api/v1/workspace"
    study = api(client, "GET", base + "/examples/system")
    invalid = deepcopy(study["definition"])
    invalid["variables"][0]["unit"] = "forged"
    api(client, "POST", base + "/plans", {"definition": invalid}, expected=422)
    invalid = deepcopy(study["definition"])
    invalid["collection_requirements"][0].pop("catalog_binding")
    api(client, "POST", base + "/plans", {"definition": invalid}, expected=422)
    configured = api(
        client,
        "POST",
        "/api/v1/model-center/research-inputs/configure",
        {
            "key": "variable_source:temperature_mean_daily@1.0.0",
        },
    )
    plan = study["definition"]
    plan["variables"].append(configured["variable"])
    plan["collection_requirements"].append(configured["requirement"])
    plan["input_recipes"]["observations"]["variable_codes"].append(
        "temperature_mean_daily"
    )
    saved = api(client, "POST", base + "/plans", {"definition": plan})
    readiness = api(
        client, "GET", base + "/plans/" + saved["design_id"] + "/input-readiness"
    )
    assert not readiness["items"][-1]["execution"]["available"]
    table = study["observations"]
    table["columns"].append(
        {
            "code": "temperature_mean_daily",
            "name": configured["variable"]["name"],
            "unit": "celsius",
            "value_kind": "estimated",
        }
    )
    for row in table["rows"]:
        row["values"]["temperature_mean_daily"] = 20
    before = len(api(client, "GET", base + "/runs")["items"])
    rejected = api(
        client,
        "POST",
        base + "/runs",
        {
            "design_id": saved["design_id"],
            "expected_revision": saved["revision"],
            "observations": table,
        },
        expected=422,
    )
    assert "channel" in rejected["detail"]
    assert len(api(client, "GET", base + "/runs")["items"]) == before
    return {
        "unit_override_rejected": True,
        "unbound_input_rejected": True,
        "third_party_upload_rejected": True,
        "no_run_created_for_missing_channel": True,
    }


def main() -> None:
    """生成不含 Cookie 或凭据的工程验收记录；所有观测为构造验收数据。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        api(client, "GET", "/api/v1/workspace/session")
        catalog = api(client, "GET", "/api/v1/model-center/research-inputs")
        assert catalog["total"] == 63
        scenarios = [
            scenario(client, "system", "user_supplied"),
            scenario(client, "chain", "synthetic"),
        ]
        checks = refusals(client)
        with httpx.Client(base_url=args.base_url, timeout=30) as other:
            api(other, "GET", "/api/v1/workspace/session")
            api(
                other,
                "GET",
                "/api/v1/workspace/models/" + scenarios[0]["model_id"],
                expected=404,
            )
    proof = {
        "service": args.base_url,
        "engineering_fixture_only": True,
        "manual_entry_is_not_business_sync": True,
        "catalog_sha256": catalog["sha256"],
        "categories": catalog["categories"],
        "scenarios": scenarios,
        "refusals": checks,
        "cross_workspace_rejected": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Input source acceptance passed", flush=True)


if __name__ == "__main__":
    main()
