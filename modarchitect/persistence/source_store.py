# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 21:52
# @Author  : Codex
# @File    : source_store.py
"""持久化独立采集执行和不可变来源快照，保持主体隔离与准确回执。"""

from collections.abc import Mapping, Sequence
from datetime import timedelta
from secrets import compare_digest, token_urlsafe
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Connection,
    Column,
    DateTime,
    ForeignKey,
    JSON,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    insert,
    select,
    text,
    update,
)

from ..contracts.identifiers import identity_sha256, new_uuid7
from ..contracts.enterprise.identity import VerifiedPrincipal
from ..input_sources.contracts import instant
from ..input_sources.service import validate_acquisition_result
from ..runtime.store import internal_principal
from .design_store import DesignConflict, DesignStore
from .schema import metadata

acquisitions = Table(
    "input_acquisitions",
    metadata,
    Column("acquisition_id", Uuid, primary_key=True),
    Column("design_id", ForeignKey("research_designs.design_id"), nullable=False),
    Column("request_key", String(128), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    Column("input_json", JSON, nullable=False),
    Column("input_sha256", String(64), nullable=False),
    Column("status", String(24), nullable=False),
    Column("attempt_id", Uuid),
    Column("lease_until", DateTime(timezone=True)),
    Column("scheduler_id", String(128)),
    Column("result_sha256", String(64)),
    Column("error", String(1000)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("design_id", "request_key", name="uq_input_acquisition_request"),
    CheckConstraint(
        "status IN ('queued','dispatching','submitted','running','succeeded','failed','uncertain','cancelled')",
        name="ck_input_acquisition_status",
    ),
    CheckConstraint(
        "input_sha256 ~ '^[a-f0-9]{64}$' AND request_sha256 ~ '^[a-f0-9]{64}$'",
        name="ck_input_acquisition_sha",
    ),
)
snapshots = Table(
    "input_source_snapshots",
    metadata,
    Column("snapshot_id", Uuid, primary_key=True),
    Column(
        "acquisition_id",
        ForeignKey("input_acquisitions.acquisition_id"),
        nullable=False,
    ),
    Column("variable_code", String(96), nullable=False),
    Column("snapshot_json", JSON, nullable=False),
    Column("snapshot_sha256", String(64), nullable=False),
    UniqueConstraint(
        "acquisition_id", "variable_code", name="uq_acquisition_source_variable"
    ),
    CheckConstraint("snapshot_sha256 ~ '^[a-f0-9]{64}$'", name="ck_input_snapshot_sha"),
)
dispatch = Table(
    "input_acquisition_dispatch",
    metadata,
    Column(
        "acquisition_id",
        ForeignKey("input_acquisitions.acquisition_id"),
        primary_key=True,
    ),
    Column("owner_json", JSON, nullable=False),
    Column("dispatch_token", String(128), nullable=False),
    Column("status", String(24), nullable=False),
    Column("claimed_at", DateTime(timezone=True)),
)


class SourceStore:
    """网络发生在事务外；写入、领取和回传通过同一身份及数据库锁保护。"""

    def __init__(self, store: DesignStore):
        """复用现有低权限事务入口，不另建数据库连接池。"""
        self.store = store

    def verify_role(self) -> None:
        """启动前检查新资料表的强制行级安全和非所有者执行身份。"""
        with self.store.engine.connect() as connection:
            count = connection.execute(
                text("""
                SELECT count(*) FROM pg_class c WHERE c.relnamespace='public'::regnamespace
                AND c.relname IN ('input_acquisitions','input_source_snapshots')
                AND c.relrowsecurity AND c.relforcerowsecurity AND NOT pg_has_role(c.relowner,'MEMBER')
            """)
            ).scalar_one()
        if count != 2:
            raise RuntimeError("Input source row security is not configured")

    def _view(self, connection: Connection, row: Mapping) -> dict:
        """最小公开状态只含读取采集所需的结果和失败原因。"""
        ids = (
            connection.execute(
                select(snapshots.c.snapshot_id).where(
                    snapshots.c.acquisition_id == row["acquisition_id"]
                )
            )
            .scalars()
            .all()
        )
        return {
            "acquisition_id": str(row["acquisition_id"]),
            "status": row["status"],
            "snapshot_ids": [str(v) for v in ids],
            "error": row["error"],
        }

    def enqueue(
        self,
        owner: VerifiedPrincipal,
        design_id: UUID,
        key: str,
        request_sha: str,
        payload: dict,
        *,
        frozen_version_id: UUID | None = None,
    ) -> dict:
        """锁定同一方案后创建唯一采集和投递记录，重放不重新获取数据。"""
        with self.store.transaction(owner) as tx:
            tx.lock_design(design_id)
            old = (
                tx.connection.execute(
                    select(acquisitions).where(
                        acquisitions.c.design_id == design_id,
                        acquisitions.c.request_key == key,
                    )
                )
                .mappings()
                .first()
            )
            if old:
                if old["request_sha256"] != request_sha:
                    raise DesignConflict(
                        "Acquisition request key refers to different inputs"
                    )
                return self._view(tx.connection, old)
            from .schema import drafts

            if frozen_version_id is not None:
                version = tx.get_version(version_id=frozen_version_id)
                definition = version["contract_json"].get("research_plan")
                if version["design_id"] != design_id or definition is None or identity_sha256(definition) != payload.get("definition_sha256"):
                    raise DesignConflict("Frozen acquisition definition differs")
            else:
                revision = tx.connection.execute(
                    select(drafts.c.revision).where(drafts.c.design_id == design_id)
                ).scalar_one()
                if revision != payload["request"]["expected_revision"]:
                    raise DesignConflict("Research draft revision has changed")
            identity = new_uuid7()
            row = dict(
                acquisition_id=identity,
                design_id=design_id,
                request_key=key,
                request_sha256=request_sha,
                input_json=payload,
                input_sha256=identity_sha256(payload),
                status="queued",
                created_at=instant(),
                updated_at=instant(),
                error=None,
            )
            tx.connection.execute(insert(acquisitions).values(**row))
            tx.connection.execute(
                insert(dispatch).values(
                    acquisition_id=identity,
                    owner_json={
                        "source": owner.company.source,
                        "company_id": owner.company.company_id,
                        "subject": owner.subject,
                    },
                    dispatch_token=token_urlsafe(48),
                    status="queued",
                )
            )
            return self._view(tx.connection, row)

    def read(self, owner: VerifiedPrincipal, identity: UUID) -> dict:
        """按可信主体读取采集状态。"""
        with self.store.transaction(owner) as tx:
            row = (
                tx.connection.execute(
                    select(acquisitions).where(
                        acquisitions.c.acquisition_id == identity
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise LookupError("Input acquisition was not found")
            return self._view(tx.connection, row)

    def replay(
        self, owner: VerifiedPrincipal, design_id: UUID, key: str, request_sha: str
    ) -> dict | None:
        """草稿修改后仍可重放首次采集请求，不用新定义重做网络访问。"""
        with self.store.transaction(owner) as tx:
            row = (
                tx.connection.execute(
                    select(acquisitions).where(
                        acquisitions.c.design_id == design_id,
                        acquisitions.c.request_key == key,
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            if row["request_sha256"] != request_sha:
                raise DesignConflict(
                    "Acquisition request key refers to different inputs"
                )
            return self._view(tx.connection, row)

    def read_snapshot(self, owner: VerifiedPrincipal, identity: UUID) -> dict:
        """受权读回准确证据并重新核对内容摘要。"""
        with self.store.transaction(owner) as tx:
            row = (
                tx.connection.execute(
                    select(snapshots).where(snapshots.c.snapshot_id == identity)
                )
                .mappings()
                .first()
            )
            if row is None:
                raise LookupError("Input source snapshot was not found")
            if identity_sha256(row["snapshot_json"]) != row["snapshot_sha256"]:
                raise DesignConflict("Persisted source snapshot checksum differs")
            return {
                "snapshot_id": str(identity),
                "sha256": row["snapshot_sha256"],
                "snapshot": row["snapshot_json"],
            }

    def resolve(
        self, owner: VerifiedPrincipal, identities: Sequence[UUID]
    ) -> list[dict]:
        """只向统一封存规则传递服务端读取的可信资料。"""
        if len(set(identities)) != len(identities) or len(identities) > 1800:
            raise ValueError("Source snapshot references must be unique and bounded")
        return [self.read_snapshot(owner, identity) for identity in identities]

    def next_dispatch(self) -> dict | None:
        """内部队列只存投递凭据，原始资料始终受 RLS 保护。"""
        self.expire_inactive()
        with self.store.engine.begin() as connection:
            row = (
                connection.execute(
                    select(dispatch)
                    .where(dispatch.c.status == "queued")
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            connection.execute(
                update(dispatch)
                .where(dispatch.c.acquisition_id == row["acquisition_id"])
                .values(status="dispatching", claimed_at=instant())
            )
            return {
                "acquisition_id": str(row["acquisition_id"]),
                "dispatch_token": row["dispatch_token"],
            }

    def _owner(self, identity: UUID, token: str | None = None) -> VerifiedPrincipal:
        """仅内部入口使用队列的封存主体恢复事务，校验单任务凭据。"""
        with self.store.engine.connect() as connection:
            row = (
                connection.execute(
                    select(dispatch).where(dispatch.c.acquisition_id == identity)
                )
                .mappings()
                .first()
            )
        if row is None or (
            token is not None and not compare_digest(row["dispatch_token"], token)
        ):
            raise LookupError("Input acquisition dispatch was not found")
        return internal_principal(row["owner_json"])

    def dispatch_result(
        self, identity: UUID, scheduler_id: str | None, error: str | None
    ) -> None:
        """真实回执不覆盖已完成、已取消或已领取的状态。"""
        with self.store.transaction(self._owner(identity)) as tx:
            row = (
                tx.connection.execute(
                    select(acquisitions)
                    .where(acquisitions.c.acquisition_id == identity)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            values = {"scheduler_id": scheduler_id, "updated_at": instant()}
            if row["status"] in {"queued", "dispatching"}:
                values.update(status="uncertain" if error else "submitted", error=error)
                tx.connection.execute(
                    update(dispatch)
                    .where(dispatch.c.acquisition_id == identity)
                    .values(status=values["status"])
                )
            tx.connection.execute(
                update(acquisitions)
                .where(acquisitions.c.acquisition_id == identity)
                .values(**values)
            )

    def claim(self, identity: UUID, token: str) -> dict:
        """唯一活动尝试领取准确载荷，取消或失败后不能以重投重启。"""
        with self.store.transaction(self._owner(identity, token)) as tx:
            row = (
                tx.connection.execute(
                    select(acquisitions)
                    .where(acquisitions.c.acquisition_id == identity)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if row["status"] in {"succeeded", "failed", "cancelled"}:
                return {"finished": True, "status": row["status"]}
            if row["status"] == "running":
                raise DesignConflict("Input acquisition already has an active attempt")
            if identity_sha256(row["input_json"]) != row["input_sha256"]:
                raise DesignConflict("Sealed acquisition input checksum differs")
            attempt = new_uuid7()
            tx.connection.execute(
                update(acquisitions)
                .where(acquisitions.c.acquisition_id == identity)
                .values(
                    status="running",
                    attempt_id=attempt,
                    lease_until=instant() + timedelta(minutes=5),
                    updated_at=instant(),
                    error=None,
                )
            )
            tx.connection.execute(
                update(dispatch)
                .where(dispatch.c.acquisition_id == identity)
                .values(status="running")
            )
            return {
                "finished": False,
                "attempt_id": str(attempt),
                "input": row["input_json"],
                "input_sha256": row["input_sha256"],
            }

    def heartbeat(self, identity: UUID, attempt: UUID) -> None:
        """取消、过期或其他尝试不能续租。"""
        with self.store.transaction(self._owner(identity)) as tx:
            changed = tx.connection.execute(
                update(acquisitions)
                .where(
                    acquisitions.c.acquisition_id == identity,
                    acquisitions.c.attempt_id == attempt,
                    acquisitions.c.status == "running",
                    acquisitions.c.lease_until >= instant(),
                )
                .values(
                    lease_until=instant() + timedelta(minutes=5), updated_at=instant()
                )
            )
            if changed.rowcount != 1:
                raise DesignConflict("Input acquisition attempt is no longer active")

    def complete(
        self, identity: UUID, attempt: UUID, result: dict | None, error: str | None
    ) -> dict:
        """只接纳当前尝试；完整批次与不可变快照在一个短事务提交。"""
        digest = identity_sha256(result) if result is not None else None
        with self.store.transaction(self._owner(identity)) as tx:
            row = (
                tx.connection.execute(
                    select(acquisitions)
                    .where(acquisitions.c.acquisition_id == identity)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if row["attempt_id"] != attempt:
                raise DesignConflict("Input acquisition attempt is no longer current")
            if (
                row["status"] in {"succeeded", "failed"}
                and row["result_sha256"] == digest
                and row["error"] == error
            ):
                return self._view(tx.connection, row)
            if row["status"] != "running" or row["lease_until"] < instant():
                raise DesignConflict(
                    "Input acquisition attempt has expired or completed"
                )
            if result is not None:
                if set(result) != {"snapshots"}:
                    raise ValueError("Acquisition completion has undeclared outputs")
                for snapshot in validate_acquisition_result(
                    row["input_json"], result["snapshots"]
                ):
                    raw = snapshot.model_dump(mode="json")
                    tx.connection.execute(
                        insert(snapshots).values(
                            snapshot_id=new_uuid7(),
                            acquisition_id=identity,
                            variable_code=snapshot.observations.columns[0].code,
                            snapshot_json=raw,
                            snapshot_sha256=identity_sha256(raw),
                        )
                    )
            status = "succeeded" if result is not None else "failed"
            tx.connection.execute(
                update(acquisitions)
                .where(acquisitions.c.acquisition_id == identity)
                .values(
                    status=status,
                    result_sha256=digest,
                    error=error,
                    updated_at=instant(),
                )
            )
            tx.connection.execute(
                update(dispatch)
                .where(dispatch.c.acquisition_id == identity)
                .values(status=status)
            )
            return self._view(tx.connection, {**row, "status": status, "error": error})

    def cancel(self, owner: VerifiedPrincipal, identity: UUID) -> dict:
        """撤销回传权，网络请求结束后的迟到结果不得发布；不宣称进程已停止。"""
        with self.store.transaction(owner) as tx:
            row = (
                tx.connection.execute(
                    select(acquisitions)
                    .where(acquisitions.c.acquisition_id == identity)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if row is None:
                raise LookupError("Input acquisition was not found")
            if row["status"] not in {"succeeded", "failed", "cancelled"}:
                tx.connection.execute(
                    update(acquisitions)
                    .where(acquisitions.c.acquisition_id == identity)
                    .values(status="cancelled", updated_at=instant())
                )
                tx.connection.execute(
                    update(dispatch)
                    .where(dispatch.c.acquisition_id == identity)
                    .values(status="cancelled")
                )
                row = {**row, "status": "cancelled"}
            return self._view(tx.connection, row)

    def expire_inactive(self) -> None:
        """失联尝试失败，未取得明确调度回执的任务进入待对账。"""
        with self.store.engine.connect() as connection:
            pending = (
                connection.execute(
                    select(dispatch)
                    .where(
                        dispatch.c.status.in_(["dispatching", "submitted", "running"])
                    )
                    .limit(200)
                )
                .mappings()
                .all()
            )
        for job in pending:
            with self.store.transaction(internal_principal(job["owner_json"])) as tx:
                row = (
                    tx.connection.execute(
                        select(acquisitions)
                        .where(acquisitions.c.acquisition_id == job["acquisition_id"])
                        .with_for_update()
                    )
                    .mappings()
                    .one()
                )
                expired = row["status"] == "running" and row["lease_until"] < instant()
                unknown = row["status"] in {
                    "queued",
                    "dispatching",
                    "submitted",
                } and job["claimed_at"] < instant() - timedelta(minutes=10)
                if expired or unknown:
                    status = "failed" if expired else "uncertain"
                    tx.connection.execute(
                        update(acquisitions)
                        .where(acquisitions.c.acquisition_id == row["acquisition_id"])
                        .values(
                            status=status,
                            error="Source worker lease expired"
                            if expired
                            else "Source dispatch requires reconciliation",
                            updated_at=instant(),
                        )
                    )
                    tx.connection.execute(
                        update(dispatch)
                        .where(dispatch.c.acquisition_id == row["acquisition_id"])
                        .values(status=status)
                    )
