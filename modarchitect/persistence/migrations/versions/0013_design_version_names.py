# -*- coding: utf-8 -*-
# @Time    : 2026/11/18 22:00
# @Author  : Codex
# @File    : 0013_design_version_names.py
"""把方案版本名称绑定到原有冻结版本 UUID。"""

from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为历史版本分配名称，保留 UUID、配置正文和摘要。"""
    op.add_column("research_design_drafts", sa.Column("version_name", sa.String(128)))
    op.add_column("research_design_drafts", sa.Column("initial_version_name", sa.String(128)))
    op.add_column("research_design_versions", sa.Column("version_name", sa.String(128)))
    op.execute("ALTER TABLE public.research_design_versions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.research_design_versions DISABLE TRIGGER immutable_research")
    op.execute("UPDATE public.research_design_versions SET version_name = '1.0.' || (revision - 1)::text")
    op.execute("ALTER TABLE public.research_design_versions ENABLE TRIGGER immutable_research")
    op.execute("ALTER TABLE public.research_design_versions FORCE ROW LEVEL SECURITY")
    op.alter_column("research_design_versions", "version_name", nullable=False)
    op.create_unique_constraint("uq_design_version_name", "research_design_versions", ["design_id", "version_name"])
    op.create_check_constraint("ck_design_version_name", "research_design_versions", "btrim(version_name) <> ''")


def downgrade() -> None:
    """防止已分配的可应用版本名称被静默删除。"""
    op.execute("ALTER TABLE public.research_design_versions NO FORCE ROW LEVEL SECURITY")
    if op.get_bind().execute(sa.text("SELECT EXISTS(SELECT 1 FROM public.research_design_versions)")).scalar_one():
        raise ValueError("Assigned design version names prevent destructive downgrade")
    op.execute("ALTER TABLE public.research_design_versions FORCE ROW LEVEL SECURITY")
    op.drop_constraint("ck_design_version_name", "research_design_versions", type_="check")
    op.drop_constraint("uq_design_version_name", "research_design_versions", type_="unique")
    op.drop_column("research_design_versions", "version_name")
    op.drop_column("research_design_drafts", "initial_version_name")
    op.drop_column("research_design_drafts", "version_name")
