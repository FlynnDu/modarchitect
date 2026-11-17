# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 19:31
# @Author  : Codex
# @File    : verify_chain.py
"""用冻结合成输入复跑模型成果传递和关键拒绝场景。"""

from argparse import ArgumentParser
from copy import deepcopy
from datetime import date, timedelta
from hashlib import sha256
import json
import math
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = {
    "historical_logistic_forecast": ("historical_logistic", "historical-logistic"),
    "research_forecast_feature_join": ("forecast_join", "forecast-join"),
    "multivariate_linear_regression": ("multivariate_regression", "multivariate-regression"),
}
INVOCATION = "0196d000-0000-7000-8000-000000000001"


def observation_fixture() -> tuple[dict, float]:
    """生成历史曲线、回归训练期和一个留出日期的独立已知答案。"""
    rows = []
    for offset in range(17):
        days = offset * 5
        ndvi = 0.20 + ((offset * 7) % 11) / 20
        baseline = 100 / (1 + math.exp(-0.12 * (days - 25)))
        actual = baseline if offset < 12 else 0.85 * baseline + 12 * ndvi + 3
        rows.append({
            "object": {"field_ref": "fixture-field", "crop_code": "wheat", "season_ref": "fixture-season"},
            "business_date": (date(2026, 6, 1) + timedelta(days=offset)).isoformat(),
            "values": {"day": days, "height": actual, "ndvi": ndvi},
        })
    expected = rows[-1]["values"]["height"]
    # 这条未来标签不得影响任何上游拟合或下游训练。
    rows[-1]["values"]["height"] = 999
    table = {
        "columns": [
            {"code": code, "name": code, "unit": unit, "value_kind": "observed"}
            for code, unit in (("day", "day"), ("height", "cm"), ("ndvi", "1"))
        ],
        "rows": rows,
        "source_sha256": ["a" * 64],
    }
    return table, expected


def command(component: str, inputs: Path, outputs: Path, containers: bool) -> list[str]:
    """在独立进程或受限的已加载镜像中执行同一文件合同。"""
    folder, tag = COMPONENTS[component]
    if not containers:
        return [
            sys.executable, "-m", "components.%s.entrypoint" % folder,
            "--input-dir", str(inputs), "--output-dir", str(outputs),
        ]
    inputs.chmod(0o755)
    outputs.chmod(0o777)
    return [
        "docker", "run", "--rm", "--pull=never", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--memory", "256m", "--cpus", "1", "--pids-limit", "32",
        "--mount", "type=bind,source=%s,target=/work/input,readonly" % inputs,
        "--mount", "type=bind,source=%s,target=/work/output" % outputs,
        "modarchitect-%s:1" % tag,
    ]


def invocation(
    directory: Path, component: dict, parameters: dict, values: dict[str, bytes],
    *, containers: bool, rejected: bool = False,
) -> dict[str, bytes]:
    """将上游原始成果文件作为下游输入，并验证每个文件摘要。"""
    inputs, outputs = directory / "input", directory / "output"
    inputs.mkdir(parents=True)
    outputs.mkdir()
    refs = {}
    for port, raw in values.items():
        filename = "%s.json" % port
        (inputs / filename).write_bytes(raw)
        refs[port] = {"path": filename, "sha256": sha256(raw).hexdigest()}
    request = {
        "protocol_version": "1.0", "invocation_id": INVOCATION, "component": component,
        "parameters": parameters, "inputs": refs,
    }
    (inputs / "request.json").write_text(json.dumps(request), encoding="utf-8")
    result = subprocess.run(
        command(component["code"], inputs, outputs, containers), check=False,
        cwd=ROOT, capture_output=True, timeout=45,
    )
    if rejected:
        assert result.returncode == 2 and not list(outputs.iterdir()), result.stderr
        return {}
    assert result.returncode == 0, result.stderr
    manifest = json.loads((outputs / "result.json").read_bytes())
    assert manifest["invocation_id"] == INVOCATION
    files = {}
    for port, reference in manifest["outputs"].items():
        assert reference["path"] == "%s.json" % port
        raw = (outputs / reference["path"]).read_bytes()
        assert sha256(raw).hexdigest() == reference["sha256"]
        files[port] = raw
    return files


def run_sample(plan: dict, directory: Path, containers: bool) -> float:
    """按编译样例的节点顺序执行，验证实测标签和上游预测值分别保留。"""
    table, expected = observation_fixture()
    external = json.dumps(table).encode()
    products = {}
    for node in plan["composition"]["nodes"]:
        parameters = {}
        inputs = {}
        for binding in node["bindings"]:
            port, source = binding["port"], binding["source"]
            if port == "request":
                parameters = plan["input_recipes"][source["port"]]["value"]
            elif source["node"] is None:
                assert source["port"] == "observations"
                inputs[port] = external
            else:
                inputs[port] = products[source["node"]][source["port"]]
        products[node["code"]] = invocation(
            directory / node["code"], node["component"], parameters, inputs,
            containers=containers,
        )
    joined = json.loads(products["merge"]["table"])
    assert joined["rows"][-1]["values"]["height"] == 999
    assert joined["columns"][-1]["value_kind"] == "predicted"
    assert len(joined["source_sha256"]) == 2
    forecast = json.loads(products["regression"]["predictions"])["rows"]
    assert len(forecast) == 1 and forecast[0]["business_date"] == "2026-06-17"
    actual = forecast[0]["values"]["height"]
    assert math.isclose(actual, expected, abs_tol=1e-7), (actual, expected)

    upstream = json.loads(products["baseline"]["forecast"])
    merge = plan["composition"]["nodes"][1]["component"]
    parameters = plan["input_recipes"]["merge_config"]["value"]
    for index, change in enumerate(("wrong_object", "missing_date", "future_cutoff", "column_conflict")):
        bad = deepcopy(upstream)
        request = dict(parameters)
        if change == "wrong_object":
            bad["rows"][0]["object"]["field_ref"] = "other-field"
        elif change == "missing_date":
            bad["rows"].pop()
        elif change == "future_cutoff":
            bad["fit_through"] = "2026-06-13"
        else:
            request["output_code"] = "height"
        invocation(
            directory / ("bad_merge_%d" % index), merge, request,
            {"observations": external, "forecast": json.dumps(bad).encode()},
            containers=containers, rejected=True,
        )
    baseline = plan["composition"]["nodes"][0]["component"]
    request = {**plan["input_recipes"]["baseline_config"]["value"], "fit_through": "2026-06-02"}
    invocation(directory / "bad_baseline", baseline, request, {"observations": external}, containers=containers, rejected=True)
    return actual


def main() -> None:
    """读取已登记的串联样例并复跑三节点计算。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--containers", action="store_true")
    parser.add_argument("--plan", type=Path, default=ROOT / "modarchitect/web/designer/chain-example.json")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_bytes())
    with TemporaryDirectory() as temporary:
        actual = run_sample(plan, Path(temporary), args.containers)
    print("Chain prediction %.8f cm. Rejected wrong object, missing date, future cutoff, duplicate column and insufficient history." % actual)


if __name__ == "__main__":
    main()
