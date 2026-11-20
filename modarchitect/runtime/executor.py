# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 21:27
# @Author  : Codex
# @File    : executor.py
"""按封存拓扑交接实际成果，保存整条模型的训练状态并评价留出结果。"""

from copy import deepcopy
from datetime import date, timedelta
from time import monotonic
from collections.abc import Callable

from .containers import Artifact, ContainerRunner
from .service import profile_key
from ..contracts.model_center.components import Composition
from ..contracts.research.evaluation import PREDICTION_METRICS
from ..execution_contracts import compile_execution
from ..contracts.research.plans import TRAINING_CUTOFF


def observation_input(table: dict, variables: list[str]) -> Artifact:
    """按配方投影实际存在的列，独立推理允许输入中没有目标列。"""
    columns = [column for column in table["columns"] if column["code"] in variables]
    codes = {column["code"] for column in columns}
    return Artifact.encode(
        {
            **table,
            "columns": columns,
            "rows": [
                {
                    **row,
                    "values": {
                        key: value
                        for key, value in row["values"].items()
                        if key in codes
                    },
                }
                for row in table["rows"]
            ],
        }
    )


def configuration(recipe: dict, plan: dict, table: dict, context: dict | None = None,
                  training_cutoff: str | None = None) -> dict:
    """把显式运行槽位绑定到当次封存业务日及对象。"""
    result = dict(recipe["value"])
    if not recipe.get("runtime_fields"):
        return result
    cutoff = (context or {}).get("as_of") or max(row["business_date"] for row in table["rows"])
    if any(row["business_date"] > cutoff for row in table["rows"]):
        raise ValueError("Research data follows the sealed execution cutoff")
    gate = plan["evaluation"].get("numeric_gate")
    fit_cutoff = (
        (date.fromisoformat(gate["holdout_start"]) - timedelta(days=1)).isoformat()
        if gate
        else cutoff
    )
    slots = {
        "cutoff_date": cutoff,
        "fit_cutoff_date": fit_cutoff,
        "cutoff_timestamp": cutoff + "T23:59:59+08:00",
        "object": table["rows"][0]["object"],
        "season_start": (context or {}).get("period_start") or min(row["business_date"] for row in table["rows"]),
        "season_end": cutoff,
    }
    for key, slot in recipe.get("runtime_fields", {}).items():
        if slot == TRAINING_CUTOFF and training_cutoff is None:
            raise ValueError("Training cutoff was not sealed before execution")
        result[key] = training_cutoff if slot == TRAINING_CUTOFF else slots[slot]
    return result


def table_key(row: dict) -> tuple:
    """使用完整对象和业务日匹配预测与标签。"""
    obj = row["object"]
    return (obj["field_ref"], obj["crop_code"], obj["season_ref"], row["business_date"])


def evaluate(
    outputs: dict[str, dict], observed: dict, cutoffs: dict[str, str | None],
    metric_codes: list[str] | None = None,
) -> list[dict]:
    """只评价已产生预测且有同期实测的目标，逐目标保留覆盖和误差。"""
    actual = {table_key(row): row["values"] for row in observed["rows"]}
    metadata = {column["code"]: column for column in observed["columns"]}
    calculations = {
        code: compute for code, (_, compute) in PREDICTION_METRICS.items()
        if metric_codes is None or code in metric_codes
    }
    metrics = []
    for output, table in outputs.items():
        if not isinstance(table.get("columns"), list) or not isinstance(
            table.get("rows"), list
        ):
            continue
        for column in table["columns"]:
            if column.get("value_kind") != "predicted":
                continue
            code = column["code"]
            reference = metadata.get(code)
            cutoff = cutoffs.get(output)
            eligible = {key for key in actual if cutoff is None or key[3] > cutoff}
            if reference is None or reference["value_kind"] != "observed":
                metrics.append(
                    {
                        "output": output,
                        "target": code,
                        "unit": column["unit"],
                        "rows": 0,
                        "status": "awaiting_observations",
                    }
                )
                continue
            if reference["unit"] != column["unit"]:
                metrics.append(
                    {
                        "output": output,
                        "target": code,
                        "rows": 0,
                        "status": "reference_unit_mismatch",
                    }
                )
                continue
            pairs = [
                (row["values"][code], actual[table_key(row)][code])
                for row in table["rows"]
                if table_key(row) in eligible and code in actual[table_key(row)]
            ]
            if pairs:
                observed = [reference for _, reference in pairs]
                errors = [prediction - reference for prediction, reference in pairs]
                metrics.append(
                    {
                        "output": output,
                        "target": code,
                        "unit": column["unit"],
                        "rows": len(errors),
                        "coverage": len(errors) / len(eligible),
                        "expected_rows": len(eligible),
                        "status": "evaluated",
                        **{key: compute(errors, observed) for key, compute in calculations.items()},
                    }
                )
    return metrics


