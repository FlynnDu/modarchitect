# -*- coding: utf-8 -*-
# @Time    : 2026/11/16 20:13
# @Author  : Codex
# @File    : entrypoint.py
"""由构建身份固定算法及训练或预测操作，复用统一文件协议。"""

from functools import partial
import os

from components.template.file_protocol import main
from .component import predict, train


def run() -> int:
    """不接受运行请求指定导入地址或改变镜像内算法身份。"""
    code = os.environ["COMPONENT_CODE"]
    if code in {"multivariate_linear_training", "multivariate_linear_predict"}:
        from components.research_runtime.linear import predict as linear_predict, train as linear_train

        action = code.rsplit("_", 1)[1]
        return main(code, 1, ("observations",) if action == "training" else ("observations", "model"), linear_train if action == "training" else linear_predict)
    algorithm, action = code.rsplit("_", 1)
    if algorithm not in {"random_forest", "xgboost", "gaussian_process"} or action not in {"training", "predict"}:
        raise ValueError("Unknown approved tabular component")
    ports = ("observations",) if action == "training" else ("observations", "model")
    return main(code, 1, ports, partial(train if action == "training" else predict, algorithm=algorithm))


if __name__ == "__main__":
    raise SystemExit(run())
