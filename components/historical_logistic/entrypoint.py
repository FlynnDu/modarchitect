# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 19:25
# @Author  : Codex
# @File    : entrypoint.py
"""将历史逻辑斯蒂预测接入独立文件协议。"""

from components.template.file_protocol import main

from .component import forecast

if __name__ == "__main__":
    raise SystemExit(main("historical_logistic_forecast", 1, ("observations",), forecast))
