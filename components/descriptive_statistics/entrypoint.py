# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 12:46
# @Author  : Codex
# @File    : entrypoint.py
"""将描述统计接入统一的隔离文件调用协议。"""

from components.template.file_protocol import main
from .component import summarize

if __name__ == "__main__":
    raise SystemExit(
        main("research_descriptive_statistics", 1, ("observations",), summarize)
    )
