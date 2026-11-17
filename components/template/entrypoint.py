# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 16:18
# @Author  : Codex
# @File    : entrypoint.py
"""将最低记录数检查组件接入独立文件协议。"""

from component import check_table
from file_protocol import main


def calculate(inputs: dict, parameters: dict) -> dict:
    """按组件端口读入并返回校验后的同一张表。"""
    return {"checked_table": check_table(inputs["table"], parameters)}


if __name__ == "__main__":
    raise SystemExit(main("research_table_quality_check", 1, ("table",), calculate))
