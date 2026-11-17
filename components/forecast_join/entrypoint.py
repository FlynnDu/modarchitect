# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 19:25
# @Author  : Codex
# @File    : entrypoint.py
"""将预测因子合并接入独立文件协议。"""

from components.template.file_protocol import main

from .component import join_forecast

if __name__ == "__main__":
    raise SystemExit(main("research_forecast_feature_join", 1, ("observations", "forecast"), join_forecast))
