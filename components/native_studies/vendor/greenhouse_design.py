# -*- coding: utf-8 -*-
# @Time    : 2026/11/10 11:18
# @Author  : feidu
# @File    : greenhouse_design.py
"""设计器使用现有温室内核，整日节点保留每小时成果和称重证据。"""

from datetime import time, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import Field

from mlgrowth_contracts.model_center.components import Contract
from mlgrowth_contracts.model_center.greenhouse_crop_et_comparison import (
    FrozenCropCoefficient,
    WeighingCropETDay,
)
from mlgrowth_contracts.model_center.greenhouse_reference_et import (
    GreenhouseDayWeather,
    GreenhouseReferenceET,
)
from mlgrowth_contracts.model_center.greenhouse_water_balance import (
    WeighingWaterBalance,
)
from mlgrowth_contracts.model_center.outputs import (
    OutputProductReference,
    StandardResearchOutput,
)
from mlgrowth_contracts.model_center.research import Sha256

from .greenhouse_crop_et_comparison_file import compare_crop_et
from .greenhouse_reference_et_file import estimate_reference_et
from .greenhouse_water_balance_file import estimate_water_balance


class GreenhouseWeighingDayRequest(Contract):
    """24 个原始小时窗口与单独冻结的供水证据。"""

    hours: Annotated[
        tuple[WeighingWaterBalance, ...], Field(min_length=24, max_length=24)
    ]
    non_stressed_water_evidence_sha256: Sha256


def _product(code: str, result: Contract) -> StandardResearchOutput:
    return StandardResearchOutput(
        product=OutputProductReference(code=code, definition_version="1.0.0"),
        payload={"schema_version": "1.0", **result.model_dump(mode="json")},
    )


def reference_et_node(request: dict) -> StandardResearchOutput:
    """保留日参考蒸散及其公式、温室和日界。"""
    result = estimate_reference_et(GreenhouseDayWeather.model_validate(request))
    return _product("greenhouse_reference_et", result)


def weighing_day_node(request: dict) -> StandardResearchOutput:
    """一个设计节点计算同一栽培单元的整日小时估算，拒绝错位或不完整日。"""
    batch = GreenhouseWeighingDayRequest.model_validate(request)
    hours = sorted(batch.hours, key=lambda row: row.scope.started_at)
    first = hours[0].scope
    start = first.started_at.astimezone(ZoneInfo("Asia/Shanghai"))
    if start.time() != time.min or any(
        row.scope.started_at != start + timedelta(hours=index)
        or row.scope.greenhouse_ref != first.greenhouse_ref
        or row.scope.cultivation_unit_ref != first.cultivation_unit_ref
        or row.scope.season_ref != first.season_ref
        or row.scope.ground_area_m2 != first.ground_area_m2
        for index, row in enumerate(hours)
    ):
        raise ValueError(
            "Weighing samples must cover one complete scoped greenhouse day"
        )
    result = WeighingCropETDay(
        hours=tuple(estimate_water_balance(row) for row in hours),
        non_stressed_water_evidence_sha256=batch.non_stressed_water_evidence_sha256,
    )
    return _product("greenhouse_weighing_crop_et_day", result)


def crop_et_comparison_node(
    request: dict,
    reference_et: StandardResearchOutput,
    weighing_day: StandardResearchOutput,
) -> StandardResearchOutput:
    """从两项上游结果与准确 Kc 形成日蒸散对照。"""
    if (
        reference_et.product.code != "greenhouse_reference_et"
        or weighing_day.product.code != "greenhouse_weighing_crop_et_day"
        or reference_et.product.definition_version != "1.0.0"
        or weighing_day.product.definition_version != "1.0.0"
    ):
        raise ValueError("Greenhouse comparison requires the frozen upstream products")
    result = compare_crop_et(
        GreenhouseReferenceET.model_validate(
            {k: v for k, v in reference_et.payload.items() if k != "schema_version"}
        ),
        FrozenCropCoefficient.model_validate(request),
        WeighingCropETDay.model_validate(
            {k: v for k, v in weighing_day.payload.items() if k != "schema_version"}
        ),
    )
    return _product("greenhouse_crop_et_comparison", result)
