# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 18:24
# @Author  : Codex
# @File    : entrypoint.py
"""将多变量回归接入可独立复跑的组件文件协议。"""

from components.template.file_protocol import main

from .component import train_predict


if __name__ == "__main__":
    raise SystemExit(main("multivariate_linear_regression", 1, ("observations",), train_predict))