def execute(
    payload: dict, runner: ContainerRunner, heartbeat: Callable[[], None] | None = None
) -> dict:
    """训练时保存状态，预测时依次复用每个已训练节点及原变换。"""
    prediction = payload["kind"] == "predict"
    if not prediction:
        declarations = compile_execution(
            Composition.model_validate(payload["plan"]["composition"]),
            payload["kind"],
            payload["profiles"],
        )
        if payload.get("execution_contracts", declarations) != declarations:
            raise ValueError(
                "Frozen execution declaration differs from the exact component"
            )
    pipeline = (
        deepcopy(payload["pipeline"])
        if prediction
        else {
            "format": "research_pipeline_v1",
            "plan": payload["plan"],
            "order": payload["order"],
            "profiles": payload["profiles"],
            "states": {},
            "state_ports": {},
            "cutoffs": {},
            "training_data_kind": payload.get("data_kind", "user_supplied"),
        }
    )
    if not prediction and payload.get("input_sources") is not None:
        pipeline["input_sources"] = payload["input_sources"]
    plan, table = pipeline["plan"], payload.get("observations")
    if not prediction and table is not None:
        last = deepcopy(max(table["rows"], key=lambda row: row["business_date"]))
        last["business_date"] = (
            date.fromisoformat(last["business_date"]) + timedelta(days=1)
        ).isoformat()
        for column in table["columns"]:
            if column["unit"] == "day":
                last["values"][column["code"]] += 1
        pipeline["input_columns"] = table["columns"]
        pipeline["last_input"] = last
    nodes = {node["code"]: node for node in plan["composition"]["nodes"]}
    products, receipts = {}, []
    deadline = monotonic() + 240
    for code in pipeline["order"]:
        if monotonic() >= deadline:
            raise ValueError("Research run exceeded its total execution budget")
        if heartbeat is not None:
            heartbeat()
        node = nodes[code]
        component = node["component"]
        key = profile_key(component)
        profile = pipeline["profiles"][key]
        inputs, parameters = {}, {}
        for binding in node["bindings"]:
            source, port = binding["source"], binding["port"]
            if source.get("node") is not None:
                inputs[port] = products[source["node"]][source["port"]]
                continue
            recipe = plan["input_recipes"][source["port"]]
            if recipe["kind"] == "configuration":
                if not (prediction and profile.get("inference")):
                    parameters = configuration(recipe, plan, table, payload.get("execution_context"),
                                               payload.get("training_cutoff"))
            elif recipe["kind"] == "artifact":
                inputs[port] = Artifact.encode(payload["artifact_inputs"][source["port"]])
            else:
                inputs[port] = observation_input(table, recipe["variable_codes"])
        if not prediction:
            boundaries = [
                pipeline["cutoffs"].get(binding["source"].get("node"))
                for binding in node["bindings"]
            ]
            boundaries.extend(
                parameters.get(field) for field in ("training_end", "fit_through")
            )
            pipeline["cutoffs"][code] = max(
                (value for value in boundaries if value), default=None
            )
        if prediction and profile.get("inference"):
            inference = profile["inference"]
            infer_code, infer_revision = inference.rsplit("@", 1)
            component = {"code": infer_code, "revision": int(infer_revision)}
            profile = pipeline["profiles"][inference]
            inputs[profile.get("model_input", "model")] = Artifact.encode(
                pipeline["states"][code]
            )
            parameters = {}
        result = runner.call(component, profile, parameters, inputs)
        state_port = pipeline["profiles"][key].get("state_output")
        if not prediction and state_port:
            pipeline["states"][code] = result[state_port].value
            pipeline["state_ports"][code] = state_port
        if prediction and code in pipeline["states"]:
            result[pipeline["state_ports"][code]] = Artifact.encode(
                pipeline["states"][code]
            )
        products[code] = result
        receipts.append(
            {
                "node": code,
                "component": component,
                "image": profile["image"],
                "inputs": {port: item.digest for port, item in inputs.items()},
                "outputs": {port: item.digest for port, item in result.items()},
            }
        )
    outputs = {
        output["code"]: products[output["source"]["node"]][
            output["source"]["port"]
        ].value
        for output in plan["composition"]["outputs"]
    }
    for output in plan["composition"]["outputs"]:
        expected = payload.get("expected_outputs", {}).get(output["code"])
        if expected and products[output["source"]["node"]][output["source"]["port"]].digest != expected:
            raise ValueError("Frozen case output differs from its approved reference")
    if payload["kind"] == "train" and not pipeline["states"]:
        raise ValueError("Research graph did not produce a reusable training model")
    return {
        "outputs": outputs,
        "metrics": evaluate(
            outputs,
            table,
            {
                output["code"]: pipeline["cutoffs"].get(output["source"]["node"])
                for output in plan["composition"]["outputs"]
            },
            plan["evaluation"].get("metrics"),
        ) if table is not None else [],
        "receipts": receipts,
        "pipeline": pipeline if prediction or pipeline["states"] else None,
        "operation": payload["kind"],
        "data_kind": payload.get("data_kind", "user_supplied"),
        "input_sources": payload.get("input_sources"),
        "template_id": payload.get("template_id"),
    }
