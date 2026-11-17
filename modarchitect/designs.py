# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 16:09
# @Author  : Codex
# @File    : designs.py
"""编排私有草稿与方案版本，协调业务核权、合同和短事务。"""

from collections.abc import Mapping
from uuid import UUID

from .business import BusinessGateway, check_sampling
from .catalog import catalog
from .contracts.enterprise.identity import VerifiedPrincipal
from .contracts.identifiers import identity_sha256
from .contracts.model_center.components import Composition, DesignPublication
from .contracts.research.drafts import draft_file, import_draft
from .contracts.research.design_saves import DesignSave
from .contracts.research.plan_file import export_plan, plan_payload
from .contracts.research.plans import ResearchPlan
from .persistence.design_store import DesignConflict, DesignStore, DesignTransaction
from .persistence import design_save_store
from .validation import compile_graph, compile_plan, validate_submission
from .system_inputs import validate_input_bindings, validate_input_adoption


def draft_view(row: Mapping) -> dict:
    """输出旧草稿接口的字段，验证当前存储的摘要。"""
    configuration = row["configuration_json"]
    if identity_sha256(configuration) != row["configuration_sha256"]:
        raise DesignConflict("Persisted research draft checksum differs")
    return {
        "design_id": row["design_id"],
        "revision": row["revision"],
        "configuration": configuration,
        "configuration_sha256": row["configuration_sha256"],
        "updated_at": row["updated_at"],
    }


def _version_summary(row: Mapping) -> dict:
    """验证冻结摘要，输出可用于回读准确版本的索引。"""
    definition = row["contract_json"]
    if (
        identity_sha256(definition) != row["contract_sha256"]
        or definition["revision"] != row["revision"]
    ):
        raise DesignConflict("Persisted research version checksum or revision differs")
    return {
        "design_version_id": row["design_version_id"],
        "revision": row["revision"],
        "contract_sha256": row["contract_sha256"],
        "published_at": row["created_at"],
    }


def _version_view(tx: DesignTransaction, row: Mapping) -> dict:
    """校验准确版本及节点绑定，返回冻结定义和可解释的组合。"""
    summary = _version_summary(row)
    definition = row["contract_json"]
    composition = Composition.model_validate(definition["composition"])
    plan = compile_graph(composition)
    frozen = tx.version_bindings(row["design_version_id"])
    expected = {
        node.code: (
            node.component.code,
            node.component.revision,
            catalog()[node.component.code, node.component.revision].contract_sha256,
        )
        for node in composition.nodes
    }
    if frozen != expected:
        raise DesignConflict("Persisted research component bindings differ")
    if "report_plan" in definition:
        plan["report_plan"] = definition["report_plan"]
    return {
        **summary,
        "design_id": row["design_id"],
        "definition": definition,
        "plan": plan,
    }


def _append(
    tx: DesignTransaction,
    design_id: UUID,
    publication: DesignPublication,
    latest: Mapping | None,
) -> tuple[dict, bool]:
    """冻结下一版，完全相同的旧请求重放返回原版。"""
    if latest is not None and publication.revision <= latest["revision"]:
        existing = tx.get_version(design_id=design_id, revision=publication.revision)
        if existing["contract_sha256"] != identity_sha256(
            publication.publication_payload()
        ):
            raise DesignConflict("Published research design version has changed")
        return _version_view(tx, existing), False
    if publication.revision != (latest["revision"] if latest is not None else 0) + 1:
        raise DesignConflict("Research design revision must be the next version")
    digests = {key: entry.contract_sha256 for key, entry in catalog().items()}
    return _version_view(tx, tx.append_version(design_id, publication, digests)), True


