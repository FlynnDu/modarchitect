# -*- coding: utf-8 -*-
# @Time    : 2026/11/16 21:07
# @Author  : Codex
# @File    : violations.py
"""为图连接与目录输入的规则错误保留可定位的公开路径。"""


class ContractViolation(ValueError):
    """不携带原始数据和凭据的合同问题。"""

    def __init__(self, message: str, path: list[str | int], rule: str, *, node: str | None = None, port: str | None = None) -> None:
        """保存前端高亮字段所需的稳定定位。"""
        self.path, self.rule, self.node, self.port = path, rule, node, port
        super().__init__(message)

    def issue(self) -> dict:
        """只输出存在的节点和端口，复用检查与保存的错误结构。"""
        return {"path": self.path, "type": self.rule, "message": str(self),
                **({"node": self.node} if self.node else {}), **({"port": self.port} if self.port else {})}
