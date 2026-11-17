# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 15:21
# @Author  : Codex
# @File    : verify.py
"""按统一文件协议独立验证窗口、缺日和错误输入，支持准确离线镜像。"""

from argparse import ArgumentParser
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from components.template.verify import command


def verify(image: str | None = None) -> None:
    """七日最高温36度产生正信号，缺日低温不允许判为阴性。"""
    original = {
        "columns": [
            {
                "code": "temperature_maximum_daily",
                "name": "日最高气温",
                "unit": "celsius",
                "value_kind": "estimated",
            }
        ],
        "rows": [
            {
                "object": {
                    "field_ref": "field-a",
                    "crop_code": "wheat",
                    "season_ref": "2026",
                },
                "business_date": "2026-11-%02d" % day,
                "values": {"temperature_maximum_daily": 36},
            }
            for day in range(1, 8)
        ],
        "source_sha256": ["a" * 64],
    }
    for case in (
        "valid",
        "partial",
        "unit",
        "duplicate",
        "empty",
        "boolean",
        "future",
        "tamper",
    ):
        table = deepcopy(original)
        if case == "partial":
            table["rows"] = table["rows"][:1]
            table["rows"][0]["values"]["temperature_maximum_daily"] = 20
        if case == "unit":
            table["columns"][0]["unit"] = "kelvin"
        if case == "duplicate":
            table["rows"].append(deepcopy(table["rows"][0]))
        if case == "empty":
            table["rows"] = []
        if case == "boolean":
            table["rows"][0]["values"]["temperature_maximum_daily"] = True
        if case == "future":
            table["rows"][0]["business_date"] = "2026-11-08"
        with TemporaryDirectory() as directory:
            inputs, outputs = Path(directory) / "input", Path(directory) / "output"
            inputs.mkdir()
            outputs.mkdir()
            data = json.dumps(table, ensure_ascii=False).encode("utf-8")
            (inputs / "observations.json").write_bytes(data)
            request = {
                "protocol_version": "1.0",
                "invocation_id": "0196d000-0000-7000-8000-000000000001",
                "component": {"code": "catalog_weather_conditions", "revision": 1},
                "parameters": {
                    "rule": "heat_exposure",
                    "as_of": "2026-11-07",
                    "window_days": 7,
                    "variables": ["temperature_maximum_daily"],
                },
                "inputs": {
                    "observations": {
                        "path": "observations.json",
                        "sha256": "0" * 64
                        if case == "tamper"
                        else sha256(data).hexdigest(),
                    }
                },
            }
            (inputs / "request.json").write_text(json.dumps(request), encoding="utf-8")
            args = (
                command(inputs, outputs, image)
                if image
                else [
                    sys.executable,
                    "-m",
                    "components.field_research.entrypoint",
                    "--input-dir",
                    str(inputs),
                    "--output-dir",
                    str(outputs),
                ]
            )
            result = subprocess.run(
                args,
                env={**os.environ, "COMPONENT_CODE": "catalog_weather_conditions"},
                timeout=45,
                capture_output=True,
            )
            if case not in {"valid", "partial"}:
                assert result.returncode == 2 and not list(outputs.iterdir()), (
                    case,
                    result.stderr,
                )
                continue
            assert result.returncode == 0, (case, result.stderr)
            manifest = json.loads((outputs / "result.json").read_bytes())
            assert set(manifest["outputs"]) == {"report", "series"}
            for port in ("report", "series"):
                assert (
                    manifest["outputs"][port]["sha256"]
                    == sha256((outputs / (port + ".json")).read_bytes()).hexdigest()
                )
            report = json.loads((outputs / "report.json").read_bytes())["results"][0]
            assert report["result"] == (
                "triggered" if case == "valid" else "not_evaluated"
            )
            assert report["window"]["valid_days"] == (7 if case == "valid" else 1)
            assert report["metric"] == (36 if case == "valid" else 20)
    print("Weather file protocol: two positive and six rejection cases passed")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--image")
    verify(parser.parse_args().image)
