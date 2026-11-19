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
    port: str,
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
        "port": port,
        "code": code,
        "name": name,
        "unit": unit,
        "use": use,
        "kind": kind,
        "source": source,
    }


def _dataset(port: str, value: dict) -> list[dict]:
    """区分样例因素和真实研究中应提供的目标，保持二者所属数据包。"""
    return [
        descriptor(
            port,
            item["code"],
            TEMPERATURE_NAMES.get(item["code"], item["code"]),
            item["unit"],
            use,
            kind=kind,
            source="合成方法示例",
        )
        for kind, use, columns in (
            ("input", "训练因素", value["features"]),
            ("target", "训练与留出评价目标", [value["target"]]),
        )
        for item in columns
    ]


def _weighing(port: str, value: dict) -> list[dict]:
    """面积与可选证据来自小时称重，保留实际采样尺度。"""
    hours = value["hours"]
    fields = [
        ("start_mass_g", "每小时初始质量"),
        ("end_mass_g", "每小时结束质量"),
        ("irrigation_g", "每小时灌溉质量"),
        ("drainage_g", "每小时排水质量"),
    ]
    result = [
        descriptor(
            port, code, name, "g", "24 小时称重水量平衡", source="温室称重合成示例"
        )
        for code, name in fields
        if hours and code in hours[0]
    ]
    if hours and "ground_area_m2" in hours[0].get("scope", {}):
        result.append(
            descriptor(
                port,
                "ground_area_m2",
                "栽培地面面积",
                "m²",
                "称重与单位面积耗水换算",
                source="示例栽培单元",
            )
        )
    result.append(
        descriptor(
            port,
            "substrate_evaporation",
            "基质蒸发分离证据",
            "g",
            "分离蒸腾的可选证据",
            source="温室称重合成示例",
        )
    )
    return result


def _request_items(
    port: str, semantic: str, value: dict, properties: dict
) -> list[dict]:
    """展示同一准确参数合同的字段标题，避免返回案例数值和证据标识。"""
    if semantic == "greenhouse_day_weather":
        return [
            descriptor(
                port,
                code,
                name,
                unit,
                "方法参数" if kind == "parameter" else "耗水估算输入",
                kind=kind,
                source="温室合成示例",
            )
            for code, (name, unit, kind) in GREENHOUSE_FIELDS.items()
            if code in value and code in properties
        ]
    if semantic == "greenhouse_crop_coefficient" and "kc" in value:
        return [
            descriptor(
                port,
                "kc",
                "阶段作物系数",
                "1",
                "方法参数",
                kind="parameter",
                source="指定示例作物系数",
            )
        ]
    return [
        descriptor(port, code, field["title"], "", "随指定资料提供", kind="parameter")
        for code, field in properties.items()
        if code in value and field.get("title")
    ]


def native_input_requirements(row: dict) -> list[dict]:
    """按外部资料端口投影准确指标、参数与用途，原文和数值留在服务端。"""
    if "bundle_sha256" not in row:
        return []
    definition = row["definition"]
    recipes = definition["input_recipes"]
    options = row.get("indicator_options", [])
    result = []
    for port in definition["composition"]["inputs"]:
        code, semantic = port["code"], port["data_type"]["semantic"]
        recipe = recipes[code]
        if recipe["kind"] != "artifact":
            continue
        value = row.get("bundles", {}).get(recipe["artifact_output"], {})
        items = []
        for node in definition["composition"]["nodes"]:
            external = {
                binding["port"]: binding["source"]["port"]
                for binding in node["bindings"]
                if binding["source"].get("node") is None
            }
            if code not in external.values():
                continue
            if external.get("weather") == code:
                request = recipes.get(external.get("request"), {}).get("value", {})
                items.extend(
                    descriptor(
                        code, key, name, unit, "条件分析输入", source="指定气象资料"
                    )
                    for key, name, unit in WEATHER_FIELDS.get(request.get("rule"), [])
                )
            elif external.get("series") == code:
                items.extend(
                    descriptor(
                        code,
                        item["code"],
                        item["name"],
                        item["unit"],
                        "分析指标",
                        source="指定模拟成果"
                        if item["value_kind"] == "simulated"
                        else "指定分析资料",
                    )
                    for item in options
                )
            elif (
                external.get("dataset") == code
                and isinstance(value.get("features"), list)
                and isinstance(value.get("target"), dict)
            ):
                items.extend(_dataset(code, value))
            elif external.get("request") == code:
                component = node["component"]
                contract = catalog()[
                    component["code"], component["revision"]
                ].definition
                properties = (research_request_schema(contract) or {}).get(
                    "properties", {}
                )
                items.extend(
                    _weighing(code, value)
                    if semantic == "greenhouse_weighing_day_request"
                    and "hours" in value
                    else _request_items(code, semantic, value, properties)
                )
        result.extend(
            {item["code"]: item for item in items}.values()
            if items
            else [
                descriptor(
                    code,
                    code,
                    port["name"],
                    "原生合同",
                    "按资料组提供",
                    source="指定研究资料",
                )
            ]
        )
    return result
