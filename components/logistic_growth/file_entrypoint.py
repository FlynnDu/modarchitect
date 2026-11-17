# -*- coding: utf-8 -*-
# @Time    : 2026/11/6 19:30
# @Author  : feidu
# @File    : file_entrypoint.py
"""已冻结逻辑斯蒂 wheel 的文件协议桥接；该入口独立于 wheel 内容。"""

from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import re
import stat
import sys
from uuid import RFC_4122, UUID

from mlgrowth_logistic_growth.protocol import calculate, runtime_identity

_IDENTITY = {"code": "logistic_growth_numeric_file", "revision": 1}


def _read(path: Path, limit: int) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Logistic input must be a regular file without links")
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Logistic input exceeds its byte budget")
    return content


def _write(path: Path, value: dict) -> str:
    content = json.dumps(value, allow_nan=False, separators=(",", ":")).encode("utf-8")
    with path.open("xb") as stream:
        stream.write(content)
    return sha256(content).hexdigest()


def _input(directory: Path, ref: dict, limit: int) -> dict:
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
        raise ValueError("Invalid logistic file reference")
    filename = ref["path"]
    if (
        not isinstance(filename, str)
        or re.fullmatch(r"[a-z][a-z0-9_]{0,95}\.json", filename) is None
    ):
        raise ValueError("Logistic input path must be a single JSON filename")
    content = _read(directory / filename, limit)
    if sha256(content).hexdigest() != ref["sha256"]:
        raise ValueError("Logistic input checksum differs")
    value = json.loads(content.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Logistic input must be a JSON object")
    return value


def run(input_dir: Path, output_dir: Path) -> None:
    """核对原 wheel 和依赖身份，转交原数值入口后再验证实际执行身份。"""
    request = json.loads(_read(input_dir / "request.json", 65_536).decode("utf-8"))
    if (
        not isinstance(request, dict)
        or set(request)
        != {"protocol_version", "invocation_id", "component", "parameters", "inputs"}
        or request["protocol_version"] != "1.0"
        or request["component"] != _IDENTITY
        or type(request["component"]["revision"]) is not int
        or request["parameters"] != {}
    ):
        raise ValueError("Unsupported logistic file request contract")
    invocation = request["invocation_id"]
    if not isinstance(invocation, str):
        raise ValueError("Expected a canonical invocation UUIDv7")
    uuid = UUID(invocation)
    if uuid.version != 7 or uuid.variant != RFC_4122 or str(uuid) != invocation:
        raise ValueError("Expected a canonical invocation UUIDv7")
    inputs = request["inputs"]
    if not isinstance(inputs, dict) or set(inputs) != {
        "numeric_request",
        "runtime_identity",
    }:
        raise ValueError(
            "Logistic file input ports differ from the registered contract"
        )
    expected = _input(input_dir, inputs["runtime_identity"], 65_536)
    if runtime_identity() != expected:
        raise ValueError("Logistic wheel or dependency identity differs")
    result = calculate(_input(input_dir, inputs["numeric_request"], 4_000_000))
    if result["runtime"] != expected:
        raise ValueError("Logistic runtime identity changed during execution")
    path = "numeric_result.json"
    digest = _write(output_dir / path, result)
    _write(
        output_dir / "result.json",
        {
            "protocol_version": "1.0",
            "invocation_id": invocation,
            "outputs": {"numeric_result": {"path": path, "sha256": digest}},
        },
    )


def main() -> int:
    parser = ArgumentParser(
        description="Run the frozen logistic wheel with the file protocol"
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.input_dir, args.output_dir)
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print("Logistic file invocation failed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
