# -*- coding: utf-8 -*-
# @Time    : 2026/11/18 21:09
# @Author  : Codex
# @File    : 0012_study_version_numbers.py
"""登记各方案已使用的版本号，保留现有配置及修订。"""

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """在同一迁移事务中回填当前版本并启用主体隔离。"""
    op.create_table(
        "research_draft_versions",
        sa.Column("design_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(29), nullable=False),
        sa.Column("configuration_sha256", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["design_id"], ["research_design_drafts.design_id"]),
        sa.PrimaryKeyConstraint("design_id", "revision"),
        sa.UniqueConstraint("design_id", "version", name="uq_research_draft_version"),
        sa.CheckConstraint("revision >= 1", name="ck_research_draft_version_revision"),
        sa.CheckConstraint(
            r"version ~ '^(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})$'",
            name="ck_research_draft_version_format",
        ),
        sa.CheckConstraint("configuration_sha256 ~ '^[a-f0-9]{64}$'", name="ck_research_draft_version_sha256"),
    )
    op.execute("ALTER TABLE public.research_design_drafts NO FORCE ROW LEVEL SECURITY")
    op.execute("""
        INSERT INTO public.research_draft_versions (design_id, revision, version, configuration_sha256)
        SELECT design_id, revision, '1.0.0', configuration_sha256 FROM public.research_design_drafts
    """)
    op.execute("ALTER TABLE public.research_design_drafts FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.research_draft_versions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.research_draft_versions FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY ownership ON public.research_draft_versions USING (
            EXISTS (SELECT 1 FROM public.research_designs
                    WHERE design_id = research_draft_versions.design_id)
        )
    """)
    op.execute("""
        CREATE TRIGGER immutable_research BEFORE UPDATE OR DELETE ON public.research_draft_versions
        FOR EACH ROW EXECUTE FUNCTION public.reject_frozen_research_change()
    """)


def downgrade() -> None:
    """仅空登记表可回退，已分配的版本证据保留。"""
    op.execute("ALTER TABLE public.research_draft_versions NO FORCE ROW LEVEL SECURITY")
    if op.get_bind().execute(sa.text("SELECT EXISTS(SELECT 1 FROM public.research_draft_versions)")).scalar_one():
        raise ValueError("Assigned study versions prevent destructive downgrade")
    op.drop_table("research_draft_versions")
