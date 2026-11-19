# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 16:57
# @Author  : Codex
# @File    : designer.py
"""提供模型设计演示页面及有界的无状态 JSON 操作。"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .contracts.research.drafts import draft_file
from .validation import check_definition, load_configuration

class DesignerAssets(StaticFiles):
    """设计器更新时重新校验静态资源，避免旧页面与新模块混用。"""

    async def get_response(self, path: str, scope: dict) -> Response:
        """保留ETag及304语义，要求浏览器采用前先核对当前制品。"""
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


router = APIRouter(include_in_schema=False)
assets = DesignerAssets(directory=Path(__file__).parent / "web" / "designer", html=True)
# 为接近规范草稿大小上限的文件保留外部信封空间。
MAX_JSON_BYTES = 1_048_576


@router.get("/")
def home(request: Request) -> RedirectResponse:
    """从应用首页进入设计器。"""
    return RedirectResponse(request.scope.get("root_path", "") + "/designer/")


async def _read_json(request: Request) -> dict:
    """读取演示 JSON，限制上传大小并拒绝异常结构。"""
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    if content_type.strip().lower() != "application/json":
        raise HTTPException(415, "Expected a JSON request")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_JSON_BYTES:
            raise HTTPException(413, "Configuration exceeds the demo size limit")
        body.extend(chunk)
    try:
        value = json.loads(body)
    except (ValueError, RecursionError) as exc:
        raise HTTPException(422, "Configuration JSON is invalid") from exc
    if not isinstance(value, dict):
        raise HTTPException(422, "Configuration must be a JSON object")
    return value


def _prepare(definition: dict) -> dict:
    """生成可导出的草稿，并复用研究方案检查。"""
    configuration = draft_file(definition)
    return {"configuration": configuration, "check": check_definition(definition)}


@router.post("/designer/validate")
async def validate(request: Request) -> dict:
    """检查浏览器内的定义并返回完整草稿信封。"""
    return await run_in_threadpool(_prepare, await _read_json(request))


def _restore(file: dict) -> dict:
    """验明文件摘要和准确版本，再检查恢复后的定义。"""
    return _prepare(load_configuration(file)["definition"])


@router.post("/designer/import")
async def restore(request: Request) -> dict:
    """读入演示文件，返回恢复后的草稿与检查结果。"""
    return await run_in_threadpool(_restore, await _read_json(request))
