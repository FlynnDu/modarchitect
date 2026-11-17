# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 16:02
# @Author  : Codex
# @File    : 0006_native_study_catalog.py
"""追加原生科学合同，保留历史目录及已封存模型和方案。"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from modarchitect.catalog import native_contracts
from modarchitect.contracts.identifiers import identity_sha256, new_uuid7

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """只登记新身份，遇到同身份异摘要时拒绝覆盖。"""
    table = sa.table("model_component_definitions", sa.column("definition_id", sa.Uuid()), sa.column("code", sa.String()), sa.column("revision", sa.Integer()), sa.column("contract_json", sa.JSON()), sa.column("contract_sha256", sa.String()))
    connection = op.get_bind()
    for definition in native_contracts():
        digest = identity_sha256(definition)
        connection.execute(insert(table).values(definition_id=new_uuid7(), code=definition["code"], revision=definition["revision"], contract_json=definition, contract_sha256=digest).on_conflict_do_nothing(index_elements=["code", "revision"]))
        actual = connection.execute(sa.select(table.c.contract_sha256).where(table.c.code == definition["code"], table.c.revision == definition["revision"])).scalar_one()
        if actual != digest:
            raise ValueError("Native study component identity is already occupied")


def downgrade() -> None:
    """目录供历史方案解释，不删除已冻结定义。"""
