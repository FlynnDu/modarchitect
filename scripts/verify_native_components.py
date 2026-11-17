# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 16:18
# @Author  : Codex
# @File    : verify_native_components.py
"""在独立 Worker 验收环境复跑原生制品正例及科学负例。"""

import argparse
from copy import deepcopy
import json
from pathlib import Path

from modarchitect.contracts.research.plans import ResearchPlan
from modarchitect.runtime.containers import ContainerRunner
from modarchitect.runtime.executor import execute
from modarchitect.runtime.service import execution_profiles
from modarchitect.study_templates import frozen_inputs, templates
from modarchitect.validation import compile_plan


def payload(row: dict) -> dict:
    """封存组件交接需要的最小真实输入，保留完整原生科学类型。"""
    definition = row["definition"]
    return {"kind": row["operation"], "plan": definition, "order": compile_plan(ResearchPlan.model_validate(definition))["order"], "artifact_inputs": frozen_inputs(row), "profiles": execution_profiles(definition), "expected_outputs": row.get("expected_outputs", {})}


def main() -> None:
    """正例必须先全部成功；再证明缺小时、标签性质及留出泄露受到拒绝。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proof = {"positive": [], "negative": []}
    runner = ContainerRunner()
    values = {}
    try:
        for row in templates():
            if "bundle_sha256" not in row:
                continue
            body = payload(row)
            result = execute(body, runner)
            assert result["pipeline"] is None
            values[row["id"]] = body
            proof["positive"].append({"template_id": row["id"], "template_sha256": row["sha256"], "revision": row["revision"], "receipts": result["receipts"]})
            print("Native positive passed: %s" % row["id"], flush=True)
        cases = []
        missing_hour = deepcopy(values["greenhouse-water-balance"])
        missing_hour["artifact_inputs"]["node_2_request"]["hours"].pop()
        cases.append(("missing_weighing_hour", missing_hour))
        for label in ("label_nature", "experimental_unit_leakage", "feature_availability"):
            body = deepcopy(values["greenhouse-random-forest"])
            data = body["artifact_inputs"]["dataset"]
            if label == "label_nature":
                data["target"]["value_kind"] = "estimated"
            elif label == "experimental_unit_leakage":
                data["samples"][-1]["experimental_unit_ref"] = data["samples"][0]["experimental_unit_ref"]
            else:
                data["samples"][0]["feature_available_at"] = "2025-01-10T00:00:00+00:00"
            cases.append((label, body))
        for name, body in cases:
            try:
                execute(body, runner)
            except ValueError:
                proof["negative"].append({"case": name, "rejected": True})
                print("Native negative rejected: %s" % name, flush=True)
            else:
                raise AssertionError("Native component accepted invalid scientific evidence")
    finally:
        runner.close()
        args.output.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
