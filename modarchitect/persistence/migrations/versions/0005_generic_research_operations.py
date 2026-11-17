# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 12:47
# @Author  : Codex
# @File    : 0005_generic_research_operations.py
"""增量扩展运行操作，追加独立描述统计组件而不改写冻结证据。"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from modarchitect.catalog import analysis_contracts
from modarchitect.contracts.identifiers import identity_sha256, new_uuid7


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """补齐自动生成器不比较的 CHECK 约束，并准确登记新合同。"""
    op.drop_constraint("ck_research_run_kind", "research_runs", type_="check")
    op.create_check_constraint(
        "ck_research_run_kind",
        "research_runs",
        "kind IN ('train','predict','analyze','simulate','calibrate')",
    )
    table = sa.table(
        "model_component_definitions",
        sa.column("definition_id", sa.Uuid()),
        sa.column("code", sa.String()),
        sa.column("revision", sa.Integer()),
        sa.column("contract_json", sa.JSON()),
        sa.column("contract_sha256", sa.String()),
    )
    connection = op.get_bind()
    for definition in analysis_contracts():
        identity = {"code": definition["code"], "revision": definition["revision"]}
        digest = identity_sha256(definition)
        connection.execute(
            insert(table)
            .values(
                **identity,
                definition_id=new_uuid7(),
                contract_json=definition,
                contract_sha256=digest,
            )
            .on_conflict_do_nothing(index_elements=["code", "revision"])
        )
        actual = connection.execute(
            sa.select(table.c.contract_sha256).filter_by(**identity)
        ).scalar_one()
        if actual != digest:
            raise ValueError("Frozen analysis component conflicts with the catalog")


def downgrade() -> None:
    """只有无新操作的封存记录时才允许收紧运行类型，不删除目录证据。"""
    count = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM research_runs WHERE kind NOT IN ('train','predict')"
            )
        )
        .scalar_one()
    )
    if count:
        raise ValueError("Cannot downgrade sealed non-training research operations")
    op.drop_constraint("ck_research_run_kind", "research_runs", type_="check")
    op.create_check_constraint(
        "ck_research_run_kind", "research_runs", "kind IN ('train','predict')"
    )
