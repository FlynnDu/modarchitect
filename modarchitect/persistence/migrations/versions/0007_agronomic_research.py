# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 17:17
# @Author  : Codex
# @File    : 0007_agronomic_research.py
"""为独立农业研究追加条件分析和指标过程合同，不改变旧方案定义。"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from modarchitect.catalog import agronomic_contracts
from modarchitect.contracts.identifiers import identity_sha256, new_uuid7

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """追加两个新身份，拒绝覆盖已经存在的不同合同。"""
    table = sa.table(
        "model_component_definitions",
        sa.column("definition_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("revision", sa.Integer()),
        sa.column("contract_json", sa.JSON()),
        sa.column("contract_sha256", sa.String()),
    )
    connection = op.get_bind()
    for definition in agronomic_contracts():
        digest = identity_sha256(definition)
        connection.execute(
            insert(table)
            .values(
                definition_id=new_uuid7(),
                code=definition["code"],
                revision=definition["revision"],
                contract_json=definition,
                contract_sha256=digest,
            )
            .on_conflict_do_nothing(index_elements=["code", "revision"])
        )
        actual = connection.execute(
            sa.select(table.c.contract_sha256).where(
                table.c.code == definition["code"],
                table.c.revision == definition["revision"],
            )
        ).scalar_one()
        if actual != digest:
            raise ValueError("Agronomic component identity is already occupied")


def downgrade() -> None:
    """准确合同供历史运行解释，保留已登记定义。"""
