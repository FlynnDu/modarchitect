# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 22:25
# @Author  : Codex
# @File    : verify.py
"""按真实文件协议独立复跑训练、串联、推理和应拒绝输入。"""

from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "components/logistic_growth/src"))


def call(
    root: Path, code: str, parameters: dict, inputs: dict[str, bytes]
) -> dict[str, bytes]:
    """写准确字节和摘要，直接使用组件共用的协议解析与成果落盘。"""
    from components.research_runtime.entrypoint import OPERATIONS
    from components.forecast_join.component import join_forecast
    from components.template.file_protocol import run

    operations = {
        **OPERATIONS,
        "research_forecast_feature_join": (("observations", "forecast"), join_forecast),
    }
    ports, calculate = operations[code]
    source, target = root / "input", root / "output"
    source.mkdir(parents=True)
    target.mkdir()
    refs = {}
    for port, raw in inputs.items():
        (source / (port + ".json")).write_bytes(raw)
        refs[port] = {"path": port + ".json", "sha256": sha256(raw).hexdigest()}
    request = {
        "protocol_version": "1.0",
        "invocation_id": "0196d000-0000-7000-8000-000000000001",
        "component": {"code": code, "revision": 1},
        "parameters": parameters,
        "inputs": refs,
    }
    (source / "request.json").write_text(json.dumps(request), encoding="utf-8")
    run(source, target, code, 1, ports, calculate)
    manifest = json.loads((target / "result.json").read_bytes())
    outputs = {}
    for port, ref in manifest["outputs"].items():
        raw = (target / ref["path"]).read_bytes()
        assert sha256(raw).hexdigest() == ref["sha256"]
        outputs[port] = raw
    return outputs


def encoded(table: dict) -> bytes:
    """为合成观测建立实际数据摘要，拒绝样例中的非有限数字。"""
    table = deepcopy(table)
    table["source_sha256"] = [
        sha256(json.dumps(table, sort_keys=True, allow_nan=False).encode()).hexdigest()
    ]
    return json.dumps(table, ensure_ascii=False, allow_nan=False).encode("utf-8")


def verify(root: Path, kind: str) -> None:
    """执行整条训练及独立预测，并用独立合成公式核对数值。"""
    example = json.loads(
        (ROOT / "modarchitect/web/designer" / (kind + "-study.json")).read_text(
            encoding="utf-8"
        )
    )
    observations, future = (
        encoded(example["observations"]),
        encoded(example["prediction_observations"]),
    )
    config = example["definition"]["input_recipes"]
    if kind == "chain":
        baseline = call(
            root / "baseline",
            "historical_logistic_training",
            config["baseline_config"]["value"],
            {"observations": observations},
        )
        joined = call(
            root / "join",
            "research_forecast_feature_join",
            config["merge_config"]["value"],
            {"observations": observations, "forecast": baseline["forecast"]},
        )
        new_forecast = call(
            root / "new-baseline",
            "historical_logistic_predict",
            {},
            {"model": baseline["trained_model"], "observations": future},
        )
        new_joined = call(
            root / "new-join",
            "research_forecast_feature_join",
            config["merge_config"]["value"],
            {"observations": future, "forecast": new_forecast["forecast"]},
        )
        observations, future = joined["table"], new_joined["table"]
    trained = call(
        root / "train",
        "multivariate_linear_training",
        config["regression_config"]["value"],
        {"observations": observations},
    )
    predicted = call(
        root / "predict",
        "multivariate_linear_predict",
        {},
        {"model": trained["trained_model"], "observations": future},
    )
    rows = json.loads(predicted["predictions"])["rows"]
    for row, source in zip(
        rows, example["prediction_observations"]["rows"], strict=True
    ):
        values = source["values"]
        expected = (
            20
            + 0.8 * values["day"]
            + 30 * values["ndvi"]
            + 10 * values["soil_water"]
            + 0.5 * values["temperature"]
        )
        if kind == "chain":
            expected = (
                0.85 * 100 / (1 + math.exp(-0.12 * (values["day"] - 25)))
                + 12 * values["ndvi"]
                + 10 * values["soil_water"]
                + 0.2 * values["temperature"]
                + 3
            )
        assert math.isclose(row["values"]["height"], expected, abs_tol=1e-5)
    bad = json.loads(future)
    feature = json.loads(trained["trained_model"])["state"]["feature_codes"][0]
    next(column for column in bad["columns"] if column["code"] == feature)["unit"] = "incorrect_unit"
    try:
        call(
            root / "reject",
            "multivariate_linear_predict",
            {},
            {"model": trained["trained_model"], "observations": encoded(bad)},
        )
    except ValueError:
        assert not list((root / "reject/output").iterdir())
    else:
        raise AssertionError("Incorrect inference units were accepted")
    print("%s: training, inference, artifact checksums and rejection passed" % kind)


if __name__ == "__main__":
    with TemporaryDirectory(prefix="modarchitect-components-") as directory:
        for example_kind in ("multivariable", "chain"):
            verify(Path(directory) / example_kind, example_kind)
