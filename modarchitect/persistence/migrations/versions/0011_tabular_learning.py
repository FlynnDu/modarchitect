# -*- coding: utf-8 -*-
# @Time    : 2026/11/16 20:15
# @Author  : Codex
# @File    : 0011_tabular_learning.py
"""追加标准表回归训练及预测合同，不修改已有科学身份和数据。"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from modarchitect.catalog import tabular_learning_contracts
from modarchitect.contracts.identifiers import identity_sha256, new_uuid7

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """准确身份只能追加，若已有同身份异摘要则原子拒绝。"""
    table = sa.table("model_component_definitions", sa.column("definition_id", sa.Uuid()), sa.column("code", sa.String()), sa.column("revision", sa.Integer()), sa.column("contract_json", sa.JSON()), sa.column("contract_sha256", sa.String()))
    connection = op.get_bind()
    for definition in tabular_learning_contracts():
        digest = identity_sha256(definition)
        connection.execute(insert(table).values(definition_id=new_uuid7(), code=definition["code"], revision=definition["revision"], contract_json=definition, contract_sha256=digest).on_conflict_do_nothing(index_elements=["code", "revision"]))
        actual = connection.execute(sa.select(table.c.contract_sha256).where(table.c.code == definition["code"], table.c.revision == definition["revision"])).scalar_one()
        if actual != digest:
            raise ValueError("Tabular component identity is already occupied")


def downgrade() -> None:
    """合同可能已被历史方案引用，不删除准确科学身份。"""
