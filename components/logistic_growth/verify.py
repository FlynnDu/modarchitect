# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 16:22
# @Author  : Codex
# @File    : verify.py
"""用独立安装后的组件入口复跑固定逻辑斯蒂样例。"""

from argparse import ArgumentParser
import importlib.util
import json
import math
import subprocess
import sys


def invoke(request: dict) -> subprocess.CompletedProcess:
    """通过组件的公开数值协议运行单个有界样例。"""
    return subprocess.run(
        [sys.executable, "-I", "-m", "mlgrowth_logistic_growth"],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def verify(wheel_sha256: str | None = None) -> dict:
    """核验独立性、冻结制品身份、三参数容差与拒绝条件。"""
    for name in ("modarchitect", "pymlgrowth", "mlgrowth_contracts"):
        if importlib.util.find_spec(name) is not None:
            raise AssertionError(
                "The numeric component must be verified in its own environment"
            )
    x = list(range(0, 101, 10))
    y = [100.0 / (1 + math.exp(-0.1 * (value - 50.0))) for value in x]
    request = {
        "operation": "fit",
        "allow_extrapolation": False,
        "series": [{"key": "engineering", "x": x, "y": y}],
    }
    response = invoke(request)
    if response.returncode != 0:
        raise AssertionError(response.stderr)
    result = json.loads(response.stdout)
    runtime = result["runtime"]
    if wheel_sha256 is not None and runtime["artifact_sha256"] != wheel_sha256:
        raise AssertionError(
            "Installed wheel checksum differs from the expected artifact"
        )
    parameters = result["series"][0]["parameters"]
    for name, expected, tolerance in (
        ("asymptote", 100.0, 1e-4),
        ("rate", 0.1, 1e-6),
        ("inflection", 50.0, 1e-4),
    ):
        if not math.isclose(parameters[name], expected, rel_tol=0, abs_tol=tolerance):
            raise AssertionError(
                "Parameter %s is outside its engineering tolerance" % name
            )
    request["series"][0]["y"] = [1.0] * len(x)
    rejected = invoke(request)
    if rejected.returncode != 2 or rejected.stdout:
        raise AssertionError("A constant observed series must be rejected")
    return {
        "artifact_sha256": runtime["artifact_sha256"],
        "parameters": parameters,
        "rejected": "constant_series",
    }


def main() -> None:
    """打印可随制品留档的样例结果。"""
    parser = ArgumentParser(
        description="Verify the independently installed Logistic component"
    )
    parser.add_argument("--expected-wheel-sha256")
    args = parser.parse_args()
    print(json.dumps(verify(args.expected_wheel_sha256), allow_nan=False))


if __name__ == "__main__":
    main()
