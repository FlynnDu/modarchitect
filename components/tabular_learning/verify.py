# -*- coding: utf-8 -*-
# @Time    : 2026/11/16 20:25
# @Author  : Codex
# @File    : verify.py
"""用真实隔离容器复跑准确制品的双目标训练、无标签推理和科学反例。"""

import argparse
from copy import deepcopy
from datetime import date, timedelta
import json
import math
from pathlib import Path

from modarchitect.runtime.containers import Artifact, ContainerRunner


def verify(algorithm: str, profiles: dict, runner: ContainerRunner) -> dict:
    """独立常量真值验证三种算法，不用组件输出生成预期结果。"""
    columns = [{"code": code, "name": code, "unit": unit, "value_kind": kind} for code, unit, kind in (("temperature", "celsius", "estimated"), ("soil", "fraction", "estimated"), ("height", "cm", "observed"), ("leaf", "cm2", "observed"))]
    table = {"columns": columns, "rows": [{"object": {"field_ref": "component-test", "crop_code": "potato", "season_ref": "2026"}, "business_date": (date(2026, 5, 1) + timedelta(days=index)).isoformat(), "values": {"temperature": 15 + index % 9, "soil": 0.1 + index * 0.01, "height": 7, "leaf": 12}} for index in range(20)], "source_sha256": ["a" * 64]}
    parameters = {"features": ["temperature", "soil"], "targets": ["height", "leaf"], "training_end": "2026-05-16", "seed": 17}
    training, inference = algorithm + "_training", algorithm + "_predict"
    result = runner.call({"code": training, "revision": 1}, profiles[training + "@1"], parameters, {"observations": Artifact.encode(table)})
    model = result["trained_model"]
    future = {**table, "columns": columns[:2], "rows": [{**row, "values": {code: row["values"][code] for code in parameters["features"]}} for row in table["rows"][16:]]}
    predicted = runner.call({"code": inference, "revision": 1}, profiles[inference + "@1"], {}, {"observations": Artifact.encode(future), "model": model})
    assert len(predicted["predictions"].value["rows"]) == 4
    for row in predicted["predictions"].value["rows"]:
        assert math.isclose(row["values"]["height"], 7, abs_tol=1e-6)
        assert math.isclose(row["values"]["leaf"], 12, abs_tol=1e-6)
    wrong = deepcopy(future)
    wrong["columns"][0]["unit"] = "kelvin"
    try:
        runner.call({"code": inference, "revision": 1}, profiles[inference + "@1"], {}, {"observations": Artifact.encode(wrong), "model": model})
    except ValueError:
        pass
    else:
        raise AssertionError("Incorrect feature units were accepted")
    invalid = deepcopy(table)
    invalid["columns"][2]["value_kind"] = "estimated"
    try:
        runner.call({"code": training, "revision": 1}, profiles[training + "@1"], parameters, {"observations": Artifact.encode(invalid)})
    except ValueError:
        pass
    else:
        raise AssertionError("Estimated targets were accepted as observed labels")
    return {"algorithm": algorithm, "two_targets": True, "label_free_prediction": True, "wrong_unit_rejected": True, "estimated_target_rejected": True, "network": "none"}


def main() -> None:
    """只执行显式登记的制品，不从请求选择外部镜像。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runner = ContainerRunner()
    try:
        profiles = json.loads(args.profiles.read_text(encoding="utf-8"))
        proof = [verify(algorithm, profiles, runner) for algorithm in ("random_forest", "xgboost", "gaussian_process")]
        args.output.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(proof))
    finally:
        runner.close()


if __name__ == "__main__":
    main()
