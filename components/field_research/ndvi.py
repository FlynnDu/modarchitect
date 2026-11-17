# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 16:28
# @Author  : Codex
# @File    : ndvi.py
"""显式计算NDVI并按完整对象日期配对，不补齐缺景或改写来源性质。"""

import math

from components.chain_tables import code, number, read_table


def derive_ndvi(inputs: dict, parameters: dict) -> dict[str, dict]:
    """红/近红外比值是计算结果；保留背景实测并拒绝错对象、错日和零分母。"""
    if set(inputs) != {"observations", "soil", "satellite"} or set(parameters) != {"red_code", "nir_code", "output_code"}:
        raise ValueError("NDVI derivation requires exact tables and variable bindings")
    red, nir, output = [code(parameters[key]) for key in ("red_code", "nir_code", "output_code")]
    if len({red,nir,output}) != 3:
        raise ValueError("NDVI inputs and derived output must be distinct")
    context_columns, context_rows = read_table(inputs["observations"], allow_empty_columns=True)
    soil_columns, soil_rows = read_table(inputs["soil"], allow_empty_columns=True)
    bands, satellite_rows = read_table(inputs["satellite"])
    if set(context_columns) & set(soil_columns) or set(bands) != {red,nir} or output in context_columns or output in soil_columns or any(bands[key]["unit"] != "dimensionless" or bands[key]["value_kind"] != "estimated" for key in (red,nir)):
        raise ValueError("NDVI requires declared estimated reflectance columns")
    if context_rows.keys() != satellite_rows.keys() or context_rows.keys() != soil_rows.keys():
        raise ValueError("NDVI tables must pair exactly by full object and acquisition business date")
    rows = []
    for key, row in context_rows.items():
        observation = satellite_rows[key]
        r, n = number(observation["values"][red]), number(observation["values"][nir])
        if r < 0 or n < 0 or abs(n+r) <= 1e-6:
            raise ValueError("NDVI reflectance or denominator is invalid")
        ndvi = (n-r)/(n+r)
        if not math.isfinite(ndvi) or not -1 <= ndvi <= 1:
            raise ValueError("NDVI is outside its physical range")
        rows.append({**row, "values": {**row["values"], **soil_rows[key]["values"], output: ndvi}})
    sources = sorted(set(inputs["observations"]["source_sha256"]+inputs["soil"]["source_sha256"]+inputs["satellite"]["source_sha256"]))
    return {"table": {"columns": [*context_columns.values(), *soil_columns.values(), {"code": output, "name": "NDVI", "unit": "dimensionless", "value_kind": "estimated"}], "rows": rows, "source_sha256": sources}}
