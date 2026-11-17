# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 16:11
# @Author  : Codex
# @File    : routes.py
"""声明版本化研究设计 HTTP 接口及可信身份依赖。"""

from secrets import compare_digest
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
)
from pydantic import Field
from fastapi.security import APIKeyHeader

from .catalog import catalog, component
from .contracts.enterprise.identity import CompanyIdentity, VerifiedPrincipal
from .contracts.enterprise.business_scope import BusinessScope
from .contracts.model_center.components import Composition, Contract, DesignPublication
from .contracts.model_center.composition import compatible
from .contracts.model_center.component_packages import (
    ComponentPackageManifest,
    ComponentPackagePortTypes,
    ComponentPackageValidation,
)
from .contracts.research.drafts import draft_file
from .contracts.research.design_saves import DesignSave, DesignReference
from .contracts.research.field_selection import FieldSelectionQuery
from .contracts.research.plan_file import (
    plan_sha256,
    requirement_payload,
)
from .contracts.research.plans import ResearchPlan, Purpose
from .designs import ResearchDesigns
from .package_preflight import registered_port_types, validate_manifest
from .validation import check_draft, compile_graph, compile_plan, load_configuration
from .runtime.service import component_record
from .study_templates import template, template_view, templates
from .system_inputs import configure_input, input_catalog
from .contracts.research.variables import VariableRole


api_key_header = APIKeyHeader(name="X-Modarchitect-Api-Key", scheme_name="ModarchitectApiKey", auto_error=False)


def require_key(
    request: Request,
    key: Annotated[str | None, Depends(api_key_header)] = None,
) -> None:
    """验证接入方业务凭据，部署缺少凭据时关闭业务入口。"""
    configured = request.app.state.api_key
    if request.app.state.authentication_mode == "delegation" and key is None:
        key = request.headers.get("X-MLGrowth-Business-Key")
    if not configured:
        raise HTTPException(503, "Research business access is not configured")
    if not key or not compare_digest(configured.encode("utf-8"), key.encode("utf-8")):
        raise HTTPException(401, "Research business credential is invalid")


async def request_business_scope(
    request: Request,
    provider_name: str | None = None,
    company_id: Annotated[int | None, Query(gt=0, lt=2**63)] = None,
) -> BusinessScope | None:
    """API-Key模式从正文或查询采用范围，冲突时拒绝而不猜测企业。"""
    if request.app.state.authentication_mode != "api_key":
        return None
    query = {"provider_name": provider_name, "company_id": company_id}
    body = {}
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    is_json = media_type == "application/json" or (media_type.startswith("application/") and media_type.endswith("+json"))
    if request.method in {"POST", "PUT"} and is_json:
        try:
            value = await request.json()
        except ValueError:
            raise HTTPException(422, "Business request must be valid JSON")
        if isinstance(value, dict):
            body = {name: value.get(name) for name in query}
    if any(query[name] is not None and body.get(name) is not None
           and query[name] != body[name] for name in query):
        raise HTTPException(422, "Business body and query scopes differ")
    selected = {name: body.get(name) if body.get(name) is not None else query[name] for name in query}
    return BusinessScope.model_validate(selected)


def principal(
    request: Request,
    scope: Annotated[BusinessScope | None, Depends(request_business_scope)],
) -> VerifiedPrincipal:
    """新部署信任持Key业务后端的企业声明，历史委托模式显式保留。"""
    if request.app.state.authentication_mode == "api_key":
        now = datetime.now(timezone.utc)
        return VerifiedPrincipal(CompanyIdentity(scope.provider_name, scope.company_id),
                                 "business_api", "modarchitect_api", "api_key_v1",
                                 now, now + timedelta(minutes=10))
    delegation = request.headers.get("X-Enterprise-Delegation")
    if not delegation or len(delegation) > 8192:
        raise HTTPException(401, "Enterprise delegation is required")
    return request.app.state.gateway.identify(delegation)


def design_service(request: Request) -> ResearchDesigns:
    """取得装配完成的方案服务。"""
    service = request.app.state.design_service
    if service is None:
        raise HTTPException(503, "Research database is not configured")
    return service


class PublishDraft(Contract):
    """使用明确的草稿修订发布。"""

    expected_revision: Annotated[int, Field(strict=True, ge=1)]


class SaveDraft(PublishDraft):
    """使用草稿修订及完整配置文件更新。"""

    configuration: dict


Principal = Annotated[VerifiedPrincipal, Depends(principal)]
DesignService = Annotated[ResearchDesigns, Depends(design_service)]
RequestKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=1, max_length=128)
]

directory = APIRouter(prefix="/api/v1/model-center", tags=["组件目录"])
compatibility = APIRouter(
    prefix="/api/v1/model-center",
    tags=["方案版本"],
    dependencies=[Depends(require_key)],
)
research = APIRouter(
    prefix="/api/v1/research",
    tags=["研究设计"],
    dependencies=[Depends(require_key)],
)


