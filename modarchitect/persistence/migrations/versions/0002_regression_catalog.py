# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 18:31
# @Author  : Codex
# @File    : 0002_regression_catalog.py
"""向独立研究库登记多变量回归的不可变版本。"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from modarchitect.catalog import regression_contract
from modarchitect.contracts.identifiers import identity_sha256, new_uuid7

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """登记准确版本，并验证先前登记的内容没有冲突。"""
    table = sa.table(
        "model_component_definitions",
        sa.column("definition_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("revision", sa.Integer()),
        sa.column("contract_json", sa.JSON()),
        sa.column("contract_sha256", sa.String()),
    )
    definition = regression_contract()
    digest = identity_sha256(definition)
    connection = op.get_bind()
    identity = {"code": definition["code"], "revision": definition["revision"]}
    connection.execute(
        insert(table).values(
            **identity, definition_id=new_uuid7(), contract_json=definition,
            contract_sha256=digest,
        ).on_conflict_do_nothing(index_elements=["code", "revision"])
    )
    existing = connection.execute(
        sa.select(table.c.contract_sha256).filter_by(**identity)
    ).scalar_one()
    if existing != digest:
        raise ValueError("Frozen regression definition conflicts with the catalog")


def downgrade() -> None:
    """保留可能已被研究方案引用的准确历史定义。"""
