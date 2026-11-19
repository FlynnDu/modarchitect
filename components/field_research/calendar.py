# -*- coding: utf-8 -*-
# @Time    : 2026/11/17 21:16
# @Author  : Codex
# @File    : calendar.py
"""按固定日期基准生成精确时间坐标，不添加观测、不推测作物生育起点。"""

from components.chain_tables import business_date, code, read_table


def calendar_axis(inputs: dict, parameters: dict) -> dict[str, dict]:
    """继承实际对象和日期，训练与预测采用同一坐标，拒绝覆盖外部数值。"""
    if set(inputs) != {"observations"} or set(parameters) != {"output_code", "origin_date"}:
        raise ValueError("Calendar axis requires its exact table and parameters")
    if parameters["origin_date"] != "1970-01-01":
        raise ValueError("Calendar coordinate origin differs from its versioned contract")
    origin = business_date(parameters["origin_date"])
    output = code(parameters["output_code"])
    table = inputs["observations"]
    columns, rows = read_table(table, allow_empty_columns=True)
    if output in columns:
        raise ValueError("Calendar axis cannot overwrite an external observation")
    result = [{**row, "values": {**row["values"], output: (key[3] - origin).days}} for key, row in rows.items()]
    # observed仅兼容既有精确日坐标数值端口。编译血缘独立标识date_columns，禁止成为实测标签。
    return {"table": {"columns": [*columns.values(), {"code": output, "name": "观测日期坐标", "unit": "day", "value_kind": "observed"}],
                      "rows": result, "source_sha256": list(table["source_sha256"])}}
