# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 21:18
# @Author  : Codex
# @File    : store.py
"""持久化封存运行、执行尝试、调度队列及准确训练模型。"""

from datetime import datetime, timedelta, timezone
from contextlib import nullcontext
from secrets import token_urlsafe
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..contracts.enterprise.identity import CompanyIdentity, VerifiedPrincipal
from ..contracts.identifiers import identity_sha256, new_uuid7
from ..designs import draft_view
from ..persistence.design_store import DesignConflict, DesignStore, DesignTransaction
from ..persistence.schema import metadata

runs = Table(
    "research_runs",
    metadata,
    Column("run_id", Uuid, primary_key=True),
    Column("design_id", ForeignKey("research_designs.design_id"), nullable=False),
    Column("design_version_id", Uuid, nullable=False),
    Column("request_key", String(128), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("input_json", JSON, nullable=False),
    Column("input_sha256", String(64), nullable=False),
    Column("status", String(24), nullable=False),
    Column("attempt_id", Uuid),
    Column("lease_until", DateTime(timezone=True)),
    Column("scheduler_id", String(128)),
    Column("result_json", JSON),
    Column("result_sha256", String(64)),
    Column("error", String(1000)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("design_id", "request_key", name="uq_research_run_request"),
    ForeignKeyConstraint(
        ["design_version_id", "design_id"],
        [
            "research_design_versions.design_version_id",
            "research_design_versions.design_id",
        ],
    ),
    CheckConstraint(
        "kind IN ('train','predict','analyze','simulate','calibrate')",
        name="ck_research_run_kind",
    ),
    CheckConstraint(
        "status IN ('queued','dispatching','submitted','running','succeeded','failed','uncertain')",
        name="ck_research_run_status",
    ),
)
models = Table(
    "research_trained_models",
    metadata,
    Column("model_id", Uuid, primary_key=True),
    Column("run_id", ForeignKey("research_runs.run_id"), nullable=False, unique=True),
    Column("name", String(128), nullable=False),
    Column("model_json", JSON, nullable=False),
    Column("model_sha256", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
queue = Table(
    "research_dispatch_queue",
    metadata,
    Column("run_id", ForeignKey("research_runs.run_id"), primary_key=True),
    Column("owner_json", JSON, nullable=False),
    Column("dispatch_token", String(128), nullable=False),
    Column("status", String(24), nullable=False),
    Column("claimed_at", DateTime(timezone=True)),
)
datasets = Table(
    "research_design_data",
    metadata,
    Column("design_id", ForeignKey("research_designs.design_id"), primary_key=True),
    Column("observations_json", JSON, nullable=False),
    Column("observations_sha256", String(64), nullable=False),
    Column("data_kind", String(24), nullable=False),
    Column("draft_revision", Integer, nullable=False),
    Column("source_snapshot_ids", JSON, nullable=False, server_default="[]"),
)


def now() -> datetime:
    """运行与租约统一使用有时区的 UTC 时钟。"""
    return datetime.now(timezone.utc)


def internal_principal(value: dict) -> VerifiedPrincipal:
    """仅从受信调度队列的封存身份恢复内部访问范围。"""
    instant = now()
    return VerifiedPrincipal(
        CompanyIdentity(value["source"], value["company_id"]),
        value["subject"],
        "modarchitect_internal",
        "frozen_run_owner_v1",
        instant,
        instant + timedelta(minutes=10),
    )


def run_view(row: dict) -> dict:
    """隐藏封存输入，只返回当前主体可读的运行状态及完整结果。"""
    if (
        row["result_json"] is not None
        and identity_sha256(row["result_json"]) != row["result_sha256"]
    ):
        raise DesignConflict("Persisted run result checksum differs")
    return {
        key: row[key]
        for key in (
            "run_id",
            "design_id",
            "design_version_id",
            "kind",
            "status",
            "attempt_id",
            "scheduler_id",
            "input_sha256",
            "result_json",
            "result_sha256",
            "error",
            "created_at",
            "updated_at",
        )
    }


class RuntimeStore:
    """复用方案存储的可信身份事务，内部队列只存调度所需范围。"""

    def __init__(self, store: DesignStore):
        """保存共享事务入口。"""
        self.store = store

    def verify_role(self) -> None:
        """启动前核对新增研究表的强制主体隔离和非所有者运行身份。"""
        from sqlalchemy import text

        with self.store.engine.connect() as connection:
            protected = connection.execute(
                text("""
                SELECT count(*) FROM pg_class c
                WHERE c.relnamespace = 'public'::regnamespace
                  AND c.relname IN ('research_runs','research_trained_models','research_design_data')
                  AND c.relrowsecurity AND c.relforcerowsecurity
                  AND NOT pg_has_role(c.relowner, 'MEMBER')
            """)
            ).scalar_one()
        if protected != 3:
            raise RuntimeError("Research runtime row security is not configured")

    def enqueue(
        self,
        owner: VerifiedPrincipal,
        design_id: UUID,
        version_id: UUID,
        kind: str,
        key: str,
        payload: dict,
        *,
        transaction: DesignTransaction | None = None,
    ) -> dict:
        """锁定方案根后原子建立运行和待调度记录，重复请求核对原摘要。"""
        if transaction is not None:
            self.store.validate_transaction(owner, transaction)
        digest = identity_sha256(payload)
        with (self.store.transaction(owner) if transaction is None else nullcontext(transaction)) as tx:
            tx.lock_design(design_id)
            previous = (
                tx.connection.execute(
                    select(runs).where(
                        runs.c.design_id == design_id,
                        runs.c.request_key == key,
                    )
                )
                .mappings()
                .first()
            )
            if previous is not None:
                if previous["input_sha256"] != digest:
                    raise DesignConflict("Run request key refers to different inputs")
                return run_view(previous)
            identity, instant = new_uuid7(), now()
            row = dict(
                run_id=identity,
                design_id=design_id,
                design_version_id=version_id,
                request_key=key,
                kind=kind,
                input_json=payload,
                input_sha256=digest,
                status="queued",
                created_at=instant,
                updated_at=instant,
            )
            result = (
                tx.connection.execute(insert(runs).values(**row).returning(runs))
                .mappings()
                .one()
            )
            tx.connection.execute(
                insert(queue).values(
                    run_id=identity,
                    status="queued",
                    dispatch_token=token_urlsafe(32),
                    owner_json={
                        "source": owner.company.source,
                        "company_id": owner.company.company_id,
                        "subject": owner.subject,
                    },
                )
            )
            return run_view(result)

    def save_plan(
        self,
        owner: VerifiedPrincipal,
        configuration: dict,
        table: dict | None,
        data_kind: str,
        *,
        key: str | None = None,
        design_id: UUID | None = None,
        revision: int = 1,
        source_snapshot_ids: tuple = (),
    ) -> dict:
        """配置与观测原子保存，任一变化推进共享修订并拒绝旧页面覆盖。"""
        with self.store.transaction(owner) as tx:
            created = False
            if design_id is None:
                row, created = tx.create_draft(key, configuration)
                design_id = row["design_id"]
            tx.lock_design(design_id)
            previous = (
                tx.connection.execute(
                    select(datasets).where(datasets.c.design_id == design_id)
                )
                .mappings()
                .first()
            )
            digest = identity_sha256(table) if table is not None else None
            changed = table is not None and (
                previous is None
                or previous["observations_sha256"] != digest
                or previous["data_kind"] != data_kind
                or previous["source_snapshot_ids"] != [str(v) for v in source_snapshot_ids]
            )
            if key is not None:
                if not created and changed:
                    raise DesignConflict("Research creation observations differ")
            else:
                row = tx.save_draft(
                    design_id, revision, configuration, force_revision=changed
                )
            if table is None:
                return draft_view(row)
            values = {
                "design_id": design_id,
                "draft_revision": row["revision"],
                "observations_json": table,
                "observations_sha256": digest,
                "data_kind": data_kind,
                "source_snapshot_ids": [str(v) for v in source_snapshot_ids],
            }
            statement = pg_insert(datasets).values(**values)
            tx.connection.execute(
                statement.on_conflict_do_update(
                    index_elements=["design_id"],
                    set_={
                        key: value
                        for key, value in values.items()
                        if key != "design_id"
                    },
                )
            )
            return draft_view(row)

    def data(self, owner: VerifiedPrincipal, design_id: UUID) -> dict:
        """重开方案时恢复云端观测，并校验保存的数据摘要。"""
        with self.store.transaction(owner) as tx:
            row = (
                tx.connection.execute(
                    select(datasets).where(datasets.c.design_id == design_id)
                )
                .mappings()
                .first()
            )
            if row is None:
                return {"observations": None, "data_kind": "user_supplied"}
            if identity_sha256(row["observations_json"]) != row["observations_sha256"]:
                raise DesignConflict("Persisted observation checksum differs")
            result = {
                "observations": row["observations_json"],
                "data_kind": row["data_kind"],
            }
            if row["source_snapshot_ids"]:
                result["source_snapshot_ids"] = row["source_snapshot_ids"]
            return result

    def read(self, owner: VerifiedPrincipal, run_id: UUID) -> dict:
        """按行级安全读取一个运行。"""
        with self.store.transaction(owner) as tx:
            row = (
                tx.connection.execute(select(runs).where(runs.c.run_id == run_id))
                .mappings()
                .first()
            )
            if row is None:
                raise LookupError("Research run was not found")
            return run_view(row)

    def run_plan(self, owner: VerifiedPrincipal, run_id: UUID) -> dict:
        """读取准确封存方案，原生资料和 Worker 凭据不进入响应。"""
        with self.store.transaction(owner) as tx:
            row = tx.connection.execute(
                select(runs.c.input_json, runs.c.input_sha256).where(runs.c.run_id == run_id)
            ).mappings().first()
            if row is None:
                raise LookupError("Research run was not found")
            if identity_sha256(row["input_json"]) != row["input_sha256"]:
                raise DesignConflict("Persisted research input checksum differs")
            payload = row["input_json"]
            return payload["plan"] if "plan" in payload else payload["pipeline"]["plan"]

    def replay(
        self, owner: VerifiedPrincipal, design_id: UUID, key: str, request_sha: str
    ) -> dict | None:
        """优先识别原请求，草稿后来修改仍可重放原运行身份。"""
        with self.store.transaction(owner) as tx:
            row = (
                tx.connection.execute(
                    select(runs).where(
                        runs.c.design_id == design_id,
                        runs.c.request_key == key,
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            if row["input_json"].get("request_sha256") != request_sha:
                raise DesignConflict("Run request key refers to different inputs")
            return run_view(row)

    def list_runs(self, owner: VerifiedPrincipal) -> list[dict]:
        """返回当前工作区最近的运行。"""
        with self.store.transaction(owner) as tx:
            return [
                run_view(row)
                for row in tx.connection.execute(
                    select(runs).order_by(runs.c.created_at.desc()).limit(100)
                ).mappings()
            ]

    def save_model(self, owner: VerifiedPrincipal, run_id: UUID, name: str) -> dict:
        """锁定成功训练运行，幂等登记一个不可变模型。"""
        with self.store.transaction(owner) as tx:
            run = (
                tx.connection.execute(
                    select(runs).where(runs.c.run_id == run_id).with_for_update()
                )
                .mappings()
                .first()
            )
            if run is None:
                raise LookupError("Research run was not found")
            previous = (
                tx.connection.execute(select(models).where(models.c.run_id == run_id))
                .mappings()
                .first()
            )
            if previous is not None:
                return dict(previous)
            if run["status"] != "succeeded" or run["kind"] != "train":
                raise DesignConflict(
                    "Only a successful training run can publish a model"
                )
            result = run_view(run)["result_json"]
            model = result["pipeline"]
            return dict(
                tx.connection.execute(
                    insert(models)
                    .values(
                        model_id=new_uuid7(),
                        run_id=run_id,
                        name=name,
                        model_json=model,
                        model_sha256=identity_sha256(model),
                        created_at=now(),
                    )
                    .returning(models)
                )
                .mappings()
                .one()
            )

    def model(self, owner: VerifiedPrincipal, model_id: UUID) -> dict:
        """读回准确模型并核对内容摘要。"""
        with self.store.transaction(owner) as tx:
            row = (
                tx.connection.execute(
                    select(models).where(models.c.model_id == model_id)
                )
                .mappings()
                .first()
            )
            if row is None:
                raise LookupError("Trained model was not found")
            if identity_sha256(row["model_json"]) != row["model_sha256"]:
                raise DesignConflict("Persisted model checksum differs")
            return dict(row)

    def list_models(self, owner: VerifiedPrincipal) -> list[dict]:
        """列出当前主体的模型索引，状态只从准确训练运行取得。"""
        with self.store.transaction(owner) as tx:
            return [
                dict(row)
                for row in tx.connection.execute(
                    select(
                        models.c.model_id,
                        models.c.run_id,
                        models.c.name,
                        models.c.model_sha256,
                        models.c.created_at,
                    )
                    .order_by(models.c.created_at.desc())
                    .limit(100)
                ).mappings()
            ]

    def next_dispatch(self) -> dict | None:
        """内部消费者在短事务内认领一个尚未发送的调度记录。"""
        self.expire_inactive()
        with self.store.engine.begin() as connection:
            row = (
                connection.execute(
                    select(queue)
                    .where(queue.c.status == "queued")
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            connection.execute(
                update(queue)
                .where(queue.c.run_id == row["run_id"])
                .values(status="dispatching", claimed_at=now())
            )
            return {**dict(row), "run_id": str(row["run_id"])}

    def dispatch_result(
        self, run_id: UUID, scheduler_id: str | None, error: str | None
    ) -> None:
        """独立记录调度回执，Worker 先完成时不覆盖科研终态。"""
        with self.store.engine.connect() as connection:
            job = (
                connection.execute(select(queue).where(queue.c.run_id == run_id))
                .mappings()
                .one()
            )
        with self.store.transaction(internal_principal(job["owner_json"])) as tx:
            tx.connection.execute(
                select(runs.c.run_id).where(runs.c.run_id == run_id).with_for_update()
            )
            state = "uncertain" if error else "submitted"
            tx.connection.execute(
                update(queue)
                .where(
                    queue.c.run_id == run_id,
                    queue.c.status.not_in(["running", "succeeded", "failed"]),
                )
                .values(status=state)
            )
            tx.connection.execute(
                update(runs)
                .where(runs.c.run_id == run_id)
                .values(scheduler_id=scheduler_id)
            )
            tx.connection.execute(
                update(runs)
                .where(
                    runs.c.run_id == run_id,
                    runs.c.status.in_(["queued", "dispatching"]),
                )
                .values(status=state, error=error, updated_at=now())
            )

    def claim(self, run_id: UUID, token: str) -> dict:
        """核验单运行凭据后建立唯一执行尝试并返回准确输入。"""
        from secrets import compare_digest

        with self.store.engine.connect() as connection:
            job = (
                connection.execute(select(queue).where(queue.c.run_id == run_id))
                .mappings()
                .first()
            )
        if job is None or not compare_digest(job["dispatch_token"], token):
            raise LookupError("Dispatch identity was not found")
        with self.store.transaction(internal_principal(job["owner_json"])) as tx:
            row = (
                tx.connection.execute(
                    select(runs).where(runs.c.run_id == run_id).with_for_update()
                )
                .mappings()
                .one()
            )
            if row["status"] in {"succeeded", "failed"}:
                return {"finished": True, "status": row["status"]}
            if row["status"] == "running":
                raise DesignConflict("Research run already has an active attempt")
            if identity_sha256(row["input_json"]) != row["input_sha256"]:
                raise DesignConflict("Sealed research input checksum differs")
            attempt = new_uuid7()
            tx.connection.execute(
                update(runs)
                .where(runs.c.run_id == run_id)
                .values(
                    status="running",
                    attempt_id=attempt,
                    lease_until=now() + timedelta(minutes=5),
                    updated_at=now(),
                    error=None,
                )
            )
            tx.connection.execute(
                update(queue).where(queue.c.run_id == run_id).values(status="running")
            )
            return {
                "finished": False,
                "attempt_id": str(attempt),
                "input": row["input_json"],
                "input_sha256": row["input_sha256"],
            }

    def complete(
        self, run_id: UUID, attempt_id: UUID, result: dict | None, error: str | None
    ) -> dict:
        """只接纳当前租约的回传，相同成功回执可重放。"""
        with self.store.engine.connect() as connection:
            job = (
                connection.execute(select(queue).where(queue.c.run_id == run_id))
                .mappings()
                .first()
            )
        if job is None:
            raise LookupError("Research run was not found")
        digest = identity_sha256(result) if result is not None else None
        with self.store.transaction(internal_principal(job["owner_json"])) as tx:
            row = (
                tx.connection.execute(
                    select(runs).where(runs.c.run_id == run_id).with_for_update()
                )
                .mappings()
                .one()
            )
            if row["attempt_id"] != attempt_id:
                raise DesignConflict("Research attempt is no longer current")
            if (
                row["status"] in {"succeeded", "failed"}
                and row["result_sha256"] == digest
                and row["error"] == error
            ):
                return run_view(row)
            if row["status"] != "running" or row["lease_until"] < now():
                raise DesignConflict("Research attempt has expired or completed")
            stored = (
                tx.connection.execute(
                    update(runs)
                    .where(runs.c.run_id == run_id)
                    .values(
                        status="succeeded" if result is not None else "failed",
                        result_json=result,
                        result_sha256=digest,
                        error=error,
                        updated_at=now(),
                    )
                    .returning(runs)
                )
                .mappings()
                .one()
            )
            tx.connection.execute(
                update(queue)
                .where(queue.c.run_id == run_id)
                .values(status=stored["status"])
            )
            return run_view(stored)

    def heartbeat(self, run_id: UUID, attempt_id: UUID) -> None:
        """只有尚未到期的当前尝试可以延长自己的租约。"""
        with self.store.engine.connect() as connection:
            job = (
                connection.execute(select(queue).where(queue.c.run_id == run_id))
                .mappings()
                .one()
            )
        with self.store.transaction(internal_principal(job["owner_json"])) as tx:
            changed = tx.connection.execute(
                update(runs)
                .where(
                    runs.c.run_id == run_id,
                    runs.c.attempt_id == attempt_id,
                    runs.c.status == "running",
                    runs.c.lease_until >= now(),
                )
                .values(lease_until=now() + timedelta(minutes=5), updated_at=now())
            )
            if changed.rowcount != 1:
                raise DesignConflict("Research attempt is no longer active")

    def expire_inactive(self) -> None:
        """失联计算进入明确失败，未知投递留待对账，均不盲目重新启动。"""
        with self.store.engine.connect() as connection:
            jobs = (
                connection.execute(
                    select(queue)
                    .where(
                        queue.c.status.in_(["dispatching", "submitted", "running"]),
                    )
                    .limit(200)
                )
                .mappings()
                .all()
            )
        for job in jobs:
            with self.store.transaction(internal_principal(job["owner_json"])) as tx:
                row = (
                    tx.connection.execute(
                        select(runs)
                        .where(runs.c.run_id == job["run_id"])
                        .with_for_update()
                    )
                    .mappings()
                    .one()
                )
                expired = row["status"] == "running" and row["lease_until"] < now()
                uncertain = row["status"] in {
                    "queued",
                    "dispatching",
                    "submitted",
                } and job["claimed_at"] < now() - timedelta(minutes=10)
                if expired or uncertain:
                    state = "failed" if expired else "uncertain"
                    error = (
                        "Research worker lease expired"
                        if expired
                        else "Scheduler acknowledgement requires reconciliation"
                    )
                    tx.connection.execute(
                        update(runs)
                        .where(runs.c.run_id == row["run_id"])
                        .values(status=state, error=error, updated_at=now())
                    )
                    tx.connection.execute(
                        update(queue)
                        .where(queue.c.run_id == row["run_id"])
                        .values(status=state)
                    )
