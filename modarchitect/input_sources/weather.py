# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 21:47
# @Author  : Codex
# @File    : weather.py
"""按准确日界和完整小时资料转换 Open-Meteo 历史网格天气。"""

from datetime import date, timedelta, timezone
import json
import math

from ..runtime.contracts import ObservationTable
from .contracts import AcquisitionRequest, SourceSnapshot, instant
from .transport import ProviderSession
from .settings import SourceSettings

DAILY = {
    "temperature_2m_min": "°C",
    "temperature_2m_max": "°C",
    "precipitation_sum": "mm",
    "shortwave_radiation_sum": "MJ/m²",
}
HOURLY = {"temperature_2m": "°C", "wind_speed_10m": "m/s", "dew_point_2m": "°C"}


def number(value: object) -> float:
    """拒绝缺测、布尔、字符串和无穷值，不隐式填补。"""
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ValueError("Weather requires finite numeric source values")
    return float(value)


def convert_weather(raw: dict, start: date, end: date) -> list[dict]:
    """完整日值与24个唯一整点才输出，不将预报或极值均值冒充小时均值。"""
    if raw.get("timezone") != "Asia/Shanghai" or raw.get("utc_offset_seconds") != 28800:
        raise ValueError("Weather source requires the Asia/Shanghai day boundary")
    days = [
        (start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)
    ]
    for kind, variables in (("daily", DAILY), ("hourly", HOURLY)):
        values, units = raw.get(kind, {}), raw.get(kind + "_units", {})
        expected_times = (
            days
            if kind == "daily"
            else [d + "T%02d:00" % hour for d in days for hour in range(24)]
        )
        if values.get("time") != expected_times:
            raise ValueError(
                "Weather source has missing, duplicate or misaligned timestamps"
            )
        for field, unit in variables.items():
            if (
                units.get(field) != unit
                or not isinstance(values.get(field), list)
                or len(values[field]) != len(expected_times)
            ):
                raise ValueError("Weather source units or array lengths differ")
            for value in values[field]:
                number(value)
                if (
                    field in {"temperature_2m", "dew_point_2m"}
                    and not -95 <= value <= 65
                ):
                    raise ValueError(
                        "Weather hourly temperatures are outside physical bounds"
                    )
    result = []
    for i, day in enumerate(days):
        daily = {name: number(raw["daily"][name][i]) for name in DAILY}
        means = {
            name: math.fsum(raw["hourly"][name][i * 24 : (i + 1) * 24]) / 24
            for name in HOURLY
        }
        temperatures = [
            daily["temperature_2m_min"],
            daily["temperature_2m_max"],
            means["temperature_2m"],
            means["dew_point_2m"],
        ]
        if (
            any(not -95 <= v <= 65 for v in temperatures)
            or temperatures[0] > temperatures[1]
        ):
            raise ValueError("Weather temperatures are outside physical bounds")
        if any(
            v < 0
            for name, v in daily.items()
            if name in {"precipitation_sum", "shortwave_radiation_sum"}
        ) or any(v < 0 for v in raw["hourly"]["wind_speed_10m"][i * 24 : (i + 1) * 24]):
            raise ValueError("Weather radiation, precipitation or wind is negative")
        dew = means["dew_point_2m"]
        result.append(
            {
                "business_date": day,
                "values": {
                    "temperature_minimum_daily": round(temperatures[0], 2),
                    "temperature_maximum_daily": round(temperatures[1], 2),
                    "temperature_mean_daily": round(means["temperature_2m"], 2),
                    "precipitation_daily": round(daily["precipitation_sum"], 2),
                    "solar_radiation_daily": round(
                        daily["shortwave_radiation_sum"] * 1000
                    ),
                    "wind_speed_2m_daily": round(
                        means["wind_speed_10m"] * 4.87 / math.log(67.8 * 10 - 5.42), 2
                    ),
                    "vapour_pressure_daily": round(
                        0.6108 * math.exp(17.27 * dew / (dew + 237.3)), 3
                    ),
                },
            }
        )
    return result


