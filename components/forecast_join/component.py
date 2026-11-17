# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 19:25
# @Author  : Codex
# @File    : component.py
"""把历史预测因子按完整对象和业务日期合并到观测表。"""

from components.chain_tables import business_date, code, number, read_table


def join_forecast(inputs: dict, parameters: dict) -> dict[str, dict]:
    """保留基线截止日之后的观测行与实测标签，严格追加预测列。"""
    if set(parameters) != {"feature_code", "output_code"}:
        raise ValueError("Invalid forecast join parameters")
    feature, output = code(parameters["feature_code"]), code(parameters["output_code"])
    observations = inputs["observations"]
    predictions = inputs["forecast"]
    observed_columns, observed_rows = read_table(observations)
    predicted_columns, predicted_rows = read_table(predictions, forecast=True)
    if output in observed_columns:
        raise ValueError("Forecast feature would overwrite an observation")
    cutoff = business_date(predictions["fit_through"])
    selected = {key: row for key, row in observed_rows.items() if key[3] > cutoff}
    if not selected or selected.keys() != predicted_rows.keys():
        raise ValueError("Forecast object dates do not match post-cutoff observations")
    column = predicted_columns[feature]
    rows = [
        {**row, "values": {**row["values"], output: number(predicted_rows[key]["values"][feature])}}
        for key, row in selected.items()
    ]
    return {"table": {
        "columns": [*observed_columns.values(), {**column, "code": output}],
        "rows": rows,
        "source_sha256": list(dict.fromkeys([*observations["source_sha256"], *predictions["source_sha256"]])),
    }}
