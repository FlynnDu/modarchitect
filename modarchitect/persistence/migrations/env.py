# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 16:05
# @Author  : Codex
# @File    : env.py
"""使用外部显式连接和研究库元数据运行 Alembic。"""

from alembic import context

from modarchitect.persistence.schema import metadata
from modarchitect.runtime import store as runtime_store
from modarchitect.persistence import source_store
from modarchitect.persistence import dataset_store
from modarchitect.persistence import report_store
from modarchitect.persistence import design_save_store


def migrate() -> None:
    """在传入的 PostgreSQL 连接上运行迁移或元数据比较。"""
    connection = context.config.attributes["connection"]
    assert runtime_store.runs.metadata is metadata
    assert source_store.snapshots.metadata is metadata
    assert dataset_store.datasets.metadata is metadata
    assert report_store.tasks.metadata is metadata
    assert design_save_store.saves.metadata is metadata
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()


migrate()
