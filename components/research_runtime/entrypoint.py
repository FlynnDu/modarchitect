# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 21:13
# @Author  : Codex
# @File    : entrypoint.py
"""按镜像构建时固定的组件身份调用文件协议。"""

import os

from components.template.file_protocol import main
from .growth import forecast, predict as predict_growth
from .linear import predict as predict_linear, train as train_linear

OPERATIONS = {
    "multivariate_linear_training": (("observations",), train_linear),
    "historical_logistic_training": (("observations",), forecast),
    "historical_logistic_predict": (("model", "observations"), predict_growth),
    "multivariate_linear_predict": (("model", "observations"), predict_linear),
}


def run() -> int:
    """读取受信镜像环境中的固定身份，拒绝任意函数导入。"""
    component = os.environ["COMPONENT_CODE"]
    ports, calculate = OPERATIONS[component]
    return main(component, 1, ports, calculate)


if __name__ == "__main__":
    raise SystemExit(run())
