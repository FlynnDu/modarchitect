# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 16:08
# @Author  : Codex
# @File    : design_store.py
"""隔离 PostgreSQL 事务、草稿并发控制和不可变版本写入。"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import (
    Connection,
    Engine,
    RowMapping,
    func,
    insert,
    select,
    text,
    tuple_,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..contracts.enterprise.identity import EnterpriseAccessError, VerifiedPrincipal
from ..contracts.identifiers import identity_sha256, new_uuid7
from ..contracts.model_center.components import DesignPublication
from .schema import bindings, components, designs, drafts, scopes, versions


class DesignConflict(ValueError):
    """请求身份、草稿修订或方案版本与已有状态冲突。"""


class StudyVersionConflict(DesignConflict):
    """本方案曾使用过该版本号。"""


class DesignStore:
    """负责连接生命周期，按可信主体建立短事务。"""

    def __init__(self, engine: Engine):
        """仅支持有强制行级安全的 PostgreSQL 适配。"""
        if engine.dialect.name != "postgresql":
            raise ValueError("The research database requires PostgreSQL")
        self.engine = engine

    def verify_runtime_role(self) -> None:
        """启动时拒绝数据库高权限连接和未启用强制行级安全的表。"""
        with self.engine.connect() as connection:
            unsafe = connection.execute(
                text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_roles WHERE (rolsuper OR rolbypassrls)
                    AND pg_has_role(oid, 'MEMBER')
                )
            """)
            ).scalar_one()
            protected = connection.execute(
                text("""
                SELECT count(*) FROM pg_class c
                WHERE c.relnamespace = 'public'::regnamespace
                  AND c.relname IN ('resource_scopes','research_designs','research_design_drafts',
                                    'research_design_versions','research_design_components',
                                    'research_dataset_snapshots','research_report_tasks',
                                    'research_report_batches','research_design_saves',
                                    'research_draft_versions','research_studies')
                  AND c.relrowsecurity AND c.relforcerowsecurity
                  AND NOT pg_has_role(c.relowner, 'MEMBER')
            """)
            ).scalar_one()
            if unsafe or protected != 11:
                raise RuntimeError(
                    "The research runtime role or row security configuration is unsafe"
                )

    def validate_transaction(
        self, principal: VerifiedPrincipal, transaction: "DesignTransaction"
    ) -> None:
        """共享事务必须属于同一存储和主体，避免行级身份与投递归属分离。"""
        if (
            transaction.connection.engine is not self.engine
            or transaction.principal.company != principal.company
            or transaction.principal.subject != principal.subject
        ):
            raise EnterpriseAccessError("Shared transaction identity differs")

    @contextmanager
    def transaction(
        self, principal: VerifiedPrincipal
    ) -> Iterator["DesignTransaction"]:
        """在同一事务绑定主体，提交后才离开调用。"""
        principal.validate(audience=principal.audience, now=datetime.now(timezone.utc))
        with self.engine.begin() as connection:
            connection.execute(
                text("""
                SELECT set_config('modarchitect.company_source', :source, true),
                       set_config('modarchitect.company_id', :company, true),
                       set_config('modarchitect.subject', :subject, true)
            """),
                {
                    "source": principal.company.source,
                    "company": str(principal.company.company_id),
                    "subject": principal.subject,
                },
            )
            yield DesignTransaction(connection, principal)


