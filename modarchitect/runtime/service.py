# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 21:21
# @Author  : Codex
# @File    : service.py
"""编排准确方案、封存输入、运行请求及模型复用。"""

import json
import os
from pathlib import Path
from uuid import UUID

from ..contracts.enterprise.identity import VerifiedPrincipal
from ..catalog import ComponentVersion
from ..contracts.identifiers import identity_sha256
from ..designs import ResearchDesigns
from ..system_inputs import seal_input_sources, validate_input_bindings, validate_input_adoption
from ..execution_contracts import execution_capability
from ..persistence.source_store import SourceStore
from ..persistence.dataset_store import DatasetStore
from ..datasets import ResearchDatasets
from .contracts import PredictionRequest, TrainingRequest, ExecutionRequest, SavePlan, TemplateExecutionRequest, ExecutionCheckRequest, ObservationTable
from .preparation import ExecutionRejected, prepare_observations, prepare_template, prepare_prediction
from .store import RuntimeStore


def profiles() -> dict[str, dict]:
    """读取部署提供的制品注册表，镜像地址不接受客户端覆盖。"""
    filename = os.getenv("MODARCHITECT_RUNTIME_PROFILES")
    if not filename:
        raise ValueError("Research execution profiles are not configured")
    value = json.loads(Path(filename).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or any(
        not isinstance(item, dict) or not item.get("image", "").startswith("sha256:")
        for item in value.values()
    ):
        raise ValueError("Research execution profile registry is invalid")
    return value


def profile_key(component: dict) -> str:
    """准确组件身份作为注册及运行引用。"""
    return "%s@%s" % (component["code"], component["revision"])


def request_identity(request) -> str:
    """没有新快照引用时保持旧请求摘要，避免升级破坏已保存的幂等键。"""
    exclude = {"source_snapshot_ids"} if not request.source_snapshot_ids else set()
    if request.dataset_snapshot_id is None:
        exclude.add("dataset_snapshot_id")
    return identity_sha256(request.model_dump(mode="json", exclude=exclude))


def component_record(version: ComponentVersion) -> dict:
    """在纯组件合同上附加当前部署的实际执行可用性。"""
    record = version.record()
    capability = execution_capability(
        {"code": version.definition.code, "revision": version.definition.revision}
    )
    record["research_contract"]["capabilities"] = (
        capability.model_dump(mode="json") if capability else None
    )
    if os.getenv("MODARCHITECT_RUNTIME_PROFILES"):
        try:
            key = "%s@%s" % (version.definition.code, version.definition.revision)
            if key in profiles():
                record["research_contract"]["execution"] = {
                    "status": "available",
                    "profile": "offline_cpu",
                }
        except (OSError, ValueError):
            record["research_contract"]["execution"] = {"status": "unavailable"}
    return record


def execution_profiles(plan: dict) -> dict:
    """同时冻结训练组件及其独立推理组件的执行制品。"""
    registered = profiles()
    selected = {}
    for node in plan["composition"]["nodes"]:
        key = profile_key(node["component"])
        if key not in registered:
            raise ValueError("Component execution is not available: %s" % key)
        selected[key] = registered[key]
        inference = registered[key].get("inference")
        if inference:
            selected[inference] = registered[inference]
    return selected


class ResearchRuntime:
    """复用已有保存和发布流程，计算交给独立调度及 Worker。"""

    def __init__(self, designs: ResearchDesigns, store: RuntimeStore):
        """注入实际方案服务和运行持久化。"""
        self.designs = designs
        self.store = store
        self.sources = SourceStore(store.store)
        self.datasets = ResearchDatasets(designs, DatasetStore(store.store), self.sources)

    def input_data(self, owner: VerifiedPrincipal, request) -> tuple[ObservationTable | None, str, tuple]:
        """解析新数据集或历史输入，数据集性质与引用只相信受权持久记录。"""
        if request.dataset_snapshot_id is None:
            return request.observations, request.data_kind, request.source_snapshot_ids
        content = self.datasets.resolve(owner, request.dataset_snapshot_id)
        if "study_id" in content:
            raise ValueError("Applied study datasets must be used through their study operations")
        return (ObservationTable.model_validate(content["observations"]), content["data_kind"],
                tuple(UUID(value) for value in content["source_snapshot_ids"]))

    def source_snapshots(self, owner: VerifiedPrincipal, identities: tuple) -> list[dict]:
        """来源引用错误与预检、实际启动保持同一规则定位。"""
        try:
            return self.sources.resolve(owner, identities)
        except (LookupError, ValueError) as exc:
            raise ExecutionRejected("input_source", "Authorized source snapshots are missing or invalid", ["source_snapshot_ids"]) from exc

    def save_plan(
        self,
        owner: VerifiedPrincipal,
        body: SavePlan,
        *,
        key: str | None = None,
        design_id=None,
    ) -> dict:
        """共用草稿验证，配置和观测在同一个受权事务中形成修订。"""
        from ..contracts.research.drafts import draft_file

        configuration = self.designs.prepare_draft(owner, draft_file(body.definition), check_selection=body.observations is not None or body.dataset_snapshot_id is not None)
        retained = (self.designs.read(owner, design_id)["configuration"]["definition"] if design_id is not None
                    else self.designs.creation_definition(owner, key, configuration) if key is not None else None)
        validate_input_adoption(body.definition, retained)
        observations, data_kind, source_ids = self.input_data(owner, body)
        if (
            design_id is not None
            and observations is None
            and "data_kind" not in body.model_fields_set
        ):
            # 只改方案元信息时沿用原数据标记，避免把已存合成记录默认为真实上传。
            data_kind = self.store.data(owner, design_id)["data_kind"]
        validate_input_bindings(
            body.definition, require_catalog=data_kind != "synthetic"
        )
        if observations is not None:
            seal_input_sources(
                body.definition, observations.sealed(), data_kind, owner.subject,
                source_snapshots=self.source_snapshots(owner, source_ids),
            )
        elif body.source_snapshot_ids:
            raise ValueError("Source snapshot references require an observation table")
        return self.store.save_plan(
            owner,
            configuration,
            observations.sealed() if observations is not None else None,
            data_kind,
            key=key,
            design_id=design_id,
            revision=body.expected_revision,
            version_name=body.version_name,
            replace_candidate="version_name" in body.model_fields_set,
            source_snapshot_ids=source_ids,
        )

    def train(
        self,
        owner: VerifiedPrincipal,
        request: TrainingRequest | ExecutionRequest,
        key: str,
    ) -> dict:
        """从当前准确修订发布方案，再原子封存运行及调度记录。"""
        request_sha = request_identity(request)
        operation = (
            request.operation if isinstance(request, ExecutionRequest) else "train"
        )
        previous = self.store.replay(owner, request.design_id, key, request_sha)
        if previous is not None:
            return previous
        draft = self.designs.read(owner, request.design_id)
        if draft["revision"] != request.expected_revision:
            from ..persistence.design_store import DesignConflict

            raise DesignConflict("Research draft revision has changed")
        definition = draft["configuration"]["definition"]
        observations, data_kind, source_ids = self.input_data(owner, request)
        prepared = prepare_observations(
            definition, operation, observations, data_kind,
            owner.subject, execution_profiles,
            strict_purpose=isinstance(request, ExecutionRequest),
            source_snapshots=self.source_snapshots(owner, source_ids),
        )
        version = self.designs.publish(
            owner, request.design_id, request.expected_revision
        )
        payload = {**prepared.payload, "version_id": str(version["design_version_id"]), "request_sha256": request_sha}
        return self.store.enqueue(
            owner,
            request.design_id,
            version["design_version_id"],
            operation,
            key,
            payload,
        )

    def predict(
        self, owner: VerifiedPrincipal, request: PredictionRequest, key: str
    ) -> dict:
        """按准确模型及其既定制品生成新预测任务，保持训练状态。"""
        model = self.store.model(owner, request.model_id)
        training = self.store.read(owner, model["run_id"])
        observations, data_kind, source_ids = self.input_data(owner, request)
        if observations is None:
            raise ValueError("Prediction requires observations or an exact dataset")
        prepared = prepare_prediction(model, observations, data_kind, owner.subject, profiles(),
                                      self.source_snapshots(owner, source_ids))
        payload = {**prepared.payload, "request_sha256": request_identity(request)}
        return self.store.enqueue(
            owner,
            training["design_id"],
            training["design_version_id"],
            "predict",
            key,
            payload,
        )

    def run_template(self, owner: VerifiedPrincipal, request: TemplateExecutionRequest, key: str) -> dict:
        """按批准模板封存原生案例，复用发布、短事务投递及真实调度。"""
        from ..persistence.design_store import DesignConflict

        request_sha = identity_sha256(request.model_dump(mode="json"))
        previous = self.store.replay(owner, request.design_id, key, request_sha)
        if previous is not None:
            return previous
        draft = self.designs.read(owner, request.design_id)
        if draft["revision"] != request.expected_revision:
            raise DesignConflict("Research draft revision has changed")
        definition = draft["configuration"]["definition"]
        prepared = prepare_template(definition, request.template_id, request.template_sha256,
                                    owner.subject, execution_profiles)
        version = self.designs.publish(owner, request.design_id, request.expected_revision)
        payload = {**prepared.payload, "version_id": str(version["design_version_id"]), "request_sha256": request_sha}
        return self.store.enqueue(owner, request.design_id, version["design_version_id"], payload["kind"], key, payload)

    def check_execution(self, owner: VerifiedPrincipal, body: ExecutionCheckRequest) -> dict:
        """对当前编辑输入执行与启动相同的准备规则，不创建任何研究记录。"""
        from ..contracts.research.drafts import draft_file

        try:
            self.designs.prepare_draft(owner, draft_file(body.definition))
            retained = self.designs.read(owner, body.design_id)["configuration"]["definition"] if body.design_id is not None else None
            try:
                validate_input_adoption(body.definition, retained)
            except ValueError as exc:
                raise ExecutionRejected("input_source", exc, ["collection_requirements"]) from exc
            marker = body.definition.get("layout", {}).get("study_template")
            native = any(recipe.get("kind") == "artifact" for recipe in body.definition.get("input_recipes", {}).values() if isinstance(recipe, dict))
            if native:
                if not marker or not marker.get("id") or not marker.get("sha256") or body.observations is not None:
                    raise ExecutionRejected("template_identity", "Template identity and approved inputs must be used together")
                prepared = prepare_template(body.definition, marker["id"], marker["sha256"],
                                            owner.subject, execution_profiles)
                if prepared.payload["kind"] != body.operation:
                    raise ExecutionRejected("operation", "Research purpose differs from the requested operation")
            else:
                observations, data_kind, source_ids = self.input_data(owner, body)
                prepared = prepare_observations(body.definition, body.operation, observations,
                                                data_kind, owner.subject, execution_profiles,
                                                source_snapshots=self.source_snapshots(owner, source_ids))
        except ExecutionRejected as exc:
            return {"can_execute": False, "issues": exc.issues}
        except LookupError:
            issue = ExecutionRejected("template_identity", "Referenced study template was not found")
            return {"can_execute": False, "issues": issue.issues}
        return {"can_execute": True, "issues": []}
