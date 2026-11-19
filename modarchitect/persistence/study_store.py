# -*- coding: utf-8 -*-
# @Time    : 2026/11/18 22:25
# @Author  : Codex
# @File    : study_store.py
"""在既有行级授权事务中创建和读取不可变研究实例。"""

from datetime import date
from uuid import UUID

from sqlalchemy import insert, select

from ..contracts.enterprise.identity import VerifiedPrincipal
from ..contracts.identifiers import new_uuid7
from .design_store import DesignConflict, DesignStore
from .schema import studies


class StudyStore:
    """研究实例绑定准确版本和作用范围。"""

    def __init__(self, store: DesignStore):
        """复用方案存储和可信主体事务。"""
        self.store = store

    def create(self, owner: VerifiedPrincipal, design_id: UUID, version_id: UUID, key: str,
               context: dict, start: date, end: date) -> dict:
        """同一方案内的幂等键只可用于一个准确应用请求。"""
        with self.store.transaction(owner) as tx:
            tx.lock_design(design_id)
            previous = tx.connection.execute(select(studies).where(
                studies.c.design_id == design_id, studies.c.request_key == key,
            )).mappings().one_or_none()
            if previous is not None:
                if previous["context_json"]["request_sha256"] != context["request_sha256"]:
                    raise DesignConflict("Study request key refers to different inputs")
                return dict(previous)
            return dict(tx.connection.execute(insert(studies).values(
                study_id=new_uuid7(), design_id=design_id, design_version_id=version_id,
                request_key=key, context_json=context, observation_start=start, observation_end=end,
            ).returning(studies)).mappings().one())

    def read(self, owner: VerifiedPrincipal, study_id: UUID) -> dict:
        """只向所属主体返回固定应用上下文。"""
        with self.store.transaction(owner) as tx:
            row = tx.connection.execute(select(studies).where(
                studies.c.study_id == study_id,
            )).mappings().one_or_none()
            if row is None:
                raise LookupError("Research study was not found")
            return dict(row)
