# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 16:18
# @Author  : Codex
# @File    : component.py
"""参考组件只检查研究观测表的最低记录数并返回原表。"""


def check_table(table: dict, parameters: dict) -> dict:
    """验证最少记录数和输入形状，保留行、列和来源字段。"""
    minimum = parameters.get("minimum_valid_rows")
    if (
        set(parameters) != {"minimum_valid_rows"}
        or type(minimum) is not int
        or minimum < 1
    ):
        raise ValueError("Minimum valid rows must be a positive integer")
    if set(table) != {"columns", "rows", "source_sha256"}:
        raise ValueError("Observation table fields differ")
    if not all(isinstance(table[key], list) for key in table):
        raise ValueError("Observation table columns, rows and sources must be arrays")
    if len(table["rows"]) < minimum or any(
        not isinstance(row, dict) for row in table["rows"]
    ):
        raise ValueError("Observation table has insufficient valid rows")
    return table
