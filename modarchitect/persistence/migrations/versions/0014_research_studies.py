# -*- coding: utf-8 -*-
# @Time    : 2026/11/18 22:20
# @Author  : Codex
# @File    : 0014_research_studies.py
"""持久化固定版本应用和采集、数据集、运行的归属约束。"""

from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """沿用日报任务身份补应用记录，历史运行和快照继续按原证据读取。"""
    op.create_table(
        "research_studies",
        sa.Column("study_id", sa.Uuid(), primary_key=True),
        sa.Column("design_id", sa.Uuid(), nullable=False),
        sa.Column("design_version_id", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.String(128)),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("observation_start", sa.Date(), nullable=False),
        sa.Column("observation_end", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("study_id", "design_id", name="uq_study_design"),
        sa.UniqueConstraint("study_id", "design_id", "design_version_id", name="uq_study_version"),
        sa.UniqueConstraint("design_id", "request_key", name="uq_study_request"),
        sa.ForeignKeyConstraint(["design_version_id", "design_id"],
                               ["research_design_versions.design_version_id", "research_design_versions.design_id"]),
        sa.CheckConstraint("observation_end >= observation_start", name="ck_study_observation_dates"),
    )
    op.execute("ALTER TABLE public.research_report_tasks NO FORCE ROW LEVEL SECURITY")
    op.execute("""
        INSERT INTO public.research_studies (study_id, design_id, design_version_id, context_json,
                                             observation_start, observation_end, created_at)
        SELECT task_id, design_id, design_version_id, settings_json, observation_start, observation_end, created_at
        FROM public.research_report_tasks
    """)
    op.execute("ALTER TABLE public.research_report_tasks FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.research_studies ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.research_studies FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY ownership ON public.research_studies USING (
            design_id IN (SELECT design_id FROM public.research_designs)
        )
    """)
    op.execute("""
        CREATE TRIGGER immutable_research BEFORE UPDATE OR DELETE ON public.research_studies
        FOR EACH ROW EXECUTE FUNCTION public.reject_frozen_research_change()
    """)
    for table in ("research_dataset_snapshots", "input_acquisitions", "research_runs"):
        op.add_column(table, sa.Column("study_id", sa.Uuid()))
    op.add_column("research_runs", sa.Column("dataset_snapshot_id", sa.Uuid()))
    op.create_unique_constraint("uq_dataset_study", "research_dataset_snapshots", ["dataset_id", "study_id"])
    op.create_foreign_key("fk_dataset_study", "research_dataset_snapshots", "research_studies",
                          ["study_id", "design_id"], ["study_id", "design_id"])
    op.create_foreign_key("fk_acquisition_study", "input_acquisitions", "research_studies",
                          ["study_id", "design_id"], ["study_id", "design_id"])
    op.create_foreign_key("fk_run_study_version", "research_runs", "research_studies",
                          ["study_id", "design_id", "design_version_id"], ["study_id", "design_id", "design_version_id"])
    op.create_foreign_key("fk_run_study_dataset", "research_runs", "research_dataset_snapshots",
                          ["dataset_snapshot_id", "study_id"], ["dataset_id", "study_id"])
    op.create_check_constraint("ck_run_study_dataset", "research_runs", "(study_id IS NULL) = (dataset_snapshot_id IS NULL)")
    op.create_foreign_key("fk_report_study", "research_report_tasks", "research_studies",
                          ["task_id", "design_id", "design_version_id"], ["study_id", "design_id", "design_version_id"])
    op.execute("""
        CREATE FUNCTION public.protect_study_lineage() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $$
        BEGIN
            IF NEW.study_id IS DISTINCT FROM OLD.study_id OR
                to_jsonb(NEW)->'dataset_snapshot_id' IS DISTINCT FROM to_jsonb(OLD)->'dataset_snapshot_id'
            THEN RAISE EXCEPTION 'Study lineage cannot be changed'; END IF;
            RETURN NEW;
        END; $$
    """)
    for table in ("input_acquisitions", "research_runs"):
        op.execute("CREATE TRIGGER immutable_study_lineage BEFORE UPDATE ON public.%s "
                   "FOR EACH ROW EXECUTE FUNCTION public.protect_study_lineage()" % table)


def downgrade() -> None:
    """应用记录是科研溯源证据，阻止破坏性回退。"""
    raise ValueError("Study lineage migration is append only")
