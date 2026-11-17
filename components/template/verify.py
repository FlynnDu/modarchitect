# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 16:18
# @Author  : Codex
# @File    : verify.py
"""通过同一可执行入口验证样例成果及应拒绝输入。"""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ENTRYPOINT = Path(__file__).with_name("entrypoint.py")


def command(inputs: Path, outputs: Path, image: str | None) -> list[str]:
    """选择独立进程或本地离线容器，复用相同输入和断言。"""
    if image is None:
        return [
            sys.executable,
            str(ENTRYPOINT),
            "--input-dir",
            str(inputs),
            "--output-dir",
            str(outputs),
        ]
    outputs.chmod(0o777)
    return [
        "docker",
        "run",
        "--pull=never",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "128m",
        "--cpus",
        "1",
        "--pids-limit",
        "32",
        "--mount",
        "type=bind,source=%s,target=/work/input,readonly" % inputs,
        "--mount",
        "type=bind,source=%s,target=/work/output" % outputs,
        image,
    ]


def verify_case(
    minimum: int, *, tamper: bool = False, image: str | None = None
) -> None:
    """以真实文件调用验证一个正例、数量不足或篡改摘要。"""
    with TemporaryDirectory() as directory:
        work = Path(directory)
        inputs, outputs = work / "input", work / "output"
        inputs.mkdir()
        outputs.mkdir()
        table = {
            "columns": [{"code": "driver"}],
            "rows": [{"driver": 1}],
            "source_sha256": ["a" * 64],
        }
        content = json.dumps(table).encode("utf-8")
        digest = "0" * 64 if tamper else sha256(content).hexdigest()
        (inputs / "table.json").write_bytes(content)
        invocation = "0196d000-0000-7000-8000-000000000001"
        request = {
            "protocol_version": "1.0",
            "invocation_id": invocation,
            "component": {"code": "research_table_quality_check", "revision": 1},
            "parameters": {"minimum_valid_rows": minimum},
            "inputs": {"table": {"path": "table.json", "sha256": digest}},
        }
        (inputs / "request.json").write_text(json.dumps(request), encoding="utf-8")
        process = subprocess.run(
            command(inputs, outputs, image),
            timeout=30,
            check=False,
            capture_output=True,
        )
        if tamper or minimum > 1:
            assert process.returncode == 2 and not list(outputs.iterdir())
            return
        assert process.returncode == 0, process.stderr
        result = json.loads((outputs / "result.json").read_bytes())
        data = (outputs / "checked_table.json").read_bytes()
        assert result["invocation_id"] == invocation
        assert result["outputs"]["checked_table"]["sha256"] == sha256(data).hexdigest()
        assert json.loads(data) == table


def main() -> None:
    """复跑通过、数量不足和篡改三个场景。"""
    parser = ArgumentParser(description="Verify the component file interface")
    parser.add_argument("--image", help="Run a locally installed OCI image")
    args = parser.parse_args()
    verify_case(1, image=args.image)
    verify_case(2, image=args.image)
    verify_case(1, tamper=True, image=args.image)
    print(
        "Component verification passed: success, insufficient rows, checksum mismatch"
    )


if __name__ == "__main__":
    main()
