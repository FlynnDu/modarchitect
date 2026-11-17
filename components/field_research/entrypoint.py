# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 14:17
# @Author  : Codex
# @File    : entrypoint.py
"""以镜像固定身份运行新田间研究组件，复用统一文件协议。"""

import os

from components.template.file_protocol import main
from .weather import conditions
from .ndvi import derive_ndvi

OPERATIONS = {
    "catalog_weather_conditions": (("observations",), conditions),
    "sentinel_ndvi_features": (("observations", "soil", "satellite"), derive_ndvi),
}


def run() -> int:
    """组件身份由批准构建确定，不接受客户端导入模块或函数。"""
    code = os.environ["COMPONENT_CODE"]
    ports, calculate = OPERATIONS[code]
    return main(code, 1, ports, calculate)


if __name__ == "__main__":
    raise SystemExit(run())
