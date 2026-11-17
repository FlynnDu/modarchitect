# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 12:56
# @Author  : Codex
# @File    : verify.py
"""通过实际文件入口验证独立预期与拒绝样例，可复跑准确镜像。"""

from argparse import ArgumentParser
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from components.template.verify import command

EXAMPLES = Path(__file__).with_name("examples")


def verify(image: str | None = None) -> None:
    """固定算例均值为二、样本标准差为一，另外核对六种失败输入。"""
    original = json.loads((EXAMPLES / "observations.json").read_bytes())
    expected = json.loads((EXAMPLES / "expected-summary.json").read_bytes())
    for case in (
        "valid",
        "singleton",
        "unknown",
        "duplicate",
        "boolean",
        "nonfinite",
        "nature",
        "tamper",
    ):
        table, parameters = deepcopy(original), {"variables": ["lai"]}
        if case == "singleton":
            table["rows"] = table["rows"][:1]
        if case == "unknown":
            parameters["variables"] = ["missing"]
        if case == "duplicate":
            parameters["variables"] = ["lai", "lai"]
        if case == "boolean":
            table["rows"][0]["values"]["lai"] = True
        if case == "nonfinite":
            table["rows"][0]["values"]["lai"] = float("inf")
        if case == "nature":
            table["columns"][0]["value_kind"] = "unknown"
        with TemporaryDirectory() as directory:
            work = Path(directory)
            inputs, outputs = work / "input", work / "output"
            inputs.mkdir()
            outputs.mkdir()
            content = json.dumps(table, ensure_ascii=False).encode("utf-8")
            (inputs / "observations.json").write_bytes(content)
            request = {
                "protocol_version": "1.0",
                "invocation_id": "0196d000-0000-7000-8000-000000000001",
                "component": {"code": "research_descriptive_statistics", "revision": 1},
                "parameters": parameters,
                "inputs": {
                    "observations": {
                        "path": "observations.json",
                        "sha256": "0" * 64
                        if case == "tamper"
                        else sha256(content).hexdigest(),
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
                    "components.descriptive_statistics.entrypoint",
                    "--input-dir",
                    str(inputs),
                    "--output-dir",
                    str(outputs),
                ]
            )
            process = subprocess.run(args, timeout=45, check=False, capture_output=True)
            if case not in {"valid", "singleton"}:
                assert process.returncode == 2 and not list(outputs.iterdir()), case
                continue
            assert process.returncode == 0, process.stderr
            manifest = json.loads((outputs / "result.json").read_bytes())
            data = (outputs / "summary.json").read_bytes()
            assert manifest["invocation_id"] == request["invocation_id"]
            assert manifest["outputs"]["summary"]["sha256"] == sha256(data).hexdigest()
            summary = json.loads(data)
            if case == "valid":
                assert summary == expected
            else:
                assert summary["row_count"] == 1
                assert summary["variables"][0]["sample_std"] is None
    print(
        "Descriptive statistics file protocol: 2 positive and 6 rejection cases passed"
    )


def main() -> None:
    """使用本地进程或指定离线容器执行相同验收。"""
    parser = ArgumentParser(description="Verify descriptive statistics component")
    parser.add_argument("--image")
    verify(parser.parse_args().image)


if __name__ == "__main__":
    main()
