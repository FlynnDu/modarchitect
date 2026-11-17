# -*- coding: utf-8 -*-
# @Time    : 2026/11/3 23:46
# @Author  : feidu
# @File    : protocol.py
"""独立数值包的有界JSON协议与运行时身份；不导入平台类型或提供路径执行。"""

import hashlib
from importlib.metadata import distribution, version
import json
from pathlib import Path
import platform
import re

from .core import evaluate_curve, fit_curve


def runtime_identity() -> dict:
    """返回可冻结的代码及依赖身份，不暴露宿主路径、环境变量或凭据。"""
    files = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(Path(__file__).parent.glob("*.py"))
    }
    digest = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    source = distribution("mlgrowth-logistic-growth").read_text("direct_url.json")
    archive = json.loads(source or "{}").get("archive_info", {})
    wheel_sha = archive.get("hashes", {}).get("sha256") or archive.get(
        "hash", ""
    ).removeprefix("sha256=")
    if not re.fullmatch(r"[0-9a-f]{64}", wheel_sha):
        raise ValueError("Numeric component must be installed from a hashed wheel")
    return {
        "protocol": "numeric_component_v1",
        "distribution": "mlgrowth-logistic-growth",
        "version": version("mlgrowth-logistic-growth"),
        "code_sha256": digest,
        "artifact_sha256": wheel_sha,
        "python": platform.python_version(),
        "dependencies": {name: version(name) for name in ("numpy", "scipy")},
        "dependency_records_sha256": {
            name: hashlib.sha256(
                distribution(name).read_text("RECORD").encode()
            ).hexdigest()
            for name in ("numpy", "scipy")
        },
    }


def calculate(body: dict) -> dict:
    """只接受拟合/求值及有限序列，不消费额外字段或任意模型代码。"""
    if not isinstance(body, dict) or set(body) != {
        "operation",
        "series",
        "allow_extrapolation",
    }:
        raise ValueError("Numeric component request fields are invalid")
    operation, series = body["operation"], body["series"]
    if type(body["allow_extrapolation"]) is not bool or (
        operation == "fit" and body["allow_extrapolation"]
    ):
        raise ValueError("Numeric component extrapolation policy is invalid")
    if (
        operation not in {"fit", "evaluate"}
        or not isinstance(series, list)
        or not 1 <= len(series) <= 32
    ):
        raise ValueError("Numeric component operation or series budget is invalid")
    results, seen = [], set()
    for item in series:
        fields = {"key", "x", "y" if operation == "fit" else "parameters"}
        if (
            not isinstance(item, dict)
            or set(item) != fields
            or not isinstance(item["key"], str)
            or not item["key"]
            or item["key"] in seen
        ):
            raise ValueError("Numeric component series fields or identity are invalid")
        seen.add(item["key"])
        result = (
            fit_curve(item["x"], item["y"])
            if operation == "fit"
            else evaluate_curve(
                item["parameters"], item["x"], body["allow_extrapolation"]
            )
        )
        results.append({"key": item["key"], **result})
    return {"runtime": runtime_identity(), "series": results}
