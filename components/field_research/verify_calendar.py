# -*- coding: utf-8 -*-
# @Time    : 2026/11/17 21:54
# @Author  : Codex
# @File    : verify_calendar.py
"""独立复跑版本化日期坐标的文件协议正反例，不依赖数据库或调度。"""

from argparse import ArgumentParser
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from components.template.verify import command


def verify(image: str | None = None) -> None:
    """验证稀疏日期准确换算、错误基准与篡改摘要拒绝，并核对真实成果字节。"""
    fixtures = Path(__file__).parent / "manifests/research_calendar_axis"
    for name in ("positive", "negative", "tamper"):
        case = json.loads((fixtures / ("positive.json" if name == "tamper" else name + ".json")).read_text(encoding="utf-8"))
        with TemporaryDirectory() as directory:
            inputs, outputs = Path(directory) / "input", Path(directory) / "output"
            inputs.mkdir()
            outputs.mkdir()
            raw = json.dumps(case["inputs"]["observations"]).encode("utf-8")
            (inputs / "observations.json").write_bytes(raw)
            invocation = "0196d000-0000-7000-8000-000000000001"
            request = {"protocol_version": "1.0", "invocation_id": invocation,
                       "component": {"code": "research_calendar_axis", "revision": 1},
                       "parameters": case["parameters"], "inputs": {"observations": {
                           "path": "observations.json", "sha256": "0" * 64 if name == "tamper" else sha256(raw).hexdigest()}}}
            (inputs / "request.json").write_text(json.dumps(request), encoding="utf-8")
            arguments = command(inputs, outputs, image) if image else [
                sys.executable, "-m", "components.field_research.entrypoint",
                "--input-dir", str(inputs), "--output-dir", str(outputs)]
            result = subprocess.run(arguments, env={**os.environ, "COMPONENT_CODE": "research_calendar_axis"}, capture_output=True, timeout=45)
            if name != "positive":
                assert result.returncode == 2 and not list(outputs.iterdir()), (name, result.stderr)
                if name == "negative":
                    assert case["expected_error"].encode() in result.stderr
                continue
            assert result.returncode == 0, result.stderr
            receipt = json.loads((outputs / "result.json").read_bytes())
            assert receipt["invocation_id"] == invocation and set(receipt["outputs"]) == {"table"}
            reference = receipt["outputs"]["table"]
            actual = (outputs / reference["path"]).read_bytes()
            assert sha256(actual).hexdigest() == reference["sha256"]
            table = json.loads(actual)
            assert [row["values"][case["parameters"]["output_code"]] for row in table["rows"]] == case["expected_values"]
            assert table["source_sha256"] == case["inputs"]["observations"]["source_sha256"]
    print("Calendar file protocol: sparse dates and two rejection cases passed")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--image")
    verify(parser.parse_args().image)
