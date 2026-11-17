# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 15:31
# @Author  : Codex
# @File    : api.py
"""装配模型设计服务的 HTTP 入口和运行资源。"""

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from .business import BusinessGateway, BusinessSettings, BusinessUnavailable
from .catalog import CatalogConflict
from .contracts.enterprise.identity import EnterpriseAccessError
from .designer import assets, router as designer_router
from .designs import ResearchDesigns
from .persistence.design_store import DesignConflict, DesignStore
from .routes import compatibility, directory, research
from .runtime.routes import internal, workspace
from .runtime.service import ResearchRuntime
from .runtime.store import RuntimeStore
from .runtime.preparation import ExecutionRejected
from .validation import DesignValidationError
from .input_sources.routes import workspace as source_workspace, internal as source_internal
from .input_sources.service import InputAcquisition
from .persistence.source_store import SourceStore
from .runtime.dataset_routes import router as dataset_router
from .report_tasks.routes import workspace as report_workspace, business as report_business, internal as report_internal
from .report_tasks.service import ReportTasks
from .persistence.report_store import ReportStore


def _configured_gateway() -> BusinessGateway:
    """从部署变量装配固定业务端点。"""
    return BusinessGateway(
        BusinessSettings(
            identity_url=os.getenv("MODARCHITECT_IDENTITY_URL"),
            identity_audience=os.getenv("MODARCHITECT_IDENTITY_AUDIENCE"),
            identity_key=os.getenv("MODARCHITECT_IDENTITY_KEY"),
            selection_url=os.getenv("MODARCHITECT_SELECTION_URL"),
            selection_audience=os.getenv("MODARCHITECT_SELECTION_AUDIENCE"),
            selection_key=os.getenv("MODARCHITECT_SELECTION_KEY"),
        )
    )


async def _domain_error(_request: Request, exc: Exception) -> JSONResponse:
    """统一映射已知错误并隐藏业务上游及数据库正文。"""
    if isinstance(exc, (RequestValidationError, ValidationError)):
        status, detail = 422, "Research contract validation failed"
    elif isinstance(exc, EnterpriseAccessError):
        status, detail = 403, str(exc)
    elif isinstance(exc, (DesignConflict, CatalogConflict)):
        status, detail = 409, str(exc)
    elif isinstance(exc, LookupError):
        status, detail = 404, "Research resource was not found"
    elif isinstance(exc, (BusinessUnavailable, OperationalError)):
        status, detail = 503, "Research dependency is unavailable"
    else:
        status, detail = 422, str(exc)
    body = {"detail": detail}
    if isinstance(exc, (ExecutionRejected, DesignValidationError)):
        body["issues"] = exc.issues
    elif isinstance(exc, (RequestValidationError, ValidationError)):
        body["issues"] = [{"rule": "plan_contract", "path": list(item["loc"]),
                           "message": item["msg"]}
                          for item in exc.errors()]
    return JSONResponse(body, status_code=status)


def health() -> dict[str, str]:
    """返回应用进程的存活状态。"""
    return {"status": "ok"}


def create_app(
    *,
    database_url: str | None = None,
    business_key: str | None = None,
    api_key: str | None = None,
    authentication_mode: str | None = None,
    proxy_prefix: str | None = None,
    gateway: BusinessGateway | None = None,
) -> FastAPI:
    """装配应用。没有部署配置时保留目录、OpenAPI 和存活入口。"""
    url = database_url or os.getenv("MODARCHITECT_DATABASE_URL")
    engine = (
        create_engine(url, pool_pre_ping=True, hide_parameters=True) if url else None
    )
    store = DesignStore(engine) if engine is not None else None
    gateway = gateway or _configured_gateway()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        """检查运行角色并释放连接池。"""
        try:
            if store is not None:
                store.verify_runtime_role()
                RuntimeStore(store).verify_role()
                SourceStore(store).verify_role()
            yield
        finally:
            if engine is not None:
                engine.dispose()

    prefix = (proxy_prefix if proxy_prefix is not None else os.getenv("MODARCHITECT_PROXY_PREFIX", "")).rstrip("/")
    application = FastAPI(
        title="modarchitect", lifespan=lifespan,
        root_path_in_servers=False,
    )

    @application.middleware("http")
    async def restore_proxy_prefix(request: Request, call_next):
        """只采用部署明确允许的前缀，恢复代理已去除的ASGI路径。"""
        path = request.scope["path"]
        if prefix and request.headers.get("X-Forwarded-Prefix") == prefix:
            request.scope["root_path"] = prefix
            request.scope["path"] = prefix + request.scope["path"]
            request.scope["raw_path"] = prefix.encode("utf-8") + request.scope["raw_path"]
        if path == application.openapi_url:
            # 显式根地址按当次入口生成，不污染直连与代理共用的schema缓存。
            return JSONResponse({
                **application.openapi(),
                "servers": [{"url": request.scope.get("root_path") or "/"}],
            })
        return await call_next(request)

    @application.middleware("http")
    async def bound_research_input(request: Request, call_next):
        """流式限制研究上传和内部结果正文，避免先读取无限输入。"""
        if request.method in {"POST", "PUT"} and request.url.path.startswith(("/api/v1/workspace", "/api/v1/research", "/api/v1/model-center/designs", "/internal/v1/research", "/internal/v1/input-acquisitions", "/internal/v1/report-tasks")):
            chunks, total = [], 0
            async for chunk in request.stream():
                total += len(chunk)
                if total > 8_000_000:
                    return JSONResponse({"detail": "Research input exceeds its byte budget"}, status_code=413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        return await call_next(request)

    mode = authentication_mode or os.getenv("MODARCHITECT_AUTH_MODE", "api_key")
    if mode not in {"api_key", "delegation"}:
        raise ValueError("Research authentication mode is invalid")
    application.state.authentication_mode = mode
    application.state.api_key = api_key or business_key or os.getenv("MODARCHITECT_API_KEY")
    if mode == "delegation" and not application.state.api_key:
        application.state.api_key = os.getenv("MODARCHITECT_BUSINESS_KEY")
    application.state.gateway = gateway
    application.state.design_service = (
        ResearchDesigns(store, gateway) if store is not None else None
    )
    application.state.research_runtime = (
        ResearchRuntime(application.state.design_service, RuntimeStore(store))
        if store is not None else None
    )
    application.state.input_acquisition = (
        InputAcquisition(application.state.design_service, SourceStore(store)) if store is not None else None
    )
    application.state.research_datasets = (
        application.state.research_runtime.datasets if store is not None else None
    )
    application.state.report_tasks = (
        ReportTasks(application.state.research_runtime, ReportStore(store)) if store is not None else None
    )
    application.add_api_route("/health", health, methods=["GET"], summary="进程存活")
    for error in (
        ValueError,
        LookupError,
        BusinessUnavailable,
        OperationalError,
        RequestValidationError,
    ):
        application.add_exception_handler(error, _domain_error)
    for router in (directory, compatibility, research, designer_router, workspace, internal, source_workspace, source_internal, dataset_router, report_workspace, report_business, report_internal):
        application.include_router(router)
    application.mount("/designer", assets, name="designer")
    return application


app = create_app()
