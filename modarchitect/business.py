# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 16:04
# @Author  : Codex
# @File    : business.py
"""验证业务身份和选地响应，统一草稿与发布的采集点授权。"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from urllib.parse import urlsplit

import httpx
from shapely.geometry import shape

from .contracts.enterprise.identity import (
    CompanyIdentity,
    EnterpriseAccessError,
    VerifiedPrincipal,
)
from .contracts.identifiers import identity_sha256
from .contracts.research.field_selection import (
    FieldSelectionCandidate,
    FieldSelectionQuery,
    FieldSelectionResult,
    SelectedResearchFields,
    require_sampling_points,
)
from .contracts.research.identity_headers import validate_subject
from .contracts.research.plans import sampling_points_required


class BusinessUnavailable(RuntimeError):
    """依赖缺配置、失联或响应无法验证。"""


@dataclass(frozen=True)
class BusinessSettings:
    """端点和凭据来自部署设施。"""

    identity_url: str | None
    identity_audience: str | None
    identity_key: str | None = field(repr=False)
    selection_url: str | None
    selection_audience: str | None
    selection_key: str | None = field(repr=False)


def _timestamp(value: str) -> datetime:
    """要求业务签发的时间带时区。"""
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.utcoffset() is None:
        raise ValueError("Business timestamp requires a timezone")
    return timestamp


class BusinessGateway:
    """每次在线核权，使用由部署提供的固定 HTTPS 端点。"""

    def __init__(
        self,
        settings: BusinessSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        """允许工程验收通过 HTTP 传输替身复用完整协议验证。"""
        self.settings = settings
        self.transport = transport

    def _post(
        self,
        url: str | None,
        key: str | None,
        audience: str | None,
        payload: dict,
        *,
        delegation: str | None = None,
    ) -> dict:
        """固定端点失败时返回稳定的错误，响应正文及凭据留在边界内。"""
        try:
            parsed = urlsplit(url or "")
        except ValueError as exc:
            raise BusinessUnavailable("Business endpoint is not configured") from exc
        if (
            not all((key, audience, parsed.hostname))
            or parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.query
        ):
            raise BusinessUnavailable("Business endpoint is not configured")
        headers = {"Authorization": "Bearer %s" % key}
        if delegation is not None:
            headers["X-Enterprise-Delegation"] = delegation
        try:
            with (
                httpx.Client(
                    transport=self.transport, timeout=10, trust_env=False
                ) as client,
                client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json={"schema_version": "1.0", "audience": audience, **payload},
                ) as response,
            ):
                if response.status_code in (401, 403):
                    raise EnterpriseAccessError(
                        "Business authorization denied the operation"
                    )
                if response.status_code != 200:
                    raise BusinessUnavailable("Business response is unavailable")
                buffer = bytearray()
                for chunk in response.iter_bytes():
                    if len(buffer) + len(chunk) > 2 * 1024 * 1024:
                        raise BusinessUnavailable(
                            "Business response exceeds its size budget"
                        )
                    buffer.extend(chunk)
            body = json.loads(buffer)
            if not isinstance(body, dict) or body.pop("schema_version", None) != "1.0":
                raise BusinessUnavailable("Business response contract differs")
            return body
        except (httpx.HTTPError, UnicodeError) as exc:
            raise BusinessUnavailable("Business request failed") from exc
        except ValueError as exc:
            if isinstance(exc, EnterpriseAccessError):
                raise
            raise BusinessUnavailable("Business response is not valid JSON") from exc

    def identify(self, delegation: str) -> VerifiedPrincipal:
        """解析经过业务身份端验证的主体、受众、企业和有效期。"""
        settings = self.settings
        body = self._post(
            settings.identity_url,
            settings.identity_key,
            settings.identity_audience,
            {},
            delegation=delegation,
        )
        if body.get("decision") == "denied":
            raise EnterpriseAccessError("Business authorization denied the operation")
        try:
            if body["decision"] != "allowed":
                raise ValueError("Unknown identity decision")
            data = body["principal"]
            principal = VerifiedPrincipal(
                CompanyIdentity(data["company_source"], data["company_id"]),
                validate_subject(data["subject"]),
                data["audience"],
                data["policy_revision"],
                _timestamp(data["verified_at"]),
                _timestamp(data["expires_at"]),
            )
            principal.validate(
                audience=settings.identity_audience, now=datetime.now(timezone.utc)
            )
            return principal
        except EnterpriseAccessError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise BusinessUnavailable("Business principal contract differs") from exc

    def resolve(
        self, principal: VerifiedPrincipal, query: FieldSelectionQuery
    ) -> FieldSelectionResult:
        """用请求摘要绑定授权结果并核对候选地块的作物、季节和归属。"""
        geometry = shape(query.geometry)
        if not geometry.is_valid or geometry.is_empty or geometry.area <= 0:
            raise ValueError("Research selection polygon is invalid")
        settings = self.settings
        payload = query.model_dump(mode="json")
        digest = identity_sha256(payload)
        company = {
            "source": principal.company.source,
            "company_id": principal.company.company_id,
        }
        body = self._post(
            settings.selection_url,
            settings.selection_key,
            settings.selection_audience,
            {
                "company": company,
                "subject": principal.subject,
                "query": payload,
                "query_sha256": digest,
            },
        )
        try:
            verified_company = CompanyIdentity(
                body["company"]["source"], body["company"]["company_id"]
            )
            if (
                verified_company != principal.company
                or body["subject"] != principal.subject
                or body["audience"] != settings.selection_audience
                or body["query_sha256"] != digest
                or not _timestamp(body["verified_at"])
                <= datetime.now(timezone.utc)
                < _timestamp(body["expires_at"])
            ):
                raise ValueError("Field selection authorization differs")
            result = FieldSelectionResult.model_validate(
                {"candidates": body["candidates"]}
            )
            fields = set()
            for item in result.candidates:
                context = item.context
                root = context.units[0]
                if (
                    root.field_ref in fields
                    or root.crop_code != query.crop_code
                    or (context.season_start, context.season_end)
                    != (query.season_start, query.season_end)
                ):
                    raise ValueError("Field selection crop, season or identity differs")
                fields.add(root.field_ref)
            return result
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            raise BusinessUnavailable("Field selection response is invalid") from exc


def authorized_fields(
    gateway: BusinessGateway,
    principal: VerifiedPrincipal,
    selected: SelectedResearchFields,
) -> tuple[FieldSelectionCandidate, ...]:
    """从当前授权结果提取显式选择的同一项目地块。"""
    result = gateway.resolve(principal, selected.selection)
    matches = {item.context.units[0].field_ref: item for item in result.candidates}
    if not set(selected.field_refs) <= matches.keys():
        raise LookupError("Authorized research field was not found")
    fields = tuple(matches[ref] for ref in selected.field_refs)
    if len({item.context.project_ref for item in fields}) != 1:
        raise ValueError("Selected business fields belong to different projects")
    return fields


def check_sampling(
    gateway: BusinessGateway,
    principal: VerifiedPrincipal,
    definition: dict,
) -> None:
    """对每块地重新核验至少一个业务授权点位。"""
    requirements = definition.get("collection_requirements", [])
    if not isinstance(requirements, list):
        raise ValueError("Collection requirements must be an array")
    flags = [
        sampling_points_required(
            item.get("unit_kind"), item.get("requires_sampling_points")
        )
        for item in requirements
        if isinstance(item, dict)
    ]
    if not any(flags):
        return
    if definition.get("sampling_selection") is None:
        raise ValueError("Select business fields before saving a sampling-point plan")
    selection = SelectedResearchFields.model_validate(definition["sampling_selection"])
    require_sampling_points(authorized_fields(gateway, principal, selection))
