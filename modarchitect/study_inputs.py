# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 14:45
# @Author  : Codex
# @File    : study_inputs.py
"""解释历史原生资料的指标级合同；说明内容不会授予系统来源资格。"""

from .catalog import catalog, research_request_schema

TEMPERATURE_NAMES = {"air_temperature": "空气温度", "canopy_temperature": "冠层温度"}
WEATHER_FIELDS = {
    "frost_exposure": [("tmin_c", "日最低气温", "celsius")],
    "heat_exposure": [("tmax_c", "日最高气温", "celsius")],
    "rainfall_deficit": [("precipitation_mm", "日降水量", "mm")],
    "rainfall_excess": [("precipitation_mm", "日降水量", "mm")],
    "warm_humid_disease": [
        ("tmean_c", "日平均气温", "celsius"),
        ("precipitation_mm", "日降水量", "mm"),
        ("vpd_kpa", "日饱和水汽压差（VPD）", "kpa"),
    ],
}
GREENHOUSE_FIELDS = {
    "air_temperature_c": ("温室日气温", "celsius", "input"),
    "net_radiation_mj_m2_d": ("日净辐射", "MJ/(m²·d)", "input"),
    "ground_heat_flux_mj_m2_d": ("日土壤热通量", "MJ/(m²·d)", "input"),
    "vapor_pressure_deficit_kpa": ("饱和水汽压差（VPD）", "kpa", "input"),
    "saturation_slope_kpa_per_c": ("饱和水汽压曲线斜率", "kPa/°C", "parameter"),
    "psychrometric_constant_kpa_per_c": ("湿度计常数", "kPa/°C", "parameter"),
}


def descriptor(
    code: str,
    name: str,
    unit: str,
    use: str,
    *,
    kind: str = "input",
    source: str = "指定方法示例",
) -> dict:
    """只输出用户理解输入所需字段，不返回原始数值、凭据和业务对象。"""
    return {
        "code": code,
        "name": name,
        "unit": unit,
        "use": use,
        "kind": kind,
        "source": source,
    }


def native_input_requirements(row: dict) -> list[dict]:
    """从准确原生请求、指标选项和资料字段投影，不以中文同名生成目录绑定。"""
    definition = row["definition"]
    if "bundle_sha256" not in row:
        return []
    result = []
    options = {item["code"]: item for item in row.get("indicator_options", [])}
    for recipe in definition["input_recipes"].values():
        if recipe["kind"] != "configuration":
            continue
        value = recipe["value"]
        if value.get("rule") in WEATHER_FIELDS:
            for code, name, unit in WEATHER_FIELDS[value["rule"]]:
                result.append(
                    descriptor(
                        code,
                        name,
                        unit,
                        "条件分析输入",
                        source="既有气象示例资料，尚未绑定当前地块来源",
                    )
                )
        for code in value.get("variables", []):
            if code in options:
                option = options[code]
                nature = (
                    "准确模拟成果"
                    if option["value_kind"] == "simulated"
                    else "既有分析示例"
                )
                result.append(
                    descriptor(
                        code, option["name"], option["unit"], "分析指标", source=nature
                    )
                )
    bundles = row.get("bundles", {})
    dataset = bundles.get("dataset")
    if (
        isinstance(dataset, dict)
        and isinstance(dataset.get("features"), list)
        and isinstance(dataset.get("target"), dict)
    ):
        for feature in dataset["features"]:
            result.append(
                descriptor(
                    feature["code"],
                    TEMPERATURE_NAMES.get(feature["code"], feature["code"]),
                    feature["unit"],
                    "训练因素",
                    source="合成方法示例（不代表真实观测）",
                )
            )
        target = dataset["target"]
        result.append(
            descriptor(
                target["code"],
                TEMPERATURE_NAMES.get(target["code"], target["code"]),
                target["unit"],
                "训练与留出评价目标",
                source="合成方法示例（不代表真实观测）",
            )
        )
    for port, value in bundles.items():
        if not isinstance(value, dict):
            continue
        node = next(
            (
                n
                for n in definition["composition"]["nodes"]
                if any(
                    b["source"].get("node") is None and b["source"]["port"] == port
                    for b in n["bindings"]
                )
            ),
            None,
        )
        schema = (
            research_request_schema(
                catalog()[
                    node["component"]["code"], node["component"]["revision"]
                ].definition
            )
            if node
            else None
        )
        for code, (name, unit, kind) in GREENHOUSE_FIELDS.items():
            if code in value and schema and code in schema.get("properties", {}):
                result.append(
                    descriptor(
                        code,
                        name,
                        unit,
                        "方法参数" if kind == "parameter" else "耗水估算输入",
                        kind=kind,
                        source="温室合成示例，不能用室外日值直接替代",
                    )
                )
        if "hours" in value:
            for code, name in [
                ("start_mass_g", "每小时初始质量"),
                ("end_mass_g", "每小时结束质量"),
                ("irrigation_g", "每小时灌溉质量"),
                ("drainage_g", "每小时排水质量"),
            ]:
                if value["hours"] and code in value["hours"][0]:
                    result.append(
                        descriptor(
                            code,
                            name,
                            "g",
                            "完整24小时称重水量平衡",
                            source="温室称重合成示例",
                        )
                    )
            result.append(
                descriptor(
                    "substrate_evaporation",
                    "基质蒸发分离证据",
                    "g",
                    "蒸腾估算的可选证据",
                    source="示例记录；缺证据不输出蒸腾分离结果",
                )
            )
        if "kc" in value:
            result.append(
                descriptor("kc", "阶段作物系数", "1", "方法参数", kind="parameter")
            )
            result.append(
                descriptor(
                    "ground_area_m2",
                    "栽培地面面积",
                    "m²",
                    "称重与单位面积耗水换算",
                    source="准确栽培单元范围",
                )
            )
    if not result:
        for port in definition["composition"]["inputs"]:
            recipe = definition["input_recipes"][port["code"]]
            if recipe["kind"] == "artifact":
                result.append(
                    descriptor(
                        port["code"],
                        port["name"],
                        "原生合同",
                        "尚缺指标级说明，不能作为普通真实研究",
                        source="历史专用资料",
                    )
                )
    return result
