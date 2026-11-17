# -*- coding: utf-8 -*-
# @Time    : 2026/11/9 18:22
# @Author  : feidu
# @File    : greenhouse_water_balance_file.py
"""以冻结的称重、灌溉和排液求温室一小时水量平衡参照。"""

from argparse import ArgumentParser
from math import fsum
from pathlib import Path
import sys

from mlgrowth_contracts.model_center.components import ComponentReference
from mlgrowth_contracts.model_center.greenhouse_water_balance import (
    WeighingWaterBalance,
    WeighingWaterBalanceReference,
)

from .file_protocol import read_invocation, write_result

_COMPONENT = ComponentReference(code="greenhouse_weighing_water_balance", revision=1)


def estimate_water_balance(
    sample: WeighingWaterBalance,
) -> WeighingWaterBalanceReference:
    """减去实际质量增量；恰好一小时，质量差的数值即平均通量。"""
    evapotranspiration = fsum(
        (
            sample.irrigation_g,
            -sample.drainage_g,
            sample.start_mass_g,
            -sample.end_mass_g,
        )
    )
    evaporation = sample.substrate_evaporation
    # 蒸发来源未知时保留空值；负通量由结果合同拒绝，避免生成假零参照。
    return WeighingWaterBalanceReference(
        scope=sample.scope,
        evidence_sha256=sample.evidence_sha256,
        evapotranspiration_g_h=evapotranspiration,
        substrate_evaporation=evaporation,
        transpiration_g_h=(
            evapotranspiration - evaporation.mass_g if evaporation is not None else None
        ),
    )


def run(input_dir: Path, output_dir: Path) -> None:
    """通过文件协议核验输入并写出一个已计算的参照成果。"""
    invocation, inputs = read_invocation(input_dir, _COMPONENT, {"weighing"})
    sample = WeighingWaterBalance.model_validate(inputs["weighing"])
    result = estimate_water_balance(sample)
    write_result(output_dir, invocation, {"reference": result.model_dump(mode="json")})


def main() -> int:
    parser = ArgumentParser(description="Estimate greenhouse weighing water balance")
    parser.add_argument("--input-dir", type=Path, default=Path("/work/input"))
    parser.add_argument("--output-dir", type=Path, default=Path("/work/output"))
    args = parser.parse_args()
    try:
        run(args.input_dir, args.output_dir)
    except (OSError, ValueError, OverflowError):
        print("Greenhouse weighing water balance invocation failed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