@research.get("/study-templates")
def business_templates(owner: Principal) -> dict:
    """企业前端读取同一方案目录，身份失败不退回个人工作区。"""
    return {"items": [template_view(row) for row in templates()]}


@research.get("/study-templates/{template_id}")
def business_template(template_id: str, owner: Principal, sha256: str | None = None) -> dict:
    """复用准确模板投影，不向浏览器发送受限原生资料。"""
    return template_view(template(template_id, sha256), include_definition=True)


@research.get("/models")
def business_models(owner: Principal, service: DesignService) -> dict:
    """按企业用户读取已保存模型，沿用模型存储的主体隔离。"""
    from .runtime.store import RuntimeStore

    return {"items": RuntimeStore(service.store).list_models(owner)}


@research.get("/models/{model_id}")
def business_model(model_id: UUID, owner: Principal, service: DesignService) -> dict:
    """准确模型仅向其所属主体返回，不因目录可见而授予私有模型访问权。"""
    from .runtime.store import RuntimeStore

    return RuntimeStore(service.store).model(owner, model_id)


class ConfigureInput(Contract):
    """选择系统输入身份、目录允许的属性和研究角色。"""

    key: str
    selectors: dict[str, str] = Field(default_factory=dict)
    role: VariableRole = "covariate"
    required_for: Annotated[tuple[Purpose, ...], Field(min_length=1)] = ("train",)


@directory.get("/research-inputs")
def list_research_inputs() -> dict:
    """公开四类标准定义和来源限制，不包含企业数据或凭据。"""
    return input_catalog()


@directory.get("/research-rules")
def research_rules() -> dict:
    """公开研究输入、计算与输出的规则入口及当前实现范围。"""
    from .runtime.preparation import rule_catalog

    return rule_catalog()


@directory.post("/research-inputs/configure")
def configure_research_input(body: ConfigureInput) -> dict:
    """从权威定义生成方案输入，拒绝任意单位及来源。"""
    return configure_input(body.key, body.selectors, body.role, required_for=body.required_for)


