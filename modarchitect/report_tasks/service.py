# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 13:53
# @Author  : Codex
# @File    : service.py
"""编排持续研究启用、真实日批次和来源到计算的有界推进。"""

from collections.abc import Callable
from datetime import date, timedelta
from uuid import UUID

from shapely.geometry import shape

from ..business import authorized_fields
from ..contracts.enterprise.identity import VerifiedPrincipal
from ..contracts.identifiers import identity_sha256
from ..datasets import SourceCoverageMissing
from ..input_sources.contracts import AcquisitionRequest
from ..input_sources.service import acquisition_windows, prepare_acquisition
from ..persistence.design_store import DesignConflict
from ..persistence.report_store import ReportStore
from ..runtime.contracts import ObservationTable
from ..runtime.preparation import prepare_observations
from ..runtime.preparation import prepare_prediction
from ..runtime.service import ResearchRuntime, execution_profiles, profiles
from ..execution_contracts import external_input_codes
from ..contracts.research.plans import ResearchPlan
from ..runtime.store import now
from ..system_inputs import input_readiness, validate_input_bindings
from .contracts import (
    BusinessReportStart,
    DailyTick,
    ReportObject,
    WorkspaceReportStart,
    SHANGHAI,
    observation_day,
    trigger_time,
)
from .scheduler import require_daily_schedule, require_daily_instance


