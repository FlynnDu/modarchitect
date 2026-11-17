# -*- coding: utf-8 -*-
# @Time    : 2026/11/3 23:46
# @Author  : feidu
# @File    : __main__.py
"""标准输入输出的独立组件入口；标准输出只包含完整有限JSON。"""

import json
import sys

from .protocol import calculate, runtime_identity


def main() -> None:
    """描述运行时或处理一个不超过4MB的JSON请求，失败退出码为2。"""
    try:
        if sys.argv[1:] == ["--describe"]:
            result = runtime_identity()
        elif not sys.argv[1:]:
            raw = sys.stdin.buffer.read(4_000_001)
            if len(raw) > 4_000_000:
                raise ValueError("Numeric component request exceeds its byte budget")
            result = calculate(json.loads(raw))
        else:
            raise ValueError("Numeric component command arguments are invalid")
        print(json.dumps(result, allow_nan=False, separators=(",", ":")))
    except (ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