@directory.get("/components")
def list_components(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict:
    """分页列出当前采用的组件。"""
    entries = [
        component_record(item) for item in catalog().values() if item.available_for_new_design
    ]
    start = (page - 1) * page_size
    return {
        "items": entries[start : start + page_size],
        "total": len(entries),
        "page": page,
        "page_size": page_size,
    }


@directory.get("/components/{code}")
def get_component(
    code: str, revision: Annotated[int | None, Query(ge=1)] = None
) -> dict:
    """返回当前组件或指定的准确历史版本。"""
    return component_record(component(code, revision))


@directory.get("/components/{code}/versions")
def component_versions(code: str) -> dict:
    """列出可用于历史解释的准确版本。"""
    component(code)
    items = [
        component_record(item) for (key, _), item in reversed(catalog().items()) if key == code
    ]
    return {"items": items, "total": len(items)}


@directory.get("/components/{code}/outputs/{output}/compatible-inputs")
def compatible_inputs(
    code: str,
    output: str,
    revision: Annotated[int | None, Query(ge=1)] = None,
) -> dict:
    """只列出当前采用组件中数据合同相等的输入端口。"""
    definition = component(code, revision).definition
    source = next((item for item in definition.outputs if item.code == output), None)
    if source is None:
        raise LookupError("Component output was not found")
    items = [
        {
            "code": item.definition.code,
            "revision": item.definition.revision,
            "input": port.code,
        }
        for item in catalog().values()
        if item.available_for_new_design
        for port in item.definition.inputs
        if compatible(source.data_type, port.data_type)
    ]
    return {
        "source": {"code": code, "revision": definition.revision, "output": output},
        "items": items,
        "total": len(items),
    }


@directory.post("/compositions/validate")
def validate_composition(body: Composition) -> dict:
    """按准确端口及节点依赖编译新组合。"""
    return compile_graph(body, adopted=True)


@directory.get("/component-packages/schema")
def component_manifest_schema() -> dict:
    """公布内置和供方组件包共同遵循的上传清单格式。"""
    return ComponentPackageManifest.model_json_schema()


@directory.get("/component-packages/port-types")
def component_package_port_types() -> ComponentPackagePortTypes:
    """列出候选文件制品可申报的已登记端口类型。"""
    items = registered_port_types()
    return ComponentPackagePortTypes(items=items, total=len(items))


@compatibility.post("/component-packages/validate", tags=["组件目录"])
def preflight_component(body: ComponentPackageManifest) -> ComponentPackageValidation:
    """校验候选清单和目录兼容性，返回候选摘要。"""
    return validate_manifest(body)


@research.post("/plans/validate")
def validate_plan(body: ResearchPlan) -> dict:
    """检查完整方案，返回科学摘要和采集要求。"""
    return {
        "plan_sha256": plan_sha256(body),
        "compiled": compile_plan(body, adopted=True),
        "collection_requirements": [
            requirement_payload(item) for item in body.collection_requirements
        ],
    }


@research.post("/configurations/draft")
def configuration_draft(body: dict) -> dict:
    """生成可携带和校验的未完成草稿文件。"""
    return draft_file(body)


@research.post("/configurations/check")
def configuration_check(body: dict) -> dict:
    """检查草稿完整性和科学合同，返回可定位问题。"""
    return check_draft(body)


@research.post("/configurations/import")
def configuration_import(body: dict) -> dict:
    """校验文件摘要，按准确版本读入历史配置。"""
    return load_configuration(body)


@research.post("/field-selections/resolve")
def resolve_fields(
    body: FieldSelectionQuery, request: Request, owner: Principal
) -> dict:
    """从业务端解析当前主体有权选择的地块和点位。"""
    return request.app.state.gateway.resolve(owner, body).model_dump(mode="json")


@research.post(
    "/design-drafts", status_code=201, responses={200: {"description": "创建重放"}}
)
def create_draft(
    body: dict,
    response: Response,
    owner: Principal,
    service: DesignService,
    key: RequestKey,
) -> dict:
    """幂等创建私有草稿。"""
    value, created = service.create(owner, key, body)
    response.status_code = 201 if created else 200
    return value


@research.get("/design-drafts")
def list_drafts(owner: Principal, service: DesignService) -> dict:
    """列出当前主体可见的草稿。"""
    return {"items": service.list_drafts(owner)}


@research.post("/design-saves", response_model=DesignReference)
def save_design_reference(
    body: DesignSave, owner: Principal, service: DesignService,
    request_id: Annotated[UUID, Header(alias="Idempotency-Key")],
) -> dict:
    """原子保存完整配置并返回供业务关联采用的准确回执。"""
    return service.save_reference(owner, request_id, body)


@research.get("/design-saves/{request_id}", response_model=DesignReference)
def get_save_receipt(request_id: UUID, owner: Principal, service: DesignService) -> dict:
    """响应丢失或业务登记失败时，按原请求查询已提交保存结果。"""
    return service.save_receipt(owner, request_id)


@research.get("/design-drafts/{design_id}")
def get_draft(design_id: UUID, owner: Principal, service: DesignService) -> dict:
    """按原身份重开私有草稿。"""
    return service.read(owner, design_id)


@research.put("/design-drafts/{design_id}")
def update_draft(
    design_id: UUID, body: SaveDraft, owner: Principal, service: DesignService
) -> dict:
    """核对修订后保存草稿。"""
    return service.save(owner, design_id, body.expected_revision, body.configuration)


@research.post("/design-drafts/{design_id}/check")
def check_saved_draft(
    design_id: UUID, owner: Principal, service: DesignService
) -> dict:
    """使用与配置检查相同的规则检查已保存草稿。"""
    return check_draft(service.read(owner, design_id)["configuration"])


@research.post("/design-drafts/{design_id}/publish")
def publish_draft(
    design_id: UUID, body: PublishDraft, owner: Principal, service: DesignService
) -> dict:
    """发布当前草稿修订。"""
    return service.publish(owner, design_id, body.expected_revision)


@research.get("/design-versions/{version_id}/configuration")
def get_configuration(
    version_id: UUID, owner: Principal, service: DesignService
) -> dict:
    """导出准确发布版本的旧配置格式。"""
    return service.configuration(owner, version_id)


@compatibility.post(
    "/designs", status_code=201, responses={200: {"description": "创建重放"}}
)
def create_design(
    body: DesignPublication,
    response: Response,
    owner: Principal,
    service: DesignService,
    key: RequestKey,
) -> dict:
    """处理旧版直接创建方案首版。"""
    result, created = service.publish_direct(owner, body, key=key)
    response.status_code = 201 if created else 200
    return result


@compatibility.get("/designs/{design_id}")
def get_design(design_id: UUID, owner: Principal, service: DesignService) -> dict:
    """读取当前主体的最新发布方案。"""
    return service.version(owner, design_id=design_id)


@compatibility.get("/designs")
def list_designs(
    owner: Principal,
    service: DesignService,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> dict:
    """分页读取当前用户已发布的方案。"""
    return service.list_published(owner, page, page_size)


@compatibility.get("/designs/{design_id}/versions")
def list_versions(design_id: UUID, owner: Principal, service: DesignService) -> dict:
    """列出准确方案的历史版本。"""
    items = service.versions(owner, design_id)
    return {"items": items, "total": len(items)}


@compatibility.get("/designs/{design_id}/versions/{revision}")
def get_version(
    design_id: UUID,
    revision: Annotated[int, Path(ge=1)],
    owner: Principal,
    service: DesignService,
) -> dict:
    """读取准确历史版本。"""
    return service.version(owner, design_id=design_id, revision=revision)


@compatibility.post(
    "/designs/{design_id}/versions",
    status_code=201,
    responses={200: {"description": "发布重放"}},
)
def publish_version(
    design_id: UUID,
    body: DesignPublication,
    response: Response,
    owner: Principal,
    service: DesignService,
) -> dict:
    """处理旧版直接追加准确方案版本。"""
    value, created = service.publish_direct(owner, body, design_id=design_id)
    response.status_code = 201 if created else 200
    return value
