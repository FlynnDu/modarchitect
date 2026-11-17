# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 18:33
# @Author  : Codex
# @File    : verify.py
"""复跑回归文件协议的单目标、双目标与失败样例。"""

from argparse import ArgumentParser
from datetime import date, timedelta
from hashlib import sha256
import json
import math
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from components.template.verify import command

MODULE = "components.multivariate_regression.entrypoint"
ROOT = Path(__file__).resolve().parents[2]
FEATURES = ["ndvi", "soil_water", "temperature"]
TARGETS = ["height", "leaf_area"]


def observation_table() -> dict:
    """生成六天满秩数据，最后一天留作预测并写入异常实测值。"""
    rows = []
    samples = [
        (0.2, 0.30, 20), (0.3, 0.30, 20), (0.2, 0.35, 20),
        (0.2, 0.30, 24), (0.4, 0.34, 23), (0.5, 0.40, 22),
    ]
    for offset, (ndvi, soil, temperature) in enumerate(samples):
        rows.append({
            "object": {"field_ref": "test-field", "crop_code": "wheat", "season_ref": "test-season"},
            "business_date": (date(2026, 7, 1) + timedelta(days=offset)).isoformat(),
            "values": dict(zip(FEATURES + TARGETS, [
                ndvi, soil, temperature,
                5 + 20 * ndvi + 10 * soil + temperature,
                1 + 5 * ndvi + 3 * soil + 2 * temperature,
            ], strict=True)),
        })
    rows[-1]["values"].update(height=900, leaf_area=999)
    return {
        "columns": [{"code": code, "name": code, "unit": "1", "value_kind": "observed"} for code in FEATURES + TARGETS],
        "rows": rows, "source_sha256": ["a" * 64],
    }


def verify_case(targets: list[str], *, failure: str | None, image: str | None) -> None:
    """通过实际文件与进程边界检查预测值、输出摘要和拒绝行为。"""
    with TemporaryDirectory() as temporary:
        directory = Path(temporary)
        inputs, outputs = directory / "input", directory / "output"
        inputs.mkdir()
        outputs.mkdir()
        table = observation_table()
        if failure == "rank":
            for row in table["rows"]:
                row["values"]["ndvi"] = 1
        if failure == "duplicate":
            table["rows"].append(table["rows"][0])
        content = json.dumps(table).encode("utf-8")
        checksum = "0" * 64 if failure == "checksum" else sha256(content).hexdigest()
        (inputs / "observations.json").write_bytes(content)
        invocation = "0196d000-0000-7000-8000-000000000001"
        request = {
            "protocol_version": "1.0", "invocation_id": invocation,
            "component": {"code": "multivariate_linear_regression", "revision": 1},
            "parameters": {"features": FEATURES, "targets": targets, "training_end": "2026-07-05"},
            "inputs": {"observations": {"path": "observations.json", "sha256": checksum}},
        }
        (inputs / "request.json").write_text(json.dumps(request), encoding="utf-8")
        arguments = command(inputs, outputs, image) if image else [
            sys.executable, "-m", MODULE, "--input-dir", str(inputs), "--output-dir", str(outputs),
        ]
        process = subprocess.run(arguments, timeout=30, check=False, capture_output=True, cwd=ROOT)
        if failure:
            assert process.returncode == 2 and not list(outputs.iterdir()), process.stderr
            return
        assert process.returncode == 0, process.stderr
        result = json.loads((outputs / "result.json").read_bytes())
        assert result["invocation_id"] == invocation
        assert set(result["outputs"]) == {"trained_model", "predictions"}
        data = {}
        for port, reference in result["outputs"].items():
            raw = (outputs / reference["path"]).read_bytes()
            assert reference["sha256"] == sha256(raw).hexdigest()
            data[port] = json.loads(raw)
        model = data["trained_model"]
        assert model["training_rows"] == 5 and model["target_codes"] == targets
        result_rows = data["predictions"]["rows"]
        assert len(result_rows) == 1 and result_rows[0]["business_date"] == "2026-07-06"
        values = result_rows[0]["values"]
        assert list(values) == targets
        expected = {"height": 41, "leaf_area": 48.7}
        assert all(math.isclose(values[code], expected[code], abs_tol=1e-8) for code in targets), values


def main() -> None:
    """核对一项及两项目标、不可拟合、重复观测和被篡改文件。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--image")
    args = parser.parse_args()
    for targets in (TARGETS[:1], TARGETS):
        verify_case(targets, failure=None, image=args.image)
    for failure in ("rank", "duplicate", "checksum"):
        verify_case(TARGETS, failure=failure, image=args.image)
    print("Regression component verified: one target, two targets, rank, duplicate and checksum")


if __name__ == "__main__":
    main()