class DesignTransaction:
    """提供同一授权事务内的方案读写。"""

    def __init__(self, connection: Connection, principal: VerifiedPrincipal):
        """复用上游已经绑定行级安全的连接。"""
        self.connection = connection
        self.principal = principal

    def _scope_id(self) -> UUID:
        """按企业来源编号幂等建立本地范围，历史范围映射可复用。"""
        source = self.principal.company.source
        company = self.principal.company.company_id
        self.connection.execute(
            pg_insert(scopes)
            .values(
                resource_scope_id=new_uuid7(), company_source=source, company_id=company
            )
            .on_conflict_do_nothing(constraint="uq_scope_company")
        )
        return self.connection.execute(
            select(scopes.c.resource_scope_id).where(
                scopes.c.company_source == source, scopes.c.company_id == company
            )
        ).scalar_one()

    def create_design(self, key: str) -> tuple[UUID, bool]:
        """以企业、主体和创建幂等键取得方案根。"""
        scope_id = self._scope_id()
        owner = self.principal.subject
        design_id = self.connection.execute(
            pg_insert(designs)
            .values(
                design_id=new_uuid7(),
                resource_scope_id=scope_id,
                subject=owner,
                idempotency_key=key,
            )
            .on_conflict_do_nothing(constraint="uq_design_request")
            .returning(designs.c.design_id)
        ).scalar_one_or_none()
        if design_id is not None:
            return design_id, True
        existing_id = self.connection.execute(
            select(designs.c.design_id).where(
                designs.c.resource_scope_id == scope_id,
                designs.c.subject == owner,
                designs.c.idempotency_key == key,
            )
        ).scalar_one()
        return existing_id, False

    def create_draft(self, key: str, configuration: dict, *, version_name: str | None = None) -> tuple[RowMapping, bool]:
        """以首次配置和候选名称验证创建重放。"""
        design_id, created = self.create_design(key)
        digest = identity_sha256(configuration)
        if not created:
            row = self.get_draft(design_id)
            if row["initial_sha256"] != digest or row["initial_version_name"] != version_name:
                raise DesignConflict("Research draft creation content differs")
            return row, False
        row = self.connection.execute(
            insert(drafts).values(
                design_id=design_id, revision=1, configuration_json=configuration,
                configuration_sha256=digest, initial_sha256=digest,
                version_name=version_name, initial_version_name=version_name,
            ).returning(drafts)
        ).mappings().one()
        return row, True

    def version_names(self, design_id: UUID) -> set[str]:
        """读取同一方案已确认的名称集合，用于预查和默认分配。"""
        return set(self.connection.execute(select(versions.c.version_name).where(
            versions.c.design_id == design_id,
        )).scalars())

    def find_creation(self, key: str) -> RowMapping | None:
        """仅在当前主体隔离范围内查找首次创建身份，不用客户端声明历史采用资格。"""
        return self.connection.execute(
            select(drafts).join(designs, designs.c.design_id == drafts.c.design_id)
            .where(designs.c.idempotency_key == key)
        ).mappings().first()

    def find_published_creation(self, key: str) -> RowMapping | None:
        """受主体隔离读取旧直接发布入口的首次准确载荷。"""
        return self.connection.execute(
            select(versions).join(designs, designs.c.design_id == versions.c.design_id)
            .where(designs.c.idempotency_key == key, versions.c.revision == 1)
        ).mappings().first()

    def list_drafts(self) -> list[RowMapping]:
        """读取当前主体最近使用的最多一百份草稿。"""
        query = (
            select(drafts)
            .order_by(drafts.c.updated_at.desc(), drafts.c.design_id)
            .limit(100)
        )
        return list(self.connection.execute(query).mappings())

    def get_draft(self, design_id: UUID, *, lock: bool = False) -> RowMapping:
        """读取当前主体的草稿，写入时锁住同一草稿。"""
        query = select(drafts).where(drafts.c.design_id == design_id)
        if lock:
            query = query.with_for_update(of=drafts)
        row = self.connection.execute(query).mappings().one_or_none()
        if row is None:
            raise LookupError("Research draft was not found")
        return row

    def save_draft(
        self,
        design_id: UUID,
        revision: int,
        configuration: dict,
        *,
        force_revision: bool = False,
        version_name: str | None = None,
        replace_candidate: bool = False,
    ) -> RowMapping:
        """核对修订并保存，重复保存原内容保留当前修订。"""
        row = self.get_draft(design_id, lock=True)
        if row["revision"] != revision:
            raise DesignConflict("Research draft revision has changed")
        digest = identity_sha256(configuration)
        unchanged = row["configuration_sha256"] == digest
        if unchanged and not force_revision and (not replace_candidate or version_name == row["version_name"]):
            return row
        published_names = self.version_names(design_id)
        if version_name in published_names:
            raise StudyVersionConflict("This study version name has already been used")
        candidate = row["version_name"]
        if candidate in published_names:
            candidate = None
        return self.connection.execute(
            update(drafts).where(drafts.c.design_id == design_id).values(
                configuration_json=configuration, configuration_sha256=digest,
                revision=revision + 1, updated_at=func.now(),
                version_name=version_name if replace_candidate else candidate,
            ).returning(drafts)
        ).mappings().one()

    def latest_version(self, design_id: UUID) -> RowMapping | None:
        """读取准确方案身份的最新版本。"""
        return (
            self.connection.execute(
                select(versions)
                .where(versions.c.design_id == design_id)
                .order_by(versions.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )

    def lock_design(self, design_id: UUID) -> None:
        """串行化草稿发布和旧版直接发布，避免授权其他主体的锁。"""
        if (
            self.connection.execute(
                select(designs.c.design_id).where(designs.c.design_id == design_id)
            ).scalar_one_or_none()
            is None
        ):
            raise LookupError("Research design was not found")
        self.connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:identity, 3911003))"),
            {"identity": str(design_id)},
        )

    def get_version(
        self,
        *,
        version_id: UUID | None = None,
        design_id: UUID | None = None,
        revision: int | None = None,
    ) -> RowMapping:
        """按版本 UUID 或方案及修订读取当前主体可见的冻结版本。"""
        if version_id is not None:
            query = select(versions).where(versions.c.design_version_id == version_id)
        else:
            query = select(versions).where(versions.c.design_id == design_id)
            if revision is not None:
                query = query.where(versions.c.revision == revision)
            query = query.order_by(versions.c.revision.desc()).limit(1)
        row = self.connection.execute(query).mappings().one_or_none()
        if row is None:
            raise LookupError("Research design version was not found")
        return row

    def list_versions(self, design_id: UUID) -> list[RowMapping]:
        """按倒序读取方案历史。"""
        if not self.connection.execute(
            select(designs.c.design_id).where(designs.c.design_id == design_id)
        ).scalar_one_or_none():
            raise LookupError("Research design was not found")
        query = (
            select(versions)
            .where(versions.c.design_id == design_id)
            .order_by(versions.c.revision.desc())
        )
        return list(self.connection.execute(query).mappings())

    def list_published(self, page: int, page_size: int) -> tuple[list[RowMapping], int]:
        """分页读取当前主体已有的发布方案，每个方案只取最新版。"""
        latest = (
            select(
                versions.c.design_id, func.max(versions.c.revision).label("revision")
            )
            .group_by(versions.c.design_id)
            .subquery()
        )
        total = self.connection.execute(
            select(func.count()).select_from(latest)
        ).scalar_one()
        query = (
            select(versions)
            .join(
                latest,
                (versions.c.design_id == latest.c.design_id)
                & (versions.c.revision == latest.c.revision),
            )
            .join(designs, designs.c.design_id == versions.c.design_id)
            .order_by(designs.c.created_at.desc(), designs.c.design_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(self.connection.execute(query).mappings()), total

    def append_version(
        self,
        design_id: UUID,
        publication: DesignPublication,
        contract_digests: dict[tuple[str, int], str],
        *,
        version_name: str | None = None,
    ) -> RowMapping:
        """同一事务写入冻结定义及节点绑定，调用方已锁住草稿。"""
        definition = publication.publication_payload()
        row = (
            self.connection.execute(
                pg_insert(versions)
                .values(
                    design_version_id=new_uuid7(),
                    design_id=design_id,
                    revision=publication.revision,
                    contract_json=definition,
                    contract_sha256=identity_sha256(definition),
                    version_name=version_name,
                )
                .on_conflict_do_nothing(constraint="uq_design_version_name")
                .returning(versions)
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise StudyVersionConflict("This study version name has already been used")
        keys = {
            (node.component.code, node.component.revision)
            for node in publication.composition.nodes
        }
        query = select(components).where(
            tuple_(components.c.code, components.c.revision).in_(keys)
        )
        registered = {
            (item["code"], item["revision"]): item
            for item in self.connection.execute(query).mappings()
        }
        for key in keys:
            catalog_row = registered.get(key)
            if (
                catalog_row is None
                or catalog_row["contract_sha256"] != contract_digests[key]
                or identity_sha256(catalog_row["contract_json"])
                != contract_digests[key]
            ):
                raise DesignConflict(
                    "Persisted component contract differs from the installed catalog"
                )
        nodes = [
            {
                "design_version_id": row["design_version_id"],
                "node_code": node.code,
                "definition_id": registered[
                    node.component.code, node.component.revision
                ]["definition_id"],
            }
            for node in publication.composition.nodes
        ]
        self.connection.execute(insert(bindings), nodes)
        return row

    def version_bindings(self, version_id: UUID) -> dict[str, tuple[str, int, str]]:
        """读取冻结节点绑定并验证各组件定义的摘要。"""
        query = select(
            bindings.c.node_code,
            components.c.code,
            components.c.revision,
            components.c.contract_json,
            components.c.contract_sha256,
        ).join_from(bindings, components)
        records = self.connection.execute(
            query.where(bindings.c.design_version_id == version_id)
        )
        result = {}
        for node, code, revision, definition, digest in records:
            if identity_sha256(definition) != digest:
                raise DesignConflict("Persisted component contract checksum differs")
            result[node] = (code, revision, digest)
        return result
