# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 13:41
# @Author  : Codex
# @File    : dataset_store.py
"""保存不可变研究数据集，复用方案归属与低权限事务。"""

from uuid import UUID
from contextlib import nullcontext

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    JSON,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    select,
)
from sqlalchemy.dialects.postgresql import insert

from ..contracts.enterprise.identity import VerifiedPrincipal
from ..contracts.identifiers import identity_sha256, new_uuid7
from ..runtime.store import now
from .design_store import DesignConflict, DesignStore, DesignTransaction
from .schema import metadata

datasets = Table(
    "research_dataset_snapshots",
    metadata,
    Column("dataset_id", Uuid, primary_key=True),
    Column("design_id", ForeignKey("research_designs.design_id"), nullable=False),
    Column("content_json", JSON, nullable=False),
    Column("content_sha256", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("design_id", "content_sha256", name="uq_research_dataset_content"),
    CheckConstraint(
        "content_sha256 ~ '^[a-f0-9]{64}$'", name="ck_research_dataset_sha"
    ),
)


class DatasetStore:
    """内容寻址去重不扩大读取权限，同一内容的历史快照不能更新。"""

    def __init__(self, store: DesignStore):
        """复用已装配的授权事务和连接池。"""
        self.store = store

    def save(
        self,
        owner: VerifiedPrincipal,
        design_id: UUID,
        content: dict,
        *,
        transaction: DesignTransaction | None = None,
    ) -> dict:
        """锁定受权方案后保存准确内容，相同内容返回原身份。"""
        if transaction is not None:
            self.store.validate_transaction(owner, transaction)
        digest = identity_sha256(content)
        with (
            self.store.transaction(owner)
            if transaction is None
            else nullcontext(transaction)
        ) as tx:
            tx.lock_design(design_id)
            tx.connection.execute(
                insert(datasets)
                .values(
                    dataset_id=new_uuid7(),
                    design_id=design_id,
                    content_json=content,
                    content_sha256=digest,
                    created_at=now(),
                )
                .on_conflict_do_nothing(constraint="uq_research_dataset_content")
            )
            return dict(
                tx.connection.execute(
                    select(datasets).where(
                        datasets.c.design_id == design_id,
                        datasets.c.content_sha256 == digest,
                    )
                )
                .mappings()
                .one()
            )

    def read(self, owner: VerifiedPrincipal, identity: UUID) -> dict:
        """按方案行级安全读取，篡改摘要视为存储冲突。"""
        with self.store.transaction(owner) as tx:
            row = (
                tx.connection.execute(
                    select(datasets).where(datasets.c.dataset_id == identity)
                )
                .mappings()
                .first()
            )
            if row is None:
                raise LookupError("Research dataset was not found")
            if identity_sha256(row["content_json"]) != row["content_sha256"]:
                raise DesignConflict("Research dataset checksum differs")
            return dict(row)
