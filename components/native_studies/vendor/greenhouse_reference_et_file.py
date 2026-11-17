# -*- coding: utf-8 -*-
# @Time    : 2026/11/9 18:14
# @Author  : feidu
# @File    : greenhouse_reference_et_file.py
"""独立计算 Qiu 等勘误式的温室日参考蒸散。"""

from argparse import ArgumentParser
from math import isfinite
from pathlib import Path
import sys

from mlgrowth_contracts.model_center.components import ComponentReference
from mlgrowth_contracts.model_center.greenhouse_reference_et import (
    GreenhouseDayWeather,
    GreenhouseReferenceET,
)

from .file_protocol import read_invocation, write_result

_COMPONENT = ComponentReference(code="greenhouse_reference_et_daily", revision=1)


def estimate_reference_et(weather: GreenhouseDayWeather) -> GreenhouseReferenceET:
    """输出 mm/d。式 5 固定空气动力学阻力 295 s/m，适用于弱风日光温室。"""
    slope = weather.saturation_slope_kpa_per_c
    gamma = weather.psychrometric_constant_kpa_per_c
    net_energy = weather.net_radiation_mj_m2_d - weather.ground_heat_flux_mj_m2_d
    radiation_term = 0.408 * slope * net_energy
    aerodynamic_term = (
        gamma
        * (628 / (weather.air_temperature_c + 273))
        * weather.vapor_pressure_deficit_kpa
    )
    denominator = slope + 1.24 * gamma
    if not isfinite(denominator):
        raise ValueError("Greenhouse reference ET denominator is out of range")
    # 负值超出本候选的输出约定，不用截零掩盖输入条件。
    return GreenhouseReferenceET(
        scope=weather.scope,
        reference_et_mm_d=(radiation_term + aerodynamic_term) / denominator,
    )


def run(input_dir: Path, output_dir: Path) -> None:
    """按文件协议校验冻结输入，写出可核对的参考蒸散结果。"""
    invocation, inputs = read_invocation(input_dir, _COMPONENT, {"weather"})
    weather = GreenhouseDayWeather.model_validate(inputs["weather"])
    result = estimate_reference_et(weather)
    write_result(
        output_dir, invocation, {"reference_et": result.model_dump(mode="json")}
    )


def main() -> int:
    parser = ArgumentParser(description="Estimate daily greenhouse reference ET")
    parser.add_argument("--input-dir", type=Path, default=Path("/work/input"))
    parser.add_argument("--output-dir", type=Path, default=Path("/work/output"))
    args = parser.parse_args()
    try:
        run(args.input_dir, args.output_dir)
    except (OSError, ValueError, OverflowError):
        print("Greenhouse reference ET invocation failed", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
