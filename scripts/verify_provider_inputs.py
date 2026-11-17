# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 22:05
# @Author  : Codex
# @File    : verify_provider_inputs.py
"""显式调用真实提供方，记录准确来源、标准结果及失败，不修改研究库。"""

import argparse
import json
from pathlib import Path

from modarchitect.input_sources.contracts import AcquisitionRequest
from modarchitect.input_sources.service import execute_acquisition, prepare_acquisition
from modarchitect.input_sources.transport import SourceUnavailable
from modarchitect.system_inputs import configure_input, input_catalog


def main() -> None:
    """通过正式获取合同逐类验收，证据保存到用户明确指定的文件。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["weather", "soil"], required=True)
    parser.add_argument("--depth", default="0-5cm")
    parser.add_argument("--latitude", type=float, default=50.46)
    parser.add_argument("--longitude", type=float, default=119.85)
    parser.add_argument("--start", default="2025-04-01")
    parser.add_argument("--end", default="2025-04-30")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    items = [
        i
        for i in input_catalog()["items"]
        if i["category"] == "third_party"
        and (i["source"]["code"] == "openmeteo_weather") == (args.source == "weather")
    ]
    configs = [
        configure_input(
            i["key"],
            {}
            if args.source == "weather"
            else {"depth": args.depth, "statistic": "mean"},
        )
        for i in items
    ]
    definition = {
        "variables": [c["variable"] for c in configs],
        "collection_requirements": [c["requirement"] for c in configs],
    }
    request = AcquisitionRequest.model_validate(
        {
            "expected_revision": 1,
            "object": {
                "field_ref": "provider-reference-check",
                "crop_code": "potato",
                "season_ref": "2025",
            },
            "reference_point": {"latitude": args.latitude, "longitude": args.longitude},
            "start_date": args.start,
            "end_date": args.end,
        }
    )
    try:
        result = execute_acquisition(
            prepare_acquisition(definition, request), lambda: None
        )
        evidence = {"source": args.source, "success": True, "snapshots": result}
    except (ValueError, OSError, SourceUnavailable) as exc:
        evidence = {"source": args.source, "success": False, "error": str(exc)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "source": args.source,
                "success": evidence["success"],
                "snapshots": len(evidence.get("snapshots", [])),
                "error": evidence.get("error"),
            },
            ensure_ascii=True,
        )
    )
    if not evidence["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
