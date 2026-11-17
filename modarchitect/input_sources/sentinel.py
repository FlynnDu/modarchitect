# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 16:20
# @Author  : Codex
# @File    : sentinel.py
"""以环境账户取得Sentinel-2准确单景反射率和原始质量，保留稀疏日期。"""

import base64
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from time import monotonic, sleep

import httpx

from ..contracts.identifiers import identity_sha256
from ..runtime.contracts import ObservationTable
from .contracts import AcquisitionRequest, SourceSnapshot, instant
from .sentinel_scene import SceneNotUsable, decode_scene, reference_grid, timestamp
from .settings import SourceSettings
from .transport import ProviderSession, SourceUnavailable

SHANGHAI = timezone(timedelta(hours=8))
EVALSCRIPT = """//VERSION=3
function setup() { return {
  input: [{bands:["B04","B08","SCL","dataMask"],units:["REFLECTANCE","REFLECTANCE","DN","DN"]}],
  output: {id:"bands",bands:4,sampleType:"FLOAT32"}, mosaicking:"TILE"
}; }
function evaluatePixel(samples) {
  if (samples.length !== 1) return [0,0,0,0];
  let s=samples[0]; return [s.B04,s.B08,s.SCL,s.dataMask];
}
function updateOutputMetadata(scenes,inputMetadata,outputMetadata) {
  outputMetadata.userData={scenes:scenes.tiles,serviceVersion:inputMetadata.serviceVersion};
}
"""


