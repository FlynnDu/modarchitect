# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 18:23
# @Author  : Codex
# @File    : file_protocol.py
"""运行独立组件共用的摘要绑定文件协议。"""

from argparse import ArgumentParser
from collections.abc import Callable
from hashlib import sha256
import json
from pathlib import Path
import re
import stat
import sys
from uuid import UUID

Calculator = Callable[[dict, dict], dict[str, dict]]


def read_bytes(path: Path, limit: int) -> bytes:
    """读取单个受限普通文件，拒绝链接及超预算输入。"""
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Expected a regular file without links")
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Input exceeds its byte budget")
    return content


def read_input(directory: Path, ref: dict) -> dict:
    """按安全文件名和摘要读取准确输入端口。"""
    filename = ref["path"]
    if set(ref) != {"path", "sha256"} or not re.fullmatch(
        r"[a-z][a-z0-9_]{0,95}\.json", filename
    ):
        raise ValueError("Invalid file reference")
    content = read_bytes(directory / filename, 4_000_000)
    if sha256(content).hexdigest() != ref["sha256"]:
        raise ValueError("Input checksum differs")
    table = json.loads(content)
    if not isinstance(table, dict):
        raise ValueError("Input port must contain a JSON object")
    return table


def write_output(directory: Path, name: str, value: dict) -> dict:
    """仅新建本次调用的成果文件并返回字节摘要。"""
    content = json.dumps(
        value, allow_nan=False, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    with (directory / name).open("xb") as stream:
        stream.write(content)
    return {"path": name, "sha256": sha256(content).hexdigest()}


def run(input_dir: Path, output_dir: Path, code: str, revision: int, ports: tuple[str, ...], calculate: Calculator) -> None:
    """核验调用、调用科学逻辑并最后写成果清单。"""
    request = json.loads(read_bytes(input_dir / "request.json", 65_536))
    if (
        set(request)
        != {"protocol_version", "invocation_id", "component", "parameters", "inputs"}
        or request["protocol_version"] != "1.0"
        or request["component"]
        != {"code": code, "revision": revision}
        or type(request["component"]["revision"]) is not int
        or set(request["inputs"]) != set(ports)
    ):
        raise ValueError("Invalid component invocation")
    invocation = UUID(request["invocation_id"])
    if invocation.version != 7 or str(invocation) != request["invocation_id"]:
        raise ValueError("Invalid invocation identity")
    inputs = {port: read_input(input_dir, request["inputs"][port]) for port in ports}
    results = calculate(inputs, request["parameters"])
    outputs = {
        port: write_output(output_dir, "%s.json" % port, value)
        for port, value in results.items()
    }
    write_output(
        output_dir,
        "result.json",
        {
            "protocol_version": "1.0",
            "invocation_id": str(invocation),
            "outputs": outputs,
        },
    )


def main(code: str, revision: int, ports: tuple[str, ...], calculate: Calculator) -> int:
    """为本地和容器提供同一个调用入口。"""
    parser = ArgumentParser(description="Run a frozen research component invocation")
    parser.add_argument("--input-dir", type=Path, default=Path("/work/input"))
    parser.add_argument("--output-dir", type=Path, default=Path("/work/output"))
    args = parser.parse_args()
    try:
        run(args.input_dir, args.output_dir, code, revision, ports, calculate)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, ArithmeticError) as exc:
        detail = ": " + str(exc)[:300] if isinstance(exc, ValueError) else ""
        print("Invalid research component invocation" + detail, file=sys.stderr)
        return 2
    return 0
