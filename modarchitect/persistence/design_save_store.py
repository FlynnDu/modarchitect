# -*- coding: utf-8 -*-
# @Time    : 2026/11/16 14:38
# @Author  : Codex
# @File    : design_save_store.py
"""持久化不可变保存回执，配置正文继续由方案草稿独占。"""

from uuid import UUID

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Table, Uuid, func, insert, select, text

from ..contracts.identifiers import identity_sha256
from .design_store import DesignConflict, DesignTransaction
from .schema import designs, metadata

saves = Table(
    "research_design_saves", metadata,
    Column("resource_scope_id", ForeignKey("resource_scopes.resource_scope_id"), primary_key=True),
    Column("subject", String(256), primary_key=True),
    Column("request_id", Uuid, primary_key=True),
    Column("request_sha256", String(64), nullable=False),
    Column("design_id", ForeignKey("research_designs.design_id"), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("configuration_sha256", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("revision >= 1", name="ck_design_save_revision"),
    CheckConstraint("request_sha256 ~ '^[a-f0-9]{64}$'", name="ck_design_save_request_sha"),
    CheckConstraint("configuration_sha256 ~ '^[a-f0-9]{64}$'", name="ck_design_save_configuration_sha"),
)


def lock_request(tx: DesignTransaction, request_id: UUID) -> None:
    """同主体同请求串行化，新请求不阻塞其他主体的独立保存。"""
    owner = tx.principal
    identity = identity_sha256({"company": [owner.company.source, owner.company.company_id],
                               "subject": owner.subject, "request": str(request_id)})
    tx.connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 3911004))"),
                          {"identity": identity})


def read_receipt(tx: DesignTransaction, request_id: UUID, digest: str | None = None) -> dict | None:
    """由数据库主体隔离限制读取，重放时进一步比对原请求摘要。"""
    row = tx.connection.execute(select(saves).where(saves.c.request_id == request_id)).mappings().one_or_none()
    if row is None:
        return None
    if digest is not None and row["request_sha256"] != digest:
        raise DesignConflict("Design save request content differs")
    return {k: row[k] for k in ("design_id", "revision", "configuration_sha256")}


def record_receipt(tx: DesignTransaction, request_id: UUID, digest: str, draft) -> dict:
    """同一草稿事务登记结果，禁止业务系统伪报另一主体的关联。"""
    scope = tx.connection.execute(select(designs.c.resource_scope_id).where(
        designs.c.design_id == draft["design_id"])).scalar_one()
    row = tx.connection.execute(insert(saves).values(
        resource_scope_id=scope, subject=tx.principal.subject, request_id=request_id,
        request_sha256=digest, design_id=draft["design_id"], revision=draft["revision"],
        configuration_sha256=draft["configuration_sha256"],
    ).returning(saves)).mappings().one()
    return {k: row[k] for k in ("design_id", "revision", "configuration_sha256")}