class ResearchDesigns:
    """使用已验证主体处理同一套草稿与发布规则。"""

    def __init__(self, store: DesignStore, gateway: BusinessGateway):
        """注入持久化和业务选地适配。"""
        self.store = store
        self.gateway = gateway

    def prepare_draft(self, principal: VerifiedPrincipal, configuration: dict, *, check_selection: bool = True) -> dict:
        """集中核验草稿合同和采集授权，允许调用方在短事务中保存关联数据。"""
        configuration = import_draft(configuration)
        validate_input_bindings(configuration["definition"])
        if check_selection:
            check_sampling(self.gateway, principal, configuration["definition"])
        return configuration

    def create(
        self, principal: VerifiedPrincipal, key: str, configuration: dict
    ) -> tuple[dict, bool]:
        """核验采集点后幂等创建或重开草稿。"""
        configuration = self.prepare_draft(principal, configuration)
        validate_input_adoption(configuration["definition"], self.creation_definition(principal, key, configuration))
        with self.store.transaction(principal) as tx:
            row, created = tx.create_draft(key, configuration)
            return draft_view(row), created

    def creation_definition(self, principal: VerifiedPrincipal, key: str, configuration: dict) -> dict | None:
        """只有准确首次配置的幂等重放可以保留原采用资格。"""
        with self.store.transaction(principal) as tx:
            previous = tx.find_creation(key)
            if previous is not None and previous["initial_sha256"] == identity_sha256(configuration):
                return configuration["definition"]
        return None

    def read(self, principal: VerifiedPrincipal, design_id: UUID) -> dict:
        """按可信企业和主体读取草稿。"""
        with self.store.transaction(principal) as tx:
            return draft_view(tx.get_draft(design_id))

    def list_drafts(self, principal: VerifiedPrincipal) -> list[dict]:
        """列出当前主体的草稿。"""
        with self.store.transaction(principal) as tx:
            return [draft_view(row) for row in tx.list_drafts()]

    def save(
        self,
        principal: VerifiedPrincipal,
        design_id: UUID,
        revision: int,
        configuration: dict,
    ) -> dict:
        """保存前在线核对采集点，再用短事务更新指定修订。"""
        previous = self.read(principal, design_id)["configuration"]["definition"]
        configuration = self.prepare_draft(principal, configuration)
        validate_input_adoption(configuration["definition"], previous)
        with self.store.transaction(principal) as tx:
            return draft_view(tx.save_draft(design_id, revision, configuration))

    def save_reference(self, principal: VerifiedPrincipal, request_id: UUID, body: DesignSave) -> dict:
        """完整方案与保存回执原子提交，业务登记重试不会再次写方案。"""
        digest = identity_sha256(body.model_dump(mode="json", exclude_none=True,
                                               exclude={"provider_name", "company_id"}))
        with self.store.transaction(principal) as tx:
            previous = design_save_store.read_receipt(tx, request_id, digest)
            if previous is not None:
                return previous
        configuration = self.prepare_draft(principal, validate_submission(body.configuration), check_selection=False)
        previous_definition = self.read(principal, body.design_id)["configuration"]["definition"] if body.design_id else None
        validate_input_adoption(configuration["definition"], previous_definition)
        with self.store.transaction(principal) as tx:
            design_save_store.lock_request(tx, request_id)
            previous = design_save_store.read_receipt(tx, request_id, digest)
            if previous is not None:
                return previous
            if body.design_id is None:
                draft, _ = tx.create_draft("design-save/" + str(request_id), configuration)
                if draft["configuration_sha256"] != identity_sha256(configuration):
                    raise DesignConflict("Design save creation identity is already occupied")
            else:
                draft = tx.save_draft(body.design_id, body.expected_revision, configuration)
            return design_save_store.record_receipt(tx, request_id, digest, draft)

    def save_receipt(self, principal: VerifiedPrincipal, request_id: UUID) -> dict:
        """只返回本主体已提交结果，未知或其他主体请求不暴露存在性。"""
        with self.store.transaction(principal) as tx:
            value = design_save_store.read_receipt(tx, request_id)
            if value is None:
                raise LookupError("Design save request was not found")
            return value

    def publish(
        self, principal: VerifiedPrincipal, design_id: UUID, revision: int
    ) -> dict:
        """对当前草稿建立不可变版本，网络核权期间不持有数据库锁。"""
        with self.store.transaction(principal) as tx:
            snapshot = draft_view(tx.get_draft(design_id))
            latest = tx.latest_version(design_id)
            if snapshot["revision"] != revision:
                raise DesignConflict("Research draft revision has changed")
            plan = ResearchPlan.model_validate(snapshot["configuration"]["definition"])
            definition = plan_payload(plan)
            if (
                latest is not None
                and latest["contract_json"].get("research_plan") == definition
            ):
                return _version_view(tx, latest)
        compile_plan(plan, adopted=True)
        check_sampling(self.gateway, principal, definition)
        with self.store.transaction(principal) as tx:
            tx.lock_design(design_id)
            current = tx.get_draft(design_id, lock=True)
            if (
                current["revision"] != revision
                or current["configuration_sha256"] != snapshot["configuration_sha256"]
            ):
                raise DesignConflict("Research draft revision has changed")
            latest = tx.latest_version(design_id)
            if (
                latest is not None
                and latest["contract_json"].get("research_plan") == definition
            ):
                return _version_view(tx, latest)
            publication = DesignPublication(
                name=plan.name,
                composition=plan.composition,
                research_plan=definition,
                revision=(latest["revision"] if latest is not None else 0) + 1,
            )
            result, _ = _append(tx, design_id, publication, latest)
            return result

    def publish_direct(
        self,
        principal: VerifiedPrincipal,
        publication: DesignPublication,
        *,
        key: str | None = None,
        design_id: UUID | None = None,
    ) -> tuple[dict, bool]:
        """兼容旧版直接发布入口，保留其准确发布载荷。"""
        if publication.research_plan is None:
            compile_graph(publication.composition, adopted=True)
        else:
            draft_file(publication.research_plan)
            plan = ResearchPlan.model_validate(publication.research_plan)
            compile_plan(plan, adopted=True)
            check_sampling(self.gateway, principal, publication.research_plan)
            retained = None
            if design_id is not None:
                with self.store.transaction(principal) as tx:
                    previous = tx.latest_version(design_id)
                    retained = previous["contract_json"].get("research_plan") if previous else None
            elif key is not None:
                with self.store.transaction(principal) as tx:
                    previous = tx.find_published_creation(key)
                    if previous is not None and previous["contract_sha256"] == identity_sha256(publication.publication_payload()):
                        retained = publication.research_plan
            validate_input_adoption(publication.research_plan, retained)
        if design_id is None and publication.revision != 1:
            raise DesignConflict("A new research design must start at revision one")
        with self.store.transaction(principal) as tx:
            if design_id is None:
                if key is None:
                    raise ValueError("Design creation requires an idempotency key")
                design_id, _ = tx.create_design(key)
            tx.lock_design(design_id)
            return _append(tx, design_id, publication, tx.latest_version(design_id))

    def version(
        self,
        principal: VerifiedPrincipal,
        *,
        version_id: UUID | None = None,
        design_id: UUID | None = None,
        revision: int | None = None,
    ) -> dict:
        """读回精确版本并验证冻结节点绑定。"""
        with self.store.transaction(principal) as tx:
            row = tx.get_version(
                version_id=version_id, design_id=design_id, revision=revision
            )
            return _version_view(tx, row)

    def versions(self, principal: VerifiedPrincipal, design_id: UUID) -> list[dict]:
        """返回按修订倒序排列的方案版本。"""
        with self.store.transaction(principal) as tx:
            return [_version_summary(row) for row in tx.list_versions(design_id)]

    def list_published(
        self, principal: VerifiedPrincipal, page: int, page_size: int
    ) -> dict:
        """返回当前主体可访问的最新版方案及分页信息。"""
        with self.store.transaction(principal) as tx:
            rows, total = tx.list_published(page, page_size)
            return {
                "items": [_version_view(tx, row) for row in rows],
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    def configuration(self, principal: VerifiedPrincipal, version_id: UUID) -> dict:
        """以旧配置格式导出准确发布版本中的研究方案。"""
        definition = self.version(principal, version_id=version_id)["definition"]
        if definition.get("research_plan") is None:
            raise LookupError("Research plan was not found")
        return export_plan(ResearchPlan.model_validate(definition["research_plan"]))