class OpenMeteoSource:
    """提供方通信与纯转换组合；接入凭据来自 Worker 装配。"""

    def __init__(
        self,
        session: ProviderSession,
        adapter: dict,
        api_key: str | None = None,
        access: str | None = None,
        endpoints: dict[str, str] | None = None,
    ):
        """注入固定网络会话、准确实现身份及可选商业订阅。"""
        self.session, self.adapter, self.api_key = session, adapter, api_key
        self.access = access
        defaults = SourceSettings.from_mapping({})
        self.endpoints = endpoints or {"archive": defaults.endpoint("MODARCHITECT_OPENMETEO_ARCHIVE_URL"), "customer": defaults.endpoint("MODARCHITECT_OPENMETEO_CUSTOMER_ARCHIVE_URL")}

    def acquire(
        self, entry: dict, binding: dict, request: AcquisitionRequest
    ) -> SourceSnapshot:
        """拉取历史原文并保留实际返回网格，未来或不完整历史资料拒绝。"""
        if self.access not in {"research", "subscription"}:
            raise ValueError(
                "Weather access purpose must be configured by the deployment"
            )
        if self.access == "subscription" and not self.api_key:
            raise ValueError("Weather subscription credentials are not configured")
        if (
            request.start_date < date(1940, 1, 1)
            or request.end_date >= instant().astimezone(timezone(timedelta(hours=8))).date()
        ):
            raise ValueError("Historical weather dates are outside the supported range")
        point = request.reference_point
        params = [
            ("latitude", str(point.latitude)),
            ("longitude", str(point.longitude)),
            ("start_date", request.start_date.isoformat()),
            ("end_date", request.end_date.isoformat()),
            ("timezone", "Asia/Shanghai"),
            ("temperature_unit", "celsius"),
            ("wind_speed_unit", "ms"),
            ("precipitation_unit", "mm"),
            ("daily", ",".join(DAILY)),
            ("hourly", ",".join(HOURLY)),
        ]
        endpoint = self.endpoints["archive"]
        if self.api_key:
            endpoint = self.endpoints["customer"]
            params.append(("apikey", self.api_key))
        body, evidence = self.session.get(endpoint, params)
        try:
            raw = json.loads(body)
        except (ValueError, UnicodeError) as exc:
            raise ValueError("Weather response is not valid JSON") from exc
        if not isinstance(raw, dict):
            raise ValueError("Weather response must be an object")
        grid = [number(raw.get("longitude")), number(raw.get("latitude"))]
        if not -180 <= grid[0] <= 180 or not -90 <= grid[1] <= 90:
            raise ValueError("Weather reference grid is invalid")
        rows = convert_weather(raw, request.start_date, request.end_date)
        variable = entry["variable"]
        code = variable["code"]
        table = ObservationTable.model_validate(
            {
                "columns": [
                    {
                        "code": code,
                        "name": variable["name"],
                        "unit": variable["unit"],
                        "value_kind": "estimated",
                    }
                ],
                "rows": [
                    {
                        **row,
                        "object": request.object.model_dump(),
                        "values": {code: row["values"][code]},
                    }
                    for row in rows
                ],
            }
        )
        return SourceSnapshot(
            binding=binding,
            adapter=self.adapter,
            request=request,
            observations=table,
            support={
                **entry["source"]["definition"]["support"],
                "requested_point": point.model_dump(),
                "grid_coordinates": grid,
                "elevation": number(raw.get("elevation")),
                "timezone": "Asia/Shanghai",
            },
            quality={
                "complete": True,
                "hourly_count_per_day": 24,
                "information_time": "unknown",
                "usage": "retrospective_or_given_factors",
                "license": "CC BY 4.0; Open-Meteo",
            },
            acquired_at=instant(),
            evidence=(evidence,),
        )
