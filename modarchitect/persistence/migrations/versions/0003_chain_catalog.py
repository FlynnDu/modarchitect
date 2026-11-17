# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 19:30
# @Author  : Codex
# @File    : 0003_chain_catalog.py
"""登记可组合的历史预测和对齐组件。"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from modarchitect.catalog import chain_contracts
from modarchitect.contracts.identifiers import identity_sha256, new_uuid7

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """追加冻结定义并核对已存在的版本是否相同。"""
    table = sa.table(
        "model_component_definitions",
        sa.column("definition_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("revision", sa.Integer()),
        sa.column("contract_json", sa.JSON()),
        sa.column("contract_sha256", sa.String()),
    )
    connection = op.get_bind()
    for definition in chain_contracts():
        identity = {"code": definition["code"], "revision": definition["revision"]}
        digest = identity_sha256(definition)
        statement = insert(table).values(
            **identity, definition_id=new_uuid7(), contract_json=definition,
            contract_sha256=digest,
        ).on_conflict_do_nothing(index_elements=["code", "revision"])
        connection.execute(statement)
        actual = connection.execute(
            sa.select(table.c.contract_sha256).filter_by(**identity)
        ).scalar_one()
        if actual != digest:
            raise ValueError("Frozen chain component conflicts with the catalog")


def downgrade() -> None:
    """保留可能被已发布方案引用的冻结组件定义。"""
