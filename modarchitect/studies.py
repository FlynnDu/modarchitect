# -*- coding: utf-8 -*-
# @Time    : 2026/11/18 22:25
# @Author  : Codex
# @File    : studies.py
"""每次应用、取数、封存和训练沿同一研究实例执行。"""

from collections import Counter
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator
from shapely.geometry import shape

from .business import authorized_fields
from .contracts.enterprise.identity import VerifiedPrincipal
from .contracts.identifiers import identity_sha256
from .contracts.model_center.components import Contract, Text
from .contracts.research.field_selection import SelectedResearchFields
from .input_sources.contracts import AcquisitionRequest, AcquisitionWindow
from .input_sources.service import prepare_acquisition
from .persistence.design_store import DesignConflict
from .persistence.study_store import StudyStore
from .report_tasks.contracts import ReportObject, StudyPeriod
from .runtime.contracts import ObservationTable
from .runtime.preparation import prepare_observations
from .runtime.service import ResearchRuntime, execution_profiles


class WorkspaceStudyStart(StudyPeriod):
    """个人工作区只能声明自有地块和参考位置。"""

    objects: Annotated[tuple[ReportObject, ...], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def unique_objects(self):
        """同一地块、作物和种植季只接受一个参考点。"""
        if len({identity_sha256(item.object.model_dump(mode="json")) for item in self.objects}) != len(self.objects):
            raise ValueError("Study objects must be unique")
        return self


class BusinessStudyStart(StudyPeriod):
    """业务对象和采集点由可信业务服务核验。"""

    fields: SelectedResearchFields
    point_refs: Annotated[tuple[Text, ...], Field(max_length=1000)] = ()


class StudyExecution(Contract):
    """应用运行基于一个确定数据集。"""

    dataset_snapshot_id: UUID
    operation: Literal["train", "analyze", "simulate", "calibrate"]


def study_view(row: dict) -> dict:
    """返回衔接采集和运行所需身份、范围与授权点位编号。"""
    context = row["context_json"]
    return {
        **{key: row[key] for key in ("study_id", "design_version_id", "observation_start", "observation_end")},
        "objects": [entry["object"] for entry in context["objects"]],
        "sampling_points": context.get("sampling_points", []),
    }


class ResearchStudies:
    """统一加载固定版本、锁定对象范围并复用取数与运行准备规则。"""

    def __init__(self, runtime: ResearchRuntime):
        """复用研究环境中的授权、执行和数据服务。"""
        self.runtime = runtime
        self.store = StudyStore(runtime.designs.store)

    def _business_scope(self, owner: VerifiedPrincipal, selection: SelectedResearchFields,
                        points: tuple[str, ...], start: date, end: date) -> tuple[list[dict], list[dict], str]:
        """校验种植季和点位归属，并从受权地块计算唯一参考点。"""
        fields = authorized_fields(self.runtime.designs.gateway, owner, selection)
        if any(start < field.context.season_start or end > field.context.season_end for field in fields):
            raise ValueError("Study observation period is outside the authorized season")
        allowed = Counter(unit.unit_ref for field in fields for unit in field.context.units if unit.kind == "point")
        selected = set(points)
        if len(selected) != len(points) or any(allowed[point] != 1 for point in points):
            raise ValueError("Study includes an unauthorized, ambiguous or repeated sampling point")
        objects = []
        bound_points = {}
        for field in fields:
            unit = field.context.units[0]
            object_ref = {"field_ref": unit.field_ref, "crop_code": unit.crop_code, "season_ref": unit.season_ref}
            point = shape(field.geometry).representative_point()
            objects.append({
                "object": object_ref,
                "reference_point": {"latitude": point.y, "longitude": point.x},
            })
            for unit in field.context.units[1:]:
                if unit.unit_ref in selected:
                    bound_points[unit.unit_ref] = {"point_ref": unit.unit_ref, "object": object_ref}
        return objects, [bound_points[point] for point in points], identity_sha256([field.model_dump(mode="json") for field in fields])

    def create(self, owner: VerifiedPrincipal, body: WorkspaceStudyStart | BusinessStudyStart, key: str) -> dict:
        """将受权业务对象与指定方案版本一次固定。"""
        version = self.runtime.designs.version(owner, version_id=body.design_version_id)
        definition = version["definition"].get("research_plan")
        if definition is None:
            raise ValueError("Study requires a frozen research plan")
        needs_points = any(item["unit_kind"] == "point" for item in definition["collection_requirements"])
        if needs_points and (
            not isinstance(body, BusinessStudyStart) or not body.point_refs
        ):
            raise ValueError("This plan requires an applied business scope with authorized sampling points")
        context = {"request_sha256": identity_sha256(body.model_dump(mode="json"))}
        if isinstance(body, BusinessStudyStart):
            objects, sampling_points, evidence = self._business_scope(owner, body.fields, body.point_refs,
                                                                      body.observation_start, body.observation_end)
            if needs_points and any(
                not any(point["object"] == item["object"] for point in sampling_points)
                for item in objects
            ):
                raise ValueError("Select at least one authorized sampling point for each selected business field")
            context.update(objects=objects, field_evidence=evidence,
                           business_selection=body.fields.model_dump(mode="json"), sampling_points=sampling_points)
        else:
            context["objects"] = [item.model_dump(mode="json") for item in body.objects]
        return study_view(self.store.create(owner, version["design_id"], body.design_version_id, key,
                                            context, body.observation_start, body.observation_end))

    def _applied(self, owner: VerifiedPrincipal, study_id: UUID) -> tuple[dict, dict]:
        """执行前复查选地授权，并从准确版本装配本次方案。"""
        study = self.store.read(owner, study_id)
        if study["request_key"] is None:
            raise ValueError("Daily studies use their report batch operations")
        context = study["context_json"]
        if context.get("business_selection"):
            _, _, evidence = self._business_scope(
                owner, SelectedResearchFields.model_validate(context["business_selection"]),
                tuple(point["point_ref"] for point in context["sampling_points"]),
                study["observation_start"], study["observation_end"],
            )
            if evidence != context["field_evidence"]:
                raise DesignConflict("Study business scope evidence has changed")
        return study, self.runtime.designs.version(owner, version_id=study["design_version_id"])

    def acquire(self, owner: VerifiedPrincipal, study_id: UUID, body: AcquisitionWindow, key: str) -> dict:
        """采集使用实例固定的参考点、日期边界和来源合同。"""
        study, version = self._applied(owner, study_id)
        selected = next((entry for entry in study["context_json"]["objects"]
                         if entry["object"] == body.object.model_dump(mode="json")), None)
        if selected is None or body.start_date < study["observation_start"] or body.end_date > study["observation_end"]:
            raise ValueError("Acquisition is outside the applied study scope")
        definition = version["definition"]["research_plan"]
        request = AcquisitionRequest(**body.model_dump(), reference_point=selected["reference_point"],
                                     expected_revision=version["revision"])
        payload = prepare_acquisition(definition, request, retained_definition=definition)
        payload["definition_sha256"] = identity_sha256(definition)
        digest = identity_sha256({"study_id": str(study_id), "request": body.model_dump(mode="json")})
        request_key = "study:" + identity_sha256([str(study_id), key])
        return self.runtime.sources.enqueue(owner, study["design_id"], request_key, digest, payload,
                                            frozen_version_id=study["design_version_id"], study_id=study_id)

    def dataset(self, owner: VerifiedPrincipal, study_id: UUID, source_ids: tuple[UUID, ...],
                observations: ObservationTable | None, data_kind: str) -> dict:
        """只封存本实例来源以及属于已确权对象和日期的观测。"""
        study, version = self._applied(owner, study_id)
        if study["context_json"].get("business_selection") and data_kind != "user_supplied":
            raise ValueError("Business studies require observed or authorized source data")
        definition = version["definition"]["research_plan"]
        if any(item["unit_kind"] != "field_season" for item in definition["collection_requirements"]):
            raise ValueError("The current study dataset adapter requires field-season observations")
        datasets = self.runtime.datasets
        content = datasets.prepare(owner, definition, source_ids, observations, data_kind, study_id=study_id)
        allowed = {identity_sha256(entry["object"]) for entry in study["context_json"]["objects"]}
        if any(identity_sha256(row["object"]) not in allowed or not
               study["observation_start"] <= date.fromisoformat(row["business_date"]) <= study["observation_end"]
               for row in content["observations"]["rows"]):
            raise ValueError("Dataset observations are outside the applied study scope")
        result = datasets.store.save(owner, study["design_id"], content, study_id=study_id)
        return {"dataset_snapshot_id": result["dataset_id"]}

    def read_dataset(self, owner: VerifiedPrincipal, study_id: UUID, dataset_id: UUID) -> dict:
        """通过本实例查证样本和来源，不公开内部采集凭据。"""
        row = self.runtime.datasets.store.read(owner, dataset_id)
        if row["study_id"] != study_id:
            raise LookupError("Research study dataset was not found")
        content = row["content_json"]
        return {"dataset_snapshot_id": dataset_id, "sha256": row["content_sha256"],
                **{key: content[key] for key in ("source_snapshot_ids", "data_kind", "observations")}}

    def run(self, owner: VerifiedPrincipal, study_id: UUID, body: StudyExecution, key: str) -> dict:
        """读取冻结版本和本实例数据集，并登记可回查的运行。"""
        study, version = self._applied(owner, study_id)
        digest = identity_sha256({"study_id": str(study_id), **body.model_dump(mode="json")})
        request_key = "study:" + identity_sha256([str(study_id), key])
        prior = self.runtime.store.replay(owner, study["design_id"], request_key, digest)
        if prior is not None:
            return prior
        dataset = self.runtime.datasets.store.read(owner, body.dataset_snapshot_id)
        if dataset["study_id"] != study_id:
            raise DesignConflict("Dataset belongs to a different research study")
        content = dataset["content_json"]
        definition = version["definition"]["research_plan"]
        source_ids = tuple(UUID(value) for value in content["source_snapshot_ids"])
        prepared = prepare_observations(
            definition, body.operation, ObservationTable.model_validate(content["observations"]), content["data_kind"],
            owner.subject, execution_profiles, source_snapshots=self.runtime.sources.resolve(owner, source_ids, study_id=study_id),
        )
        payload = {**prepared.payload, "version_id": str(study["design_version_id"]),
                   "dataset_snapshot_id": str(body.dataset_snapshot_id), "request_sha256": digest}
        return self.runtime.store.enqueue(owner, study["design_id"], study["design_version_id"],
                                          body.operation, request_key, payload, study_id=study_id,
                                          dataset_snapshot_id=body.dataset_snapshot_id)

    def read_run(self, owner: VerifiedPrincipal, study_id: UUID, run_id: UUID) -> dict:
        """读取本实例的运行，拒绝把同企业其他实例的运行当成本实例证据。"""
        row = self.runtime.store.read(owner, run_id)
        if row["study_id"] != study_id:
            raise LookupError("Research study run was not found")
        return row

    def save_model(self, owner: VerifiedPrincipal, study_id: UUID, run_id: UUID, name: str) -> dict:
        """登记本实例训练的模型并回读原始运行。"""
        self.read_run(owner, study_id, run_id)
        row = self.runtime.store.save_model(owner, run_id, name)
        return self.runtime.store.model(owner, row["model_id"])