class SentinelHubSource:
    """认证、Catalog与Process有界组合；同次采集的两个波段共用准确场景。"""

    def __init__(self, session: ProviderSession, adapter: dict, settings: SourceSettings):
        """注入当前任务私有设置，不回退用户目录profile或旧数据库。"""
        self.session, self.adapter, self.settings = session, adapter, settings
        self._token, self._expires = None, 0.0
        self._cache = {}
        self._evidence_bytes = 0

    def _bytes(self, method: str, url: str, *, headers=None, data=None, body=None) -> bytes:
        """不记录认证请求/响应；错误只保留状态，读取和总预算均受限。"""
        self.session.checkpoint()
        try:
            with self.session.client.stream(method, url, headers=headers, data=data, json=body) as response:
                response.raise_for_status()
                raw = bytearray()
                for chunk in response.iter_bytes():
                    self.session.checkpoint()
                    if len(raw)+len(chunk) > 1_000_000:
                        raise SourceUnavailable("Sentinel response exceeds its resource budget")
                    raw.extend(chunk)
                return bytes(raw)
        except httpx.HTTPStatusError:
            raise
        except httpx.HTTPError as exc:
            raise SourceUnavailable("Sentinel provider transport is unavailable") from exc

    def _authenticate(self, force: bool = False) -> str:
        """按提供方实际expires_in续期，不固定令牌寿命，也不把令牌纳入证据。"""
        if not force and self._token is not None and monotonic() < self._expires:
            return self._token
        client_id, secret = self.settings.get("SH_CLIENT_ID"), self.settings.get("SH_CLIENT_SECRET")
        if not client_id or not secret:
            raise SourceUnavailable("Sentinel Hub environment client credentials are not configured")
        try:
            raw = self._bytes("POST", self.settings.endpoint("SH_TOKEN_URL"), data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret})
            token = json.loads(raw)
            expires = token["expires_in"]
            if not isinstance(token.get("access_token"), str) or not token["access_token"] or type(expires) not in {int,float} or not math.isfinite(expires) or expires <= 0:
                raise ValueError("Invalid OAuth token")
            self._token = token["access_token"]
            self._expires = monotonic()+max(0.0, expires-min(30, expires/10))
            return self._token
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise SourceUnavailable("Sentinel Hub environment authentication failed") from exc

    def _request(self, path: str, body: dict, *, binary: bool = False) -> tuple[bytes, dict]:
        """只向采用的服务基址请求；401最多换令牌一次，临时错误有界重试。"""
        url = self.settings.endpoint("SH_BASE_URL")+path
        for attempt in range(2):
            try:
                raw = self._bytes("POST", url, headers={"Authorization": "Bearer "+self._authenticate(), "Accept": "application/x-tar" if binary else "application/geo+json"}, body=body)
                self._evidence_bytes += len(raw)
                if self._evidence_bytes > 1_000_000:
                    raise SourceUnavailable("Sentinel raw evidence exceeds its resource budget")
                return raw, {"url": url, "request": body, "sha256": sha256(raw).hexdigest(), "body_base64": base64.b64encode(raw).decode("ascii")}
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if not attempt and status == 401:
                    self._authenticate(force=True)
                    continue
                if not attempt and status in {429,502,503,504}:
                    delay = exc.response.headers.get("Retry-After", "1")
                    if delay.isdigit() and int(delay) <= 3:
                        sleep(int(delay))
                        continue
                raise SourceUnavailable("Sentinel provider request failed with HTTP %s" % status) from exc
        raise SourceUnavailable("Sentinel provider request is unavailable")

    def _collect(self, request: AcquisitionRequest) -> dict:
        """Catalog只作候选；以窄窗Process实际单景及像元质量决定可用日期。"""
        if (request.end_date-request.start_date).days >= 31 or request.end_date >= instant().astimezone(SHANGHAI).date():
            raise ValueError("Sentinel requests require 1 to 31 complete historical business dates")
        start = datetime.combine(request.start_date, datetime.min.time(), SHANGHAI).astimezone(timezone.utc)
        end = datetime.combine(request.end_date+timedelta(days=1), datetime.min.time(), SHANGHAI).astimezone(timezone.utc)
        point = request.reference_point
        grid = reference_grid(point.longitude, point.latitude)
        query = {"collections": ["sentinel-2-l2a"], "intersects": {"type": "Point", "coordinates": [point.longitude, point.latitude]}, "datetime": start.isoformat()+"/"+end.isoformat(), "limit": 100, "fields": {"include": ["id", "properties.datetime"], "exclude": []}}
        candidates, evidence, cursors = [], [], set()
        for _ in range(10):
            raw, record = self._request("/catalog/v1/search", query)
            evidence.append(record)
            page = json.loads(raw)
            for feature in page["features"]:
                acquired = timestamp(feature["properties"]["datetime"])
                if start <= acquired < end:
                    candidates.append((acquired, str(feature["id"])))
            cursor = page.get("context", {}).get("next")
            if cursor is None:
                break
            key = identity_sha256(cursor)
            if key in cursors:
                raise ValueError("Sentinel Catalog pagination repeated")
            cursors.add(key)
            query = {**query, "next": cursor}
        else:
            raise SourceUnavailable("Sentinel Catalog exceeds its page budget")
        scenes, rejected, tried = {}, [], set()
        for acquired, candidate in sorted(set(candidates)):
            day = acquired.astimezone(SHANGHAI).date().isoformat()
            if day in scenes or acquired in tried:
                continue
            tried.add(acquired)
            body = {"input": {"bounds": {"bbox": grid["bbox"], "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/"+str(grid["epsg"])}}, "data": [{"type": "sentinel-2-l2a", "dataFilter": {"timeRange": {"from": (acquired-timedelta(seconds=1)).isoformat(), "to": (acquired+timedelta(seconds=1)).isoformat()}, "mosaickingOrder": "mostRecent"}, "processing": {"harmonizeValues": True, "upsampling": "NEAREST", "downsampling": "NEAREST"}}]}, "output": {"width": 1, "height": 1, "responses": [{"identifier": "bands", "format": {"type": "image/tiff"}}, {"identifier": "userdata", "format": {"type": "application/json"}}]}, "evalscript": EVALSCRIPT}
            raw, record = self._request("/process/v1", body, binary=True)
            evidence.append(record)
            try:
                actual = decode_scene(raw, grid, acquired)
            except SceneNotUsable as exc:
                rejected.append({"catalog_candidate": candidate, "acquired_at": acquired.isoformat(), "reason": str(exc)})
                continue
            if timestamp(actual["acquired_at"]).astimezone(SHANGHAI).date().isoformat() != day:
                raise ValueError("Sentinel scene crosses its declared business date")
            scenes[day] = {**actual, "catalog_candidate": candidate}
        if not scenes:
            raise SourceUnavailable("No clear single-scene Sentinel observation is available in the requested dates")
        material = {"format": "sentinelhub_scene_evidence_v1", "requests": evidence}
        raw = json.dumps(material, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(raw) > 2_000_000:
            raise SourceUnavailable("Sentinel scene evidence exceeds its resource budget")
        return {"grid": grid, "scenes": scenes, "rejected": rejected, "evidence": {"sha256": sha256(raw).hexdigest(), "body_base64": base64.b64encode(raw).decode("ascii"), "content_type": "application/json"}}

    def acquire(self, entry: dict, binding: dict, request: AcquisitionRequest) -> SourceSnapshot:
        """每个波段保留同一实际场景，不把稀疏过境扩写为完整日序列。"""
        if binding["selectors"]:
            raise ValueError("Sentinel reference method has no mutable acquisition selectors")
        key = identity_sha256(request.model_dump(mode="json"))
        if key not in self._cache:
            self._cache[key] = self._collect(request)
        collected = self._cache[key]
        variable = entry["variable"]
        band = entry["source"]["definition"]["field_code"]
        if band not in {"B04", "B08"}:
            raise ValueError("Sentinel source does not supply the adopted band")
        rows = [{"object": request.object.model_dump(mode="json"), "business_date": day, "values": {variable["code"]: scene["bands"][band]}} for day, scene in sorted(collected["scenes"].items())]
        table = ObservationTable.model_validate({"columns": [{"code": variable["code"], "name": variable["name"], "unit": variable["unit"], "value_kind": "estimated"}], "rows": rows})
        all_dates = {(request.start_date+timedelta(days=i)).isoformat() for i in range((request.end_date-request.start_date).days+1)}
        return SourceSnapshot(binding=binding, adapter=self.adapter, request=request, observations=table,
            support={**entry["source"]["definition"]["support"], "requested_point": request.reference_point.model_dump(), "grid": collected["grid"], "scene_records": [{"business_date": day, **{key: value for key, value in scene.items() if key != "bands"}} for day, scene in sorted(collected["scenes"].items())]},
            quality={"complete": True, "coverage": "actual_clear_scene_dates", "missing_dates": sorted(all_dates-set(collected["scenes"])), "rejected_scenes": collected["rejected"], "information_time": "unknown", "usage": "retrospective_or_given_factors", "license": "Copernicus Sentinel data; Sentinel Hub account conditions apply"},
            acquired_at=instant(), evidence=(collected["evidence"],))
