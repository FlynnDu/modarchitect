# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 16:41
# @Author  : Codex
# @File    : input_taxonomy.py
"""单独投影输入的两层查找分类，不改变科学身份、来源或执行资格。"""

from importlib.resources import files
import json


def taxonomy() -> dict:
    """分类制品只保存名称和准确条目归属，不推测中文指标名或供应商品牌。"""
    value = json.loads(files("modarchitect.contracts").joinpath("input-taxonomy-v1.json").read_text(encoding="utf-8"))
    parents = {row["code"] for row in value["categories"]}
    groups = {row["code"]: row for row in value["groups"]}
    if len(parents) != len(value["categories"]) or len(groups) != len(value["groups"]) or any(row["parent"] not in parents for row in groups.values()) or set(value["assignments"].values())-set(groups):
        raise ValueError("Input taxonomy references are invalid")
    return value


def category_names() -> dict[str, str]:
    """一级名称也从相同制品读取，避免API和页面各维护一份。"""
    return {row["code"]: row["name"] for row in taxonomy()["categories"]}


def classified_catalog(catalog: dict) -> dict:
    """每项必须有且只有一个二级归属，缺分类时拒绝发布含糊目录。"""
    value = taxonomy()
    assignments, groups = value["assignments"], {row["code"]: row for row in value["groups"]}
    if {row["key"] for row in catalog["items"]} != set(assignments):
        raise ValueError("Input taxonomy does not cover the adopted catalog exactly")
    for item in catalog["items"]:
        group = assignments[item["key"]]
        if groups[group]["parent"] != item["category"]:
            raise ValueError("Input taxonomy source category differs")
        item["subcategory"] = group
    for category in catalog["categories"]:
        category["children"] = [{"code": group["code"], "name": group["name"],
                                 "count": sum(item["subcategory"] == group["code"] for item in catalog["items"])}
                                for group in value["groups"] if group["parent"] == category["code"]]
    return catalog
