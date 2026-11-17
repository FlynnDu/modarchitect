# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 17:13
# @Author  : Codex
# @File    : entrypoint.py
"""按构建时固定身份提供独立计算入口。"""

import os

from .file_protocol import main
from .series import process
from .weather import conditions

OPERATIONS = {
    "research_weather_conditions": (("weather",), conditions),
    "agronomic_indicator_analysis": (("series",), process),
}


def run() -> int:
    """调用已登记的计算函数，运行请求不能替换组件身份。"""
    code = os.environ["COMPONENT_CODE"]
    ports, calculate = OPERATIONS[code]
    return main(code, 1, ports, calculate)


if __name__ == "__main__":
    raise SystemExit(run())
