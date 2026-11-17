# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 19:25
# @Author  : Codex
# @File    : chain_tables.py
"""组合组件共用的日期、对象键和数值表检查。"""

from datetime import date
import math
import re

CODE = re.compile(r"[a-z][a-z0-9_]{0,95}")
CHECKSUM = re.compile(r"[0-9a-f]{64}")


def business_date(value: str) -> date:
    """只接受 ISO 业务日期。"""
    day = date.fromisoformat(value)
    if day.isoformat() != value:
        raise ValueError("Invalid business date")
    return day


def code(value: str) -> str:
    """校验可作为数值表列身份的代码。"""
    if not CODE.fullmatch(value):
        raise ValueError("Invalid variable code")
    return value


def number(value: object) -> float:
    """拒绝空值、布尔值及非有限数值。"""
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ValueError("A finite numeric value is required")
    return float(value)


def read_table(
    table: dict, *, forecast: bool = False, allow_empty_columns: bool = False
) -> tuple[dict[str, dict], dict[tuple[str, str, str, date], dict]]:
    """解析列、来源及完整对象日索引，并禁止重复对象日期。"""
    fields = {"columns", "rows", "source_sha256"}
    if forecast:
        fields.add("fit_through")
    if set(table) != fields or not all(
        isinstance(table[name], list) and (table[name] or name == "columns" and allow_empty_columns)
        for name in ("columns", "rows", "source_sha256")
    ):
        raise ValueError("Invalid research table shape")
    sources = table["source_sha256"]
    if any(not CHECKSUM.fullmatch(item) for item in sources) or len(set(sources)) != len(sources):
        raise ValueError("Invalid table source checksums")
    columns = {}
    for column in table["columns"]:
        column_code = code(column["code"])
        if column_code in columns or any(
            not isinstance(column[name], str) or not column[name].strip()
            for name in ("name", "unit", "value_kind")
        ):
            raise ValueError("Invalid or repeated column metadata")
        if forecast and column["value_kind"] != "predicted":
            raise ValueError("Forecast features must be marked predicted")
        columns[column_code] = column
    rows = {}
    cutoff = business_date(table["fit_through"]) if forecast else None
    for row in table["rows"]:
        obj = row["object"]
        day = business_date(row["business_date"])
        key = (obj["field_ref"], obj["crop_code"], obj["season_ref"], day)
        if (
            key in rows
            or any(not isinstance(item, str) or not item.strip() for item in key[:3])
            or set(row["values"]) != columns.keys()
            or (cutoff is not None and day <= cutoff)
        ):
            raise ValueError("Invalid, duplicate or non-historical object date")
        rows[key] = row
    return columns, rows
