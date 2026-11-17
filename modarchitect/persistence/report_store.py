# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 13:50
# @Author  : Codex
# @File    : report_store.py
"""持久化持续报告及每日唯一批次，内部索引只恢复限定的执行主体。"""

from datetime import date, datetime, timedelta
from contextlib import contextmanager
from secrets import token_hex
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
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

from ..contracts.enterprise.identity import VerifiedPrincipal
from ..contracts.identifiers import identity_sha256, new_uuid7
from ..runtime.store import internal_principal, now
from .design_store import DesignConflict, DesignStore
from .schema import metadata

tasks = Table(
    "research_report_tasks",
    metadata,
    Column("task_id", Uuid, primary_key=True),
    Column("design_id", ForeignKey("research_designs.design_id"), nullable=False),
    Column("design_version_id", Uuid, nullable=False),
    Column("request_key", String(128), nullable=False),
    Column("request_sha256", String(64), nullable=False),
    Column("definition_json", JSON, nullable=False),
    Column("settings_json", JSON, nullable=False),
    Column("observation_start", Date, nullable=False),
    Column("observation_end", Date, nullable=False),
    Column("status", String(24), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("design_id", "request_key", name="uq_report_task_request"),
    ForeignKeyConstraint(
        ["design_version_id", "design_id"],
        [
            "research_design_versions.design_version_id",
            "research_design_versions.design_id",
        ],
    ),
    CheckConstraint(
        "status IN ('active','paused','completed') AND revision >= 1",
        name="ck_report_task_state",
    ),
    CheckConstraint(
        "observation_end >= observation_start", name="ck_report_task_dates"
    ),
    CheckConstraint("request_sha256 ~ '^[a-f0-9]{64}$'", name="ck_report_task_sha"),
)
task_index = Table(
    "research_report_task_index",
    metadata,
    Column("task_id", ForeignKey("research_report_tasks.task_id"), primary_key=True),
    Column("owner_json", JSON, nullable=False),
    Column("active", Integer, nullable=False),
    Column("next_observation_day", Date, nullable=False),
    CheckConstraint("active IN (0,1)", name="ck_report_index_active"),
)
batches = Table(
    "research_report_batches",
    metadata,
    Column("batch_id", Uuid, primary_key=True),
    Column("task_id", ForeignKey("research_report_tasks.task_id"), nullable=False),
    Column("observation_day", Date, nullable=False),
    Column("scheduled_at", DateTime(timezone=True), nullable=False),
    Column("scheduler_id", String(128), nullable=False),
    Column("status", String(24), nullable=False),
    Column("acquisition_ids", JSON, nullable=False),
    Column("dataset_id", ForeignKey("research_dataset_snapshots.dataset_id")),
    Column("run_id", ForeignKey("research_runs.run_id")),
    Column("manual_json", JSON),
    Column("attempts_json", JSON, nullable=False),
    Column("lease_token", String(64)),
    Column("lease_until", DateTime(timezone=True)),
    Column("error", String(1000)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("task_id", "observation_day", name="uq_report_task_day"),
    CheckConstraint(
        "status IN ('waiting_data','collecting','queued','running','succeeded','failed')",
        name="ck_report_batch_status",
    ),
)
work = Table(
    "research_report_work",
    metadata,
    Column(
        "batch_id", ForeignKey("research_report_batches.batch_id"), primary_key=True
    ),
    Column("owner_json", JSON, nullable=False),
    Column("status", String(24), nullable=False),
    Column("next_check_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "status IN ('queued','claimed','paused','done')", name="ck_report_work_status"
    ),
)


def owner_payload(owner: VerifiedPrincipal) -> dict:
    """仅保存服务端已核验的主体引用，不保存会过期的人类委托令牌。"""
    return {
        "source": owner.company.source,
        "company_id": owner.company.company_id,
        "subject": owner.subject,
    }


def task_view(row) -> dict:
    """列表和详情共享最小计划事实，不公开执行主体、原文和调度凭据。"""
    return {
        "name": row["definition_json"]["name"],
        **{
            key: row[key]
            for key in (
                "task_id",
                "design_id",
                "design_version_id",
                "observation_start",
                "observation_end",
                "status",
                "revision",
            )
        },
    }


def batch_view(row) -> dict:
    """按业务日期展示运行归属与缺口，来源证据另经受权资源读取。"""
    return {
        key: row[key]
        for key in (
            "batch_id",
            "observation_day",
            "scheduled_at",
            "status",
            "dataset_id",
            "run_id",
            "error",
            "updated_at",
        )
    }


class ReportStore:
    """任务、批次与进度通过同一低权限连接池保存，外部动作不持有数据库锁。"""

    def __init__(self, store: DesignStore):
        """复用已有资源归属和事务入口。"""
        self.store = store

    def replay(
        self, owner: VerifiedPrincipal, design_id: UUID, key: str, digest: str
    ) -> dict | None:
        """重复启用先核对原请求，不随当前选地或调度状态变化再创建任务。"""
        with self.store.transaction(owner) as tx:
            row = (
                tx.connection.execute(
                    select(tasks).where(
                        tasks.c.design_id == design_id, tasks.c.request_key == key
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            if row["request_sha256"] != digest:
                raise DesignConflict(
                    "Report task request key refers to different inputs"
                )
            return task_view(row)

    def create(
        self,
        owner: VerifiedPrincipal,
        design_id: UUID,
        version_id: UUID,
        key: str,
        digest: str,
        definition: dict,
        settings: dict,
        start: date,
        end: date,
    ) -> dict:
        """锁定受权方案并原子建立任务和内部日分配索引。"""
        with self.store.transaction(owner) as tx:
            tx.lock_design(design_id)
            existing = (
                tx.connection.execute(
                    select(tasks).where(
                        tasks.c.design_id == design_id, tasks.c.request_key == key
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                if existing["request_sha256"] != digest:
                    raise DesignConflict(
                        "Report task request key refers to different inputs"
                    )
                return task_view(existing)
            identity = new_uuid7()
            row = (
                tx.connection.execute(
                    insert(tasks)
                    .values(
                        task_id=identity,
                        design_id=design_id,
                        design_version_id=version_id,
                        request_key=key,
                        request_sha256=digest,
                        definition_json=definition,
                        settings_json=settings,
                        observation_start=start,
                        observation_end=end,
                        status="active",
                        revision=1,
                        created_at=now(),
                        updated_at=now(),
                    )
                    .returning(tasks)
                )
                .mappings()
                .one()
            )
            tx.connection.execute(
                insert(task_index).values(
                    task_id=identity,
                    owner_json=owner_payload(owner),
                    active=1,
                    next_observation_day=start,
                )
            )
            return task_view(row)

    def read(self, owner: VerifiedPrincipal, identity: UUID) -> dict:
        """内部应用流程可读封存定义，公开入口使用最小投影。"""
        with self.store.transaction(owner) as tx:
            row = (
                tx.connection.execute(select(tasks).where(tasks.c.task_id == identity))
                .mappings()
                .first()
            )
            if row is None:
                raise LookupError("Report task was not found")
            return dict(row)

    @contextmanager
    def execution_permission(self, owner: VerifiedPrincipal, identity: UUID):
        """只在本地持久入队期间锁定任务，暂停与新计算建立有确定先后顺序。"""
        with self.store.transaction(owner) as tx:
            row = tx.connection.execute(
                select(tasks.c.status)
                .where(tasks.c.task_id == identity)
                .with_for_update(read=True)
            ).first()
            if row is None or row.status != "active":
                raise DesignConflict("Report task is not active")
            yield

    @contextmanager
    def batch_transaction(
        self, owner: VerifiedPrincipal, identity: UUID, token: str, manual_sha: str
    ):
        """同一事务核验租约和人工修订后，原子封存数据集、运行及批次关联。"""
        with self.store.transaction(owner) as tx:
            task_id = tx.connection.execute(
                select(batches.c.task_id).where(batches.c.batch_id == identity)
            ).scalar_one()
            task = (
                tx.connection.execute(
                    select(tasks)
                    .where(tasks.c.task_id == task_id)
                    .with_for_update(read=True)
                )
                .mappings()
                .one()
            )
            row = (
                tx.connection.execute(
                    select(batches)
                    .where(batches.c.batch_id == identity)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if (
                task["status"] != "active"
                or row["lease_token"] != token
                or row["lease_until"] < now()
            ):
                raise DesignConflict("Report batch execution authority changed")
            if (
                identity_sha256(row["manual_json"]) != manual_sha
                or row["dataset_id"] is not None
                or row["run_id"] is not None
            ):
                raise DesignConflict("Report batch data was already sealed or revised")
            yield tx

    def bind_run(
        self, transaction, identity: UUID, dataset_id: UUID, run_id: UUID
    ) -> None:
        """在批次原子事务内关联输入和运行，崩溃不会留下未关联的已提交计算。"""
        transaction.connection.execute(
            update(batches)
            .where(batches.c.batch_id == identity)
            .values(
                dataset_id=dataset_id,
                run_id=run_id,
                status="queued",
                error=None,
                lease_token=None,
                lease_until=None,
                updated_at=now(),
            )
        )
        transaction.connection.execute(
            update(work)
            .where(work.c.batch_id == identity)
            .values(
                status="queued",
                next_check_at=now() + timedelta(seconds=5),
            )
        )

    def list_tasks(self, owner: VerifiedPrincipal) -> list[dict]:
        """仅列当前主体可见的持续任务。"""
        with self.store.transaction(owner) as tx:
            return [
                task_view(row)
                for row in tx.connection.execute(
                    select(tasks).order_by(tasks.c.created_at.desc()).limit(100)
                ).mappings()
            ]

    def list_batches(
        self, owner: VerifiedPrincipal, identity: UUID, page: int = 1
    ) -> list[dict]:
        """批次按观察日分页，不让无权身份据空列表推断任务存在。"""
        self.read(owner, identity)
        with self.store.transaction(owner) as tx:
            return [
                batch_view(row)
                for row in tx.connection.execute(
                    select(batches)
                    .where(batches.c.task_id == identity)
                    .order_by(batches.c.observation_day.desc())
                    .offset((page - 1) * 100)
                    .limit(100)
                ).mappings()
            ]

    def change_state(
        self, owner: VerifiedPrincipal, identity: UUID, revision: int, active: bool
    ) -> dict:
        """暂停不覆盖历史批次；恢复仍复用同日唯一记录和原封存方案。"""
        with self.store.transaction(owner) as tx:
            row = (
                tx.connection.execute(
                    select(tasks).where(tasks.c.task_id == identity).with_for_update()
                )
                .mappings()
                .first()
            )
            if row is None:
                raise LookupError("Report task was not found")
            if row["revision"] != revision or row["status"] == "completed":
                raise DesignConflict("Report task revision or state differs")
            status = "active" if active else "paused"
            if row["status"] == status:
                return task_view(row)
            next_day = tx.connection.execute(
                select(task_index.c.next_observation_day).where(
                    task_index.c.task_id == identity
                )
            ).scalar_one()
            tx.connection.execute(
                update(task_index)
                .where(task_index.c.task_id == identity)
                .values(active=int(active and next_day <= row["observation_end"]))
            )
            ids = select(batches.c.batch_id).where(
                batches.c.task_id == identity,
                batches.c.status.not_in(["succeeded", "failed"]),
                batches.c.run_id.is_(None),
            )
            tx.connection.execute(
                update(work)
                .where(work.c.batch_id.in_(ids))
                .values(status="queued" if active else "paused", next_check_at=now())
            )
            return task_view(
                tx.connection.execute(
                    update(tasks)
                    .where(tasks.c.task_id == identity)
                    .values(
                        status=status,
                        revision=revision + 1,
                        updated_at=now(),
                    )
                    .returning(tasks)
                )
                .mappings()
                .one()
            )

    def allocate(self, through: date, scheduled_at: datetime, scheduler_id: str) -> int:
        """真实海豚日触发分配到期观测日，数据库唯一键消除重复及恢复重发。"""
        from ..report_tasks.contracts import trigger_time

        with self.store.engine.connect() as connection:
            entries = (
                connection.execute(
                    select(task_index)
                    .where(
                        task_index.c.active == 1,
                        task_index.c.next_observation_day <= through,
                    )
                    .order_by(task_index.c.next_observation_day, task_index.c.task_id)
                    .limit(100)
                )
                .mappings()
                .all()
            )
        created = 0
        for entry in entries:
            owner = internal_principal(entry["owner_json"])
            with self.store.transaction(owner) as tx:
                task = (
                    tx.connection.execute(
                        select(tasks)
                        .where(tasks.c.task_id == entry["task_id"])
                        .with_for_update()
                    )
                    .mappings()
                    .first()
                )
                if task is None or task["status"] != "active":
                    continue
                index = (
                    tx.connection.execute(
                        select(task_index).where(
                            task_index.c.task_id == task["task_id"]
                        )
                    )
                    .mappings()
                    .one()
                )
                day = index["next_observation_day"]
                count = 0
                while day <= min(through, task["observation_end"]) and count < 100:
                    identity = new_uuid7()
                    result = tx.connection.execute(
                        pg_insert(batches)
                        .values(
                            batch_id=identity,
                            task_id=task["task_id"],
                            observation_day=day,
                            scheduled_at=trigger_time(day),
                            scheduler_id=scheduler_id,
                            status="waiting_data",
                            acquisition_ids=[],
                            attempts_json=[
                                {
                                    "daily_instance": scheduler_id,
                                    "logical_trigger": scheduled_at.isoformat(),
                                }
                            ],
                            created_at=now(),
                            updated_at=now(),
                        )
                        .on_conflict_do_nothing(constraint="uq_report_task_day")
                        .returning(batches.c.batch_id)
                    ).scalar_one_or_none()
                    if result is not None:
                        tx.connection.execute(
                            insert(work).values(
                                batch_id=identity,
                                owner_json=entry["owner_json"],
                                status="queued",
                                next_check_at=now(),
                            )
                        )
                        created += 1
                    day += timedelta(days=1)
                    count += 1
                tx.connection.execute(
                    update(task_index)
                    .where(task_index.c.task_id == task["task_id"])
                    .values(
                        next_observation_day=day,
                        active=int(day <= task["observation_end"]),
                    )
                )
        return created

    def has_due(self, through: date) -> bool:
        """日触发按持久进度继续分页，防止前一百项持续占用触发机会。"""
        with self.store.engine.connect() as connection:
            return (
                connection.execute(
                    select(task_index.c.task_id)
                    .where(
                        task_index.c.active == 1,
                        task_index.c.next_observation_day <= through,
                    )
                    .limit(1)
                ).first()
                is not None
            )

    def completed_batches(
        self, owner: VerifiedPrincipal, identity: UUID, start: date, end: date
    ) -> list[dict]:
        """按显式日期范围读取成功批次，不受历史列表分页上限截断。"""
        with self.store.transaction(owner) as tx:
            return [
                dict(row)
                for row in tx.connection.execute(
                    select(batches)
                    .where(
                        batches.c.task_id == identity,
                        batches.c.status == "succeeded",
                        batches.c.observation_day.between(start, end),
                    )
                    .order_by(batches.c.observation_day)
                ).mappings()
            ]

    def next_work(self) -> tuple[VerifiedPrincipal, UUID, str] | None:
        """短事务领取一项进度核验；租约到期可恢复，不把正在取数变成新日期。"""
        with self.store.engine.begin() as connection:
            row = (
                connection.execute(
                    select(work)
                    .where(
                        work.c.status.in_(["queued", "claimed"]),
                        work.c.next_check_at <= now(),
                    )
                    .order_by(work.c.next_check_at)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            connection.execute(
                update(work)
                .where(work.c.batch_id == row["batch_id"])
                .values(status="claimed", next_check_at=now() + timedelta(minutes=3))
            )
        owner = internal_principal(row["owner_json"])
        token = token_hex(24)
        with self.store.transaction(owner) as tx:
            tx.connection.execute(
                update(batches)
                .where(batches.c.batch_id == row["batch_id"])
                .values(lease_token=token, lease_until=now() + timedelta(minutes=3))
            )
        return owner, row["batch_id"], token

    def batch(self, owner: VerifiedPrincipal, identity: UUID) -> dict:
        """只读准确批次，来源和结果由应用流程分别读取。"""
        with self.store.transaction(owner) as tx:
            row = (
                tx.connection.execute(
                    select(batches).where(batches.c.batch_id == identity)
                )
                .mappings()
                .first()
            )
            if row is None:
                raise LookupError("Report batch was not found")
            return dict(row)

    def progress(
        self,
        owner: VerifiedPrincipal,
        identity: UUID,
        token: str,
        changes: dict,
        delay: int = 5,
    ) -> None:
        """核对任务和当前租约后登记进度，终态批次的证据不允许被后到工作覆盖。"""
        with self.store.transaction(owner) as tx:
            task_id = tx.connection.execute(
                select(batches.c.task_id).where(batches.c.batch_id == identity)
            ).scalar_one()
            task = (
                tx.connection.execute(
                    select(tasks).where(tasks.c.task_id == task_id).with_for_update()
                )
                .mappings()
                .one()
            )
            row = (
                tx.connection.execute(
                    select(batches)
                    .where(batches.c.batch_id == identity)
                    .with_for_update()
                )
                .mappings()
                .one()
            )
            if row["lease_token"] != token or row["lease_until"] < now():
                raise DesignConflict("Report batch execution authority changed")
            if row["status"] in {"succeeded", "failed"}:
                return
            allowed = {
                "status",
                "acquisition_ids",
                "dataset_id",
                "run_id",
                "attempts_json",
                "error",
            }
            if set(changes) - allowed:
                raise ValueError("Report progress contains undeclared state")
            tx.connection.execute(
                update(batches)
                .where(batches.c.batch_id == identity)
                .values(**changes, updated_at=now(), lease_token=None, lease_until=None)
            )
            terminal = changes.get("status") in {"succeeded", "failed"}
            state = (
                "done"
                if terminal
                else "paused"
                if task["status"] == "paused"
                and not (changes.get("run_id") or row["run_id"])
                else "queued"
            )
            tx.connection.execute(
                update(work)
                .where(work.c.batch_id == identity)
                .values(status=state, next_check_at=now() + timedelta(seconds=delay))
            )
            if terminal:
                next_day = tx.connection.execute(
                    select(task_index.c.next_observation_day).where(
                        task_index.c.task_id == task_id
                    )
                ).scalar_one()
                remaining = tx.connection.execute(
                    select(batches.c.batch_id)
                    .where(
                        batches.c.task_id == task_id,
                        batches.c.status.not_in(["succeeded", "failed"]),
                    )
                    .limit(1)
                ).first()
                if next_day > task["observation_end"] and remaining is None:
                    tx.connection.execute(
                        update(tasks)
                        .where(tasks.c.task_id == task_id)
                        .values(
                            status="completed",
                            revision=task["revision"] + 1,
                            updated_at=now(),
                        )
                    )

    def provide_manual(
        self, owner: VerifiedPrincipal, identity: UUID, table: dict
    ) -> None:
        """尚未计算的批次允许补齐资料；已封存数据集或终态不能覆盖。"""
        with self.store.transaction(owner) as tx:
            row = (
                tx.connection.execute(
                    select(batches)
                    .where(batches.c.batch_id == identity)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if row is None:
                raise LookupError("Report batch was not found")
            if (
                row["dataset_id"]
                or row["run_id"]
                or row["status"] in {"succeeded", "failed"}
            ):
                raise DesignConflict("Report batch inputs are already sealed")
            if row["lease_until"] is not None and row["lease_until"] > now():
                raise DesignConflict("Report batch input preparation is in progress")
            tx.connection.execute(
                update(batches)
                .where(batches.c.batch_id == identity)
                .values(manual_json=table, updated_at=now())
            )
            tx.connection.execute(
                update(work)
                .where(work.c.batch_id == identity)
                .values(next_check_at=now())
            )
