# -*- coding: utf-8 -*-
# @Time    : 2026/11/9 18:38
# @Author  : feidu
# @File    : greenhouse_crop_et_comparison_file.py
"""同日作物蒸散估算与完整称重水量平衡的独立对照入口。"""

from argparse import ArgumentParser
from datetime import datetime, time, timedelta, timezone
from math import fsum
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from mlgrowth_contracts.model_center.components import ComponentReference
from mlgrowth_contracts.model_center.greenhouse_crop_et_comparison import (
    FrozenCropCoefficient,
    GreenhouseCropETComparison,
    WeighingCropETDay,
)
from mlgrowth_contracts.model_center.greenhouse_reference_et import (
    GreenhouseReferenceET,
)

from .file_protocol import read_invocation, write_result

_COMPONENT = ComponentReference(code="greenhouse_crop_et_daily_comparison", revision=1)
_PORTS = {"reference_et", "coefficient", "weighing_day"}
_HOUR = timedelta(hours=1)


def compare_crop_et(
    reference: GreenhouseReferenceET,
    coefficient: FrozenCropCoefficient,
    weighing: WeighingCropETDay,
) -> GreenhouseCropETComparison:
    """比较同一有效日的 ET₀×Kc 与称重作物蒸散，拒绝拼接不完整的时段。"""
    day = reference.scope.business_date
    zone = ZoneInfo(reference.scope.timezone)
    start = datetime.combine(day, time.min, zone).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(
        timezone.utc
    )
    if reference.scope != coefficient.scope or coefficient.frozen_at > start:
        raise ValueError("Crop coefficient is not frozen for the reference ET day")
    if end - start != 24 * _HOUR:
        raise ValueError("Crop ET comparison requires a 24-hour business day")

    hours = sorted(weighing.hours, key=lambda row: row.scope.started_at)
    area = hours[0].scope.ground_area_m2
    for index, row in enumerate(hours):
        scope = row.scope
        if (
            scope.started_at != start + index * _HOUR
            or scope.greenhouse_ref != reference.scope.greenhouse_ref
            or scope.cultivation_unit_ref != coefficient.cultivation_unit_ref
            or scope.season_ref != coefficient.season_ref
            or scope.ground_area_m2 != area
        ):
            raise ValueError("Weighing hours differ from the day or cultivation scope")

    # 每条记录为恰好一小时的平均 g/h。1 kg 水约为 1 L，1 L/m² 为 1 mm。
    weighing_mm = fsum(row.evapotranspiration_g_h for row in hours) / 1000 / area
    estimated_mm = reference.reference_et_mm_d * coefficient.kc
    return GreenhouseCropETComparison(
        coefficient=coefficient,
        ground_area_m2=area,
        estimated_crop_et_mm_d=estimated_mm,
        weighing_crop_et_mm_d=weighing_mm,
        difference_mm_d=estimated_mm - weighing_mm,
    )


def run(input_dir: Path, output_dir: Path) -> None:
    invocation, inputs = read_invocation(input_dir, _COMPONENT, _PORTS)
    result = compare_crop_et(
        GreenhouseReferenceET.model_validate(inputs["reference_et"]),
        FrozenCropCoefficient.model_validate(inputs["coefficient"]),
        WeighingCropETDay.model_validate(inputs["weighing_day"]),
    )
    write_result(output_dir, invocation, {"comparison": result.model_dump(mode="json")})


def main() -> int:
    parser = ArgumentParser(description="Compare daily greenhouse crop ET")
    parser.add_argument("--input-dir", type=Path, default=Path("/work/input"))
    parser.add_argument("--output-dir", type=Path, default=Path("/work/output"))
    args = parser.parse_args()
    try:
        run(args.input_dir, args.output_dir)
    except (OSError, ValueError, OverflowError):
        print("Greenhouse crop ET comparison invocation failed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