class ReportTasks:
    """复用准确方案、来源、数据集和执行入口，持续状态不侵入科学算法。"""

    def __init__(
        self,
        runtime: ResearchRuntime,
        store: ReportStore,
        daily_check: Callable | None = None,
    ):
        """注入研究执行及持久化，日计划核对可在隔离验证中替换传输。"""
        self.runtime, self.store = runtime, store
        self.daily_check = daily_check or require_daily_schedule
        self.daily_instance_check = require_daily_instance

    def required_codes(self, task: dict) -> set[str]:
        """自动采集、人工补录与计算准备使用同一操作阶段投影。"""
        definition = task["definition_json"]
        operation = (
            "predict"
            if task["settings_json"]["model_id"]
            else {
                "train": "train",
                "explore": "analyze",
                "simulate": "simulate",
                "fit": "calibrate",
            }[definition["purpose"]]
        )
        return external_input_codes(ResearchPlan.model_validate(definition), operation)

    def input_window(self, task: dict, day) -> tuple:
        """明确批次的数据下界，方法窗口可以包含观察期前的必要背景日。"""
        windows = [
            r["value"].get("window_days")
            for r in task["definition_json"]["input_recipes"].values()
            if r["kind"] == "configuration"
        ]
        window = next(
            (value for value in windows if type(value) is int and value > 0), None
        )
        if window is None and task["settings_json"]["model_id"]:
            window = 1
        if window is None:
            from ..system_inputs import resolve_input

            required = [
                r
                for r in task["definition_json"]["collection_requirements"]
                if r["variable_code"] in self.required_codes(task)
            ]
            if required and all(
                r["source"] == "third_party"
                and resolve_input(r["catalog_binding"], r["method"])["source"][
                    "definition"
                ]["support"]["temporal_support"]
                == "static"
                for r in required
            ):
                window = 1
        return (
            day - timedelta(days=window - 1) if window else task["observation_start"]
        ), day

    def field_evidence(self, fields: tuple) -> dict:
        """准确边界和种植季是持续授权的科学范围，不只比较可变地块名称。"""
        result = {}
        for field in fields:
            unit = field.context.units[0]
            key = identity_sha256(
                {
                    "field_ref": unit.field_ref,
                    "crop_code": unit.crop_code,
                    "season_ref": unit.season_ref,
                }
            )
            result[key] = {
                "boundary_ref": field.boundary_ref,
                "geometry_sha256": identity_sha256(field.geometry),
                "project_ref": field.context.project_ref,
                "season_start": field.context.season_start.isoformat(),
                "season_end": field.context.season_end.isoformat(),
            }
        return result

    def launch(
        self,
        owner: VerifiedPrincipal,
        body: WorkspaceReportStart | BusinessReportStart,
        key: str,
    ) -> dict:
        """受权固定准确版本、范围和对象，缺通道或日计划时不假装已启用。"""
        version = self.runtime.designs.version(owner, version_id=body.design_version_id)
        digest = identity_sha256(body.model_dump(mode="json"))
        replay = self.store.replay(owner, version["design_id"], key, digest)
        if replay is not None:
            return replay
        definition = version["definition"].get("research_plan")
        if definition is None or any(
            r["kind"] == "artifact" for r in definition["input_recipes"].values()
        ):
            raise ValueError(
                "Daily reports require explicit system inputs instead of fixed example bundles"
            )
        validate_input_bindings(definition, require_catalog=True)
        readiness = input_readiness(definition)
        operation = (
            "predict"
            if body.model_id
            else {
                "train": "train",
                "explore": "analyze",
                "simulate": "simulate",
                "fit": "calibrate",
            }[definition["purpose"]]
        )
        needed = external_input_codes(
            ResearchPlan.model_validate(definition), operation
        )
        readiness = [r for r in readiness if r["variable_code"] in needed]
        if not readiness or any(not r["execution"]["available"] for r in readiness):
            raise ValueError("Daily report input channels are incomplete")
        execution_profiles(definition)
        if body.model_id is not None:
            model = self.runtime.store.model(owner, body.model_id)
            trained = self.runtime.store.read(owner, model["run_id"])
            if trained["design_version_id"] != body.design_version_id or model["model_json"]["plan"] != definition:
                raise ValueError("Daily prediction model and exact plan version differ")
            cutoffs = [
                date.fromisoformat(value)
                for value in model["model_json"]["cutoffs"].values()
                if value
            ]
            if cutoffs and body.observation_start <= max(cutoffs):
                raise ValueError(
                    "Daily prediction must follow the model training cutoff"
                )
        if isinstance(body, BusinessReportStart):
            fields = authorized_fields(self.runtime.designs.gateway, owner, body.fields)
            objects = []
            for field in fields:
                unit = field.context.units[0]
                point = shape(field.geometry).representative_point()
                objects.append(
                    ReportObject.model_validate(
                        {
                            "object": {
                                "field_ref": unit.field_ref,
                                "crop_code": unit.crop_code,
                                "season_ref": unit.season_ref,
                            },
                            "reference_point": {
                                "latitude": point.y,
                                "longitude": point.x,
                            },
                        }
                    )
                )
            if any(
                body.observation_start < field.context.season_start
                or body.observation_end > field.context.season_end
                for field in fields
            ):
                raise ValueError(
                    "Report observation period is outside the authorized season"
                )
            selection = body.fields.model_dump(mode="json")
            evidence = self.field_evidence(fields)
        else:
            objects, selection = body.objects, None
            evidence = None
        self.daily_check(body.observation_start, body.observation_end)
        settings = {
            "objects": [item.model_dump(mode="json") for item in objects],
            "business_selection": selection,
            "field_evidence": evidence,
            "model_id": str(body.model_id) if body.model_id else None,
        }
        lower, upper = self.input_window(
            {
                "definition_json": definition,
                "settings_json": settings,
                "observation_start": body.observation_start,
            },
            body.observation_end,
        )
        if ((upper - lower).days + 1) * len(objects) > 5000:
            raise ValueError(
                "Daily report batch exceeds the current 5000 object-date record limit"
            )
        return self.store.create(
            owner,
            version["design_id"],
            body.design_version_id,
            key,
            digest,
            definition,
            settings,
            body.observation_start,
            body.observation_end,
        )

    def tick(self, body: DailyTick) -> dict:
        """只接受明确逻辑时刻；持久唯一批次使重复海豚触发可安全重放。"""
        day = observation_day(body)
        if body.scheduled_at > now() + timedelta(minutes=5):
            raise ValueError("Daily trigger cannot precede its scheduled time")
        self.daily_instance_check(body.scheduler_id, body.scheduled_at)
        result = {
            "created": self.store.allocate(day, body.scheduled_at, body.scheduler_id)
        }
        if self.store.has_due(day):
            result["has_more"] = True
        return result

    def provide(
        self, owner: VerifiedPrincipal, batch_id: UUID, table: ObservationTable
    ) -> None:
        """业务系统可补充标准人工资料，不能改写自动采集列或其他研究对象。"""
        batch = self.store.batch(owner, batch_id)
        task = self.store.read(owner, batch["task_id"])
        needed = self.required_codes(task)
        manual = {
            r["variable_code"]
            for r in task["definition_json"]["collection_requirements"]
            if r["source"] == "manual" and r["variable_code"] in needed
        }
        if {c.code for c in table.columns} != manual:
            raise ValueError(
                "Report observations must contain exactly the declared manual inputs"
            )
        objects = {
            identity_sha256(s["object"]) for s in task["settings_json"]["objects"]
        }
        start, end = self.input_window(task, batch["observation_day"])
        for row in table.model_dump(mode="json")["rows"]:
            if (
                identity_sha256(row["object"]) not in objects
                or not start.isoformat() <= row["business_date"] <= end.isoformat()
            ):
                raise ValueError(
                    "Report observations exceed the authorized objects or cutoff"
                )
        fresh = {
            identity_sha256(row["object"])
            for row in table.model_dump(mode="json")["rows"]
            if row["business_date"] == end.isoformat()
        }
        if fresh != objects:
            raise ValueError(
                "Report observations do not cover the current observation day for every object"
            )
        self.store.provide_manual(owner, batch_id, table.sealed())

    def manual_template(self, owner: VerifiedPrincipal, batch_id: UUID) -> dict:
        """提供当前批次准确人工列与对象的空模板，平台来源不得被人工填写。"""
        batch = self.store.batch(owner, batch_id)
        task = self.store.read(owner, batch["task_id"])
        needed = self.required_codes(task)
        codes = {
            r["variable_code"]
            for r in task["definition_json"]["collection_requirements"]
            if r["source"] == "manual" and r["variable_code"] in needed
        }
        columns = [
            {
                "code": v["code"],
                "name": v["name"],
                "unit": v["unit"],
                "value_kind": "observed",
            }
            for v in task["definition_json"]["variables"]
            if v["code"] in codes
        ]
        if not columns:
            raise ValueError("This report does not require manual observations")
        start, end = self.input_window(task, batch["observation_day"])
        rows = [
            {
                "object": item["object"],
                "business_date": (start + timedelta(days=offset)).isoformat(),
                "values": {column["code"]: None for column in columns},
            }
            for item in task["settings_json"]["objects"]
            for offset in range((end - start).days + 1)
        ]
        return {"columns": columns, "rows": rows}

    def advance_one(self) -> bool:
        """短时推进一个已有批次，外部采集/计算继续由独立真实海豚任务执行。"""
        claimed = self.store.next_work()
        if claimed is None:
            return False
        owner, identity, token = claimed
        batch = self.store.batch(owner, identity)
        task = self.store.read(owner, batch["task_id"])
        if task["status"] != "active" and batch["run_id"] is None:
            self.store.progress(owner, identity, token, {})
            return True
        try:
            result = self._advance(owner, task, batch, token)
            if result is None:
                return True
            changes, delay = result
        except DesignConflict:
            if self.store.read(owner, batch["task_id"])["status"] != "active":
                self.store.progress(owner, identity, token, {})
                return True
            raise
        except (ValueError, LookupError) as error:
            changes, delay = {"status": "failed", "error": str(error)[:1000]}, 5
        self.store.progress(owner, identity, token, changes, delay)
        return True

    def _advance(
        self, owner: VerifiedPrincipal, task: dict, batch: dict, token: str
    ) -> tuple[dict, int] | None:
        """先重核业务范围，再查来源与计算状态，不在锁内等待网络。"""
        definition = task["definition_json"]
        settings = task["settings_json"]
        if settings["business_selection"]:
            from ..contracts.research.field_selection import SelectedResearchFields

            fields = authorized_fields(
                self.runtime.designs.gateway,
                owner,
                SelectedResearchFields.model_validate(settings["business_selection"]),
            )
            current = {
                (
                    f.context.units[0].field_ref,
                    f.context.units[0].crop_code,
                    f.context.units[0].season_ref,
                )
                for f in fields
            }
            expected = {
                (
                    s["object"]["field_ref"],
                    s["object"]["crop_code"],
                    s["object"]["season_ref"],
                )
                for s in settings["objects"]
            }
            if current != expected:
                raise ValueError("Report business authorization or scope changed")
            if self.field_evidence(fields) != settings["field_evidence"]:
                raise ValueError("Report boundary or season evidence changed")
        if batch["run_id"] is not None:
            run = self.runtime.store.read(owner, batch["run_id"])
            state = run["status"]
            if state in {"succeeded", "failed"}:
                return {"status": state, "error": run["error"]}, 5
            return {
                "status": "running" if state == "running" else "queued",
                "error": None,
            }, 5
        needed = self.required_codes(task)
        manual_required = any(
            r["source"] == "manual" and r["variable_code"] in needed
            for r in definition["collection_requirements"]
        )
        if manual_required and batch["manual_json"] is None:
            return {
                "status": "waiting_data",
                "error": "Declared manual observations have not been provided",
            }, 1800
        third_party = any(
            r["source"] == "third_party" and r["variable_code"] in needed
            for r in definition["collection_requirements"]
        )
        ids = batch["acquisition_ids"]
        if third_party and not ids:
            ids = self._collect(owner, task, batch)
            history = batch["attempts_json"] + [
                {"acquisition_ids": ids, "started_at": now().isoformat()}
            ]
            return {
                "status": "collecting",
                "acquisition_ids": ids,
                "attempts_json": history,
                "error": None,
            }, 5
        source_ids = []
        for identity in ids:
            acquired = self.runtime.sources.read(owner, UUID(identity))
            if acquired["status"] == "cancelled":
                return {
                    "status": "failed",
                    "error": "Report source acquisition was explicitly cancelled",
                }, 5
            if acquired["status"] in {"failed", "uncertain"}:
                if now() > max(
                    batch["created_at"], trigger_time(batch["observation_day"])
                ) + timedelta(hours=72):
                    return {
                        "status": "failed",
                        "error": "Report source data remained unavailable beyond its 72-hour recovery window",
                    }, 5
                if acquired["status"] == "uncertain":
                    return {
                        "status": "waiting_data",
                        "error": "Source dispatch requires reconciliation; it will not be blindly resubmitted",
                    }, 1800
                return self._retry_sources(owner, task, batch)
            if acquired["status"] != "succeeded":
                return {"status": "collecting", "error": None}, 5
            source_ids.extend(UUID(v) for v in acquired["snapshot_ids"])
        manual = (
            ObservationTable.model_validate(batch["manual_json"])
            if batch["manual_json"]
            else None
        )
        try:
            content = self.runtime.datasets.prepare(
                owner, definition, tuple(source_ids), manual, "user_supplied",
                study_id=task["task_id"], allow_prior_unbound=True,
            )
        except SourceCoverageMissing:
            return self._retry_sources(owner, task, batch)
        operation = {
            "train": "train",
            "explore": "analyze",
            "simulate": "simulate",
            "fit": "calibrate",
        }[definition["purpose"]]
        if settings["model_id"]:
            model = self.runtime.store.model(owner, UUID(settings["model_id"]))
            prepared = prepare_prediction(
                model,
                ObservationTable.model_validate(content["observations"]),
                content["data_kind"],
                owner.subject,
                profiles(),
                self.runtime.sources.resolve(owner, tuple(source_ids), study_id=task["task_id"], allow_prior_unbound=True),
            )
            operation = "predict"
        else:
            prepared = prepare_observations(
                definition,
                operation,
                ObservationTable.model_validate(content["observations"]),
                content["data_kind"],
                owner.subject,
                execution_profiles,
                source_snapshots=self.runtime.sources.resolve(owner, tuple(source_ids), study_id=task["task_id"], allow_prior_unbound=True),
            )
        payload = {
            **prepared.payload,
            "version_id": str(task["design_version_id"]),
            "report_batch_id": str(batch["batch_id"]),
            "execution_context": {
                "as_of": batch["observation_day"].isoformat(),
                "period_start": task["observation_start"].isoformat(),
            },
        }
        with self.store.batch_transaction(
            owner, batch["batch_id"], token, identity_sha256(batch["manual_json"])
        ) as tx:
            dataset = self.runtime.datasets.store.save(
                owner, task["design_id"], content, transaction=tx, study_id=task["task_id"]
            )
            payload["dataset_snapshot_id"] = str(dataset["dataset_id"])
            run = self.runtime.store.enqueue(
                owner,
                task["design_id"],
                task["design_version_id"],
                operation,
                "report:" + str(batch["batch_id"]),
                payload,
                transaction=tx,
                study_id=task["task_id"],
                dataset_snapshot_id=dataset["dataset_id"],
            )
            self.store.bind_run(
                tx, batch["batch_id"], dataset["dataset_id"], run["run_id"]
            )
        return None

    def _retry_sources(self, owner: VerifiedPrincipal, task: dict, batch: dict) -> tuple[dict, int]:
        """暂缺来源与稀疏日期缺口共用恢复窗口，截止日和原有成功批次保持不变。"""
        if now() > max(batch["created_at"], trigger_time(batch["observation_day"]))+timedelta(hours=72):
            return {"status": "failed", "error": "Report source data remained unavailable beyond its 72-hour recovery window"}, 5
        generation = len(batch["attempts_json"])
        if batch["error"] is not None and generation < 7:
            ids = self._collect(owner, task, batch)
            history = batch["attempts_json"]+[{"acquisition_ids": ids, "started_at": now().isoformat()}]
            return {"status": "collecting", "acquisition_ids": ids, "attempts_json": history, "error": None}, 5
        delays = [1800, 1800, 3600, 21600, 86400, 86400, 86400]
        return {"status": "waiting_data", "error": "Provider data is unavailable; the original observation cutoff is retained"}, delays[min(generation, 6)]

    def _collect(self, owner: VerifiedPrincipal, task: dict, batch: dict) -> list[str]:
        """按每个准确对象采集，科学输入来自固定发布版本而非可变草稿。"""
        definition = task["definition_json"]
        start, end = self.input_window(task, batch["observation_day"])
        needed = self.required_codes(task)
        requirements = tuple(
            r["code"]
            for r in definition["collection_requirements"]
            if r["source"] == "third_party" and r["variable_code"] in needed
        )
        results = []
        requests = [(selected, lower, upper) for selected in task["settings_json"]["objects"]
                    for lower, upper in acquisition_windows(definition, requirements, start, end)]
        if batch["manual_json"] is not None:
            sampled = {(identity_sha256(row["object"]), row["business_date"]) for row in batch["manual_json"]["rows"]}
            requests = [(selected, lower, upper) for selected, lower, upper in requests
                        if any(key == identity_sha256(selected["object"]) and lower.isoformat() <= day <= upper.isoformat()
                               for key, day in sampled)]
        for index, (selected, lower, upper) in enumerate(requests):
            body = AcquisitionRequest.model_validate(
                {
                    **selected,
                    "expected_revision": 1,
                    "start_date": lower,
                    "end_date": upper,
                    "requirements": requirements,
                }
            )
            payload = prepare_acquisition(
                definition, body, retained_definition=definition
            )
            payload["definition_sha256"] = identity_sha256(definition)
            request_sha = identity_sha256(
                {
                    "version": str(task["design_version_id"]),
                    "request": body.model_dump(mode="json"),
                }
            )
            key = "report:%s:%s:%s" % (
                batch["batch_id"],
                len(batch["attempts_json"]),
                index,
            )
            with self.store.execution_permission(owner, task["task_id"]):
                result = self.runtime.sources.enqueue(
                    owner,
                    task["design_id"],
                    key,
                    request_sha,
                    payload,
                    frozen_version_id=task["design_version_id"],
                    study_id=task["task_id"],
                )
            results.append(result["acquisition_id"])
        return results

    def series(
        self,
        owner: VerifiedPrincipal,
        identity: UUID,
        variable: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> dict:
        """每个观察日只取该日封存实值和成果，窗口背景不重复拼入曲线。"""
        task = self.store.read(owner, identity)
        end = end or max(
            task["observation_start"],
            min(
                task["observation_end"],
                now().astimezone(SHANGHAI).date() - timedelta(days=1),
            ),
        )
        start = start or max(task["observation_start"], end - timedelta(days=89))
        if (
            start < task["observation_start"]
            or end > task["observation_end"]
            or not 0 <= (end - start).days < 90
        ):
            raise ValueError(
                "Series range must be inside the observation period and at most 90 days"
            )
        rows, columns = [], {}
        for batch in self.store.completed_batches(owner, identity, start, end):
            run = self.runtime.store.read(owner, batch["run_id"])
            dataset = self.runtime.datasets.store.read(owner, batch["dataset_id"])
            outputs = {
                "input": dataset["content_json"]["observations"],
                **{
                    "result:" + port: value
                    for port, value in run["result_json"].get("outputs", {}).items()
                },
            }
            for port, output in outputs.items():
                if (
                    not isinstance(output, dict)
                    or not isinstance(output.get("columns"), list)
                    or not isinstance(output.get("rows"), list)
                ):
                    continue
                for column in output["columns"]:
                    if variable is None or column["code"] == variable:
                        columns[(port, column["code"])] = {**column, "output": port}
                selected = [
                    c["code"]
                    for c in output["columns"]
                    if variable is None or c["code"] == variable
                ]
                for row in output["rows"]:
                    if (
                        selected
                        and row["business_date"] == batch["observation_day"].isoformat()
                    ):
                        rows.append(
                            {
                                "batch_id": batch["batch_id"],
                                "output": port,
                                "object": row["object"],
                                "business_date": row["business_date"],
                                "values": {
                                    code: row["values"][code] for code in selected
                                },
                            }
                        )
        return {
            "start": start,
            "end": end,
            "columns": list(columns.values()),
            "rows": rows,
        }
