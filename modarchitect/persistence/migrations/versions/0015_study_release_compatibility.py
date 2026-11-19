# -*- coding: utf-8 -*-
# @Time    : 2026/11/19 11:20
# @Author  : Codex
# @File    : 0015_study_release_compatibility.py
"""统一缺省版本分配和日报实例登记，兼容滚动发布中的旧 API 写入。"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """在当前授权事务中生成缺省名称，并固定日报实例身份。"""
    op.execute("""
        CREATE FUNCTION public.assign_design_version_name() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $$
        DECLARE
            suffix bigint := NEW.revision::bigint - 1;
        BEGIN
            WHILE EXISTS (
                SELECT 1 FROM public.research_design_versions
                WHERE design_id = NEW.design_id AND version_name = '1.0.' || suffix::text
            ) LOOP
                suffix := suffix + 1;
            END LOOP;
            NEW.version_name := '1.0.' || suffix::text;
            RETURN NEW;
        END; $$
    """)
    op.execute("""
        CREATE TRIGGER assign_version_name BEFORE INSERT ON public.research_design_versions
        FOR EACH ROW WHEN (NEW.version_name IS NULL)
        EXECUTE FUNCTION public.assign_design_version_name()
    """)
    op.execute("""
        CREATE FUNCTION public.bind_report_study() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $$
        BEGIN
            INSERT INTO public.research_studies (study_id, design_id, design_version_id, context_json,
                                                 observation_start, observation_end, created_at)
            VALUES (NEW.task_id, NEW.design_id, NEW.design_version_id, NEW.settings_json,
                    NEW.observation_start, NEW.observation_end, NEW.created_at)
            ON CONFLICT (study_id) DO NOTHING;
            RETURN NEW;
        END; $$
    """)
    op.execute("""
        CREATE TRIGGER bind_report_study BEFORE INSERT ON public.research_report_tasks
        FOR EACH ROW EXECUTE FUNCTION public.bind_report_study()
    """)


def downgrade() -> None:
    """撤销兼容触发器，保留已确认的版本和实例。"""
    op.execute("DROP TRIGGER bind_report_study ON public.research_report_tasks")
    op.execute("DROP FUNCTION public.bind_report_study()")
    op.execute("DROP TRIGGER assign_version_name ON public.research_design_versions")
    op.execute("DROP FUNCTION public.assign_design_version_name()")
