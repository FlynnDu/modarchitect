# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 01:01
# @Author  : Codex
# @File    : system_inputs.py
"""集中管理系统输入定义、固定来源、设计采用和运行来源证据。"""

from copy import deepcopy
from functools import lru_cache
from importlib.resources import files
import json

from jsonschema import Draft202012Validator

from .contracts.identifiers import identity_sha256
from .contracts.research.catalog_bindings import source_selection_schema
from .contracts.research.plans import CollectionRequirement
from .contracts.research.variables import Variable
from .input_sources.contracts import SourceSnapshot, match_snapshots, source_registration
from .input_taxonomy import category_names, classified_catalog
from .contracts.violations import ContractViolation

_SOURCE_NAMES = {
    "manual": "标准人工记录",
    "openmeteo_weather": "Open-Meteo 天气",
    "soilgrids_reference_normalization": "SoilGrids 单位与网格参考适配",
    "growth_trend_analysis": "平台长势分析记录",
    "sentinelhub_s2_l2a_reference": "Sentinel-2 L2A单景反射率参考",
}


@lru_cache(maxsize=1)
def _snapshot() -> dict:
    """读取随安装包发布的准确制品，损坏时拒绝而不回退旧库。"""
    resource = files("modarchitect.contracts").joinpath("system-inputs-v1.json")
    envelope = json.loads(resource.read_text(encoding="utf-8"))
    if identity_sha256(envelope["payload"]) != envelope["sha256"]:
        raise ValueError("System input catalog checksum differs")
    return envelope


@lru_cache(maxsize=1)
def _history() -> tuple[dict, ...]:
    """加载安装包保留的准确来源历史，不按最新版本覆盖已发布绑定。"""
    result = []
    for resource in files("modarchitect.contracts").iterdir():
        if resource.name.startswith("system-inputs-v") and resource.name.endswith(".json"):
            envelope = json.loads(resource.read_text(encoding="utf-8"))
            if identity_sha256(envelope["payload"]) != envelope["sha256"]:
                raise ValueError("Historical system input checksum differs")
            result.append(envelope)
    return tuple(result)


def _manual_method(description: str) -> dict:
    """登记本项目标准人工记录通道，不冒充业务系统已同步的记录。"""
    return {
        "protocol_code": "system_manual_record", "protocol_version": "1.0.0",
        "method_code": "standard_manual_entry", "instructions": description,
        "evidence_required": True,
    }


def _entry(raw: dict, kind: str, category: str, unit_kind: str | None,
           source: dict | None = None, policy: dict | None = None) -> dict:
    """从准确本体和来源构造单一目录投影，不复制用户可修改的定义。"""
    variable = {
        "code": raw["code"], "definition_version": raw["definition_version"],
        "name": raw["name"], "description": raw["description"],
        "value_type": "number", "unit": raw["unit"], "role": "covariate",
        "minimum": raw["bounds"].get("minimum"),
        "maximum": raw["bounds"].get("maximum"),
    }
    source_code = "manual" if category == "manual" else (
        source["component"]["code"] if source else (
            "growth_trend_analysis" if category == "platform_analysis" else None
        )
    )
    binding_raw = source or raw
    planned = category in {"platform_analysis", "iot_platform"}
    if planned and unit_kind is None:
        unit_kind = "report_area"
    if category == "iot_platform":
        source_code = "iot_platform"
    binding = {
        "kind": kind, "code": binding_raw["code"],
        "definition_version": binding_raw["definition_version"],
        "contract_sha256": identity_sha256(binding_raw),
        "value_nature": "observed" if category in {"manual", "iot_platform"} else "estimated" if planned else source["value_nature"],
        "source_system": None if category == "manual" else source_code,
        "selectors": {},
    }
    method = policy["method"] if policy else _manual_method(raw["description"]) if category == "manual" else None
    if planned:
        binding.update(kind="planned_source", contract_sha256=identity_sha256({"definition": raw, "category": category, "unit_kind": unit_kind, "source_system": source_code}))
        method = {"protocol_code": "planned_platform_input", "protocol_version": "1.0.0", "method_code": source_code,
                  "instructions": raw["description"], "evidence_required": True}
    reason = None
    if category == "platform_analysis":
        reason = "尚未完成报告/影像范围、日期与授权取数绑定，不能作为已接通输入。"
    elif category == "iot_platform":
        reason = "尚未登记供应商、设备、点位及同步通道。"
    elif unit_kind != "field_season":
        reason = "当前数值表仅支持地块种植季；此输入需要明确的点位、单株或样方适配。"
    elif category == "third_party" and source_registration(binding) is None:
        reason = "准确来源尚未登记接入实现。"
    return {
        "key": "%s:%s@%s" % (kind, raw["code"], raw["definition_version"]),
        "variable": variable, "category": category, "unit_kind": unit_kind,
        "selectable": True,
        "source": {"code": source_code,
                   "name": _SOURCE_NAMES.get(source_code, "物联网监测（待接入）" if category == "iot_platform" else source_code),
                   "binding": binding, "definition": source,
                   "policy": policy,
                   "selection_schema": source_selection_schema(source["selectors"] if source else {}),
                   "method": method},
        "execution": {"available": reason is None, "reason": reason,
                      "channel": ("source_snapshot" if category == "third_party" else "workspace_manual_entry") if reason is None else None},
        "data_available": None,
    }


def _catalog(envelope: dict) -> dict:
    """解释一份准确目录；禁止同一采用目录中出现含糊的指标入口。"""
    payload = envelope["payload"]
    variables = {(v["code"], v["definition_version"]): v for v in payload["variables"]}
    sources = {(s["code"], s["definition_version"]): s for s in payload["sources"]}
    items = []
    for record in payload["sampling"]:
        raw = {"code": record["code"], "definition_version": record["definition_version"],
               "name": record["name_zh"], "description": record["description_zh"],
               "unit": record["unit_code"],
               "bounds": {"minimum": record["valid_min"], "maximum": record["valid_max"]}}
        entry = _entry(raw, "sampling_indicator", "manual",
                       "point" if raw["code"] == "height_cm" else "field_season")
        entry["source"]["binding"]["contract_sha256"] = identity_sha256(record)
        items.append(entry)
    for profile in payload["profiles"]:
        if profile["source"] in {"manual", "instrument"}:
            items.append(_entry(profile["variable"], "research_variable",
                                "manual" if profile["source"] == "manual" else "iot_platform",
                                profile["unit_kind"]))
    for policy in payload["policies"]:
        ref = policy["source"]
        source = sources[ref["code"], ref["definition_version"]]
        ref = source["variable"]
        items.append(_entry(variables[ref["code"], ref["definition_version"]],
                            "variable_source", "third_party", source["support"]["unit_kind"],
                            source, policy))
    for raw in payload["variables"]:
        if raw["group"] in {"growth_trend_report", "growth_trend_point"}:
            if raw["code"].startswith("growth_report_ndvi_") and raw["code"].endswith(("_area", "_percent")):
                continue
            items.append(_entry(raw, "research_variable", "platform_analysis",
                                "point" if raw["group"] == "growth_trend_point" else None))
    if len({item["key"] for item in items}) != len(items):
        raise ValueError("Adopted input keys must be unambiguous")
    return {
        "version": payload["version"], "sha256": envelope["sha256"],
        "categories": [{"code": code, "name": name,
                        "count": sum(i["category"] == code for i in items)}
                       for code, name in category_names().items()],
        "items": items, "total": len(items),
    }


def input_catalog() -> dict:
    """只投影当前采用的目录，历史解析不依赖这个可变选择。"""
    return classified_catalog(_catalog(_snapshot()))


@lru_cache(maxsize=1)
def _historical_catalog_entries() -> tuple[dict, ...]:
    """固定安装包只投影一次历史目录，每次解析仍按准确来源身份匹配。"""
    return tuple(entry for envelope in _history() for entry in _catalog(envelope)["items"])


def resolve_input(binding: dict, method: dict | None = None) -> dict:
    """按准确身份解析历史来源；摘要冲突、缺失或伪造来源均拒绝。"""
    matches = []
    for entry in _historical_catalog_entries():
        expected = entry["source"]["binding"]
        if expected and (method is None or entry["source"]["method"] == method) and all(expected[k] == binding.get(k) for k in (
            "kind", "code", "definition_version", "contract_sha256"
        )):
            matches.append(entry)
    def scientific_contract(entry: dict) -> dict:
        """采用策略的展示版本不参与准确来源科学身份。"""
        result = deepcopy(entry)
        result["source"].pop("policy")
        return result
    if not matches or any(scientific_contract(entry) != scientific_contract(matches[0]) for entry in matches[1:]):
        raise ValueError("System input identity or exact source checksum differs")
    return deepcopy(matches[0])


def configure_input(key: str, selectors: dict, role: str = "covariate", *, required_for: tuple[str, ...] = ("train",)) -> dict:
    """按精确目录生成变量与采集要求，所有来源属性必须显式符合 Schema。"""
    entry = next((i for i in input_catalog()["items"] if i["key"] == key), None)
    if entry is None or not entry["selectable"]:
        raise ValueError("System input is not available for selection")
    return _configure(entry, selectors, role, required_for=required_for)


def _configure(entry: dict, selectors: dict, role: str, *, required_for: tuple[str, ...] = ("train",)) -> dict:
    """按给定准确来源配置，历史验证不重新采用当前来源。"""
    if not Draft202012Validator(entry["source"]["selection_schema"]).is_valid(selectors):
        raise ValueError("System input requires its exact registered source selectors")
    variable = Variable.model_validate({**entry["variable"], "role": role})
    binding = {**entry["source"]["binding"], "selectors": selectors}
    if role in {"target", "validation"} and binding["value_nature"] != "observed":
        raise ValueError("Research targets require observed measurement sources")
    requirement = CollectionRequirement(
        code=variable.code, variable_code=variable.code,
        method=entry["source"]["method"], unit_kind=entry["unit_kind"],
        requires_sampling_points=entry["unit_kind"] == "point",
        required_for=required_for,
        source="manual" if entry["category"] == "manual" else "business_system" if entry["category"] in {"platform_analysis", "iot_platform"} else "third_party",
        catalog_binding=binding, minimum_observations_per_unit=1,
        minimum_independent_units=1,
    )
    return {"variable": variable.model_dump(mode="json"),
            "requirement": requirement.model_dump(mode="json"),
            "entry": entry}


def validate_input_bindings(definition: dict, *, require_catalog: bool = False) -> None:
    """对所有调用方核验固定定义，普通新运行拒绝私有外部输入。"""
    current_design = definition.get("schema_version") == "1.5"
    raw_variables = definition.get("variables", [])
    requirements = definition.get("collection_requirements", [])
    if not isinstance(raw_variables, list) or not isinstance(requirements, list):
        raise ValueError("System input variables and requirements must be arrays")
    if any(not isinstance(v, dict) or not isinstance(v.get("code"), str) for v in raw_variables):
        raise ValueError("System input variable identity is invalid")
    variables = {v["code"]: v for v in raw_variables}
    if len(variables) != len(raw_variables):
        raise ValueError("System input variable identities must be unique")
    bound_codes = set()
    for index, raw in enumerate(requirements):
        requirement = CollectionRequirement.model_validate(raw)
        binding = requirement.catalog_binding
        if binding is None:
            if require_catalog or current_design:
                raise ContractViolation(
                    "Select external inputs from the system input catalog",
                    ["collection_requirements", index, "catalog_binding"],
                    "unregistered_indicator",
                )
            continue
        try:
            entry = resolve_input(binding.model_dump(mode="json"), requirement.method.model_dump(mode="json"))
        except ValueError as exc:
            raise ContractViolation(str(exc), ["collection_requirements", index, "catalog_binding"], "invalid_source") from exc
        if requirement.variable_code not in variables:
            raise ValueError("System input requirement references an unknown variable")
        if requirement.variable_code in bound_codes:
            raise ValueError("An external variable requires one unambiguous source binding")
        variable = Variable.model_validate(variables[requirement.variable_code])
        try:
            expected = _configure(entry, binding.selectors, variable.role)
        except ValueError as exc:
            raise ContractViolation(str(exc), ["collection_requirements", index, "catalog_binding"], "invalid_source") from exc
        expected_variable = expected["variable"]
        actual_variable = variable.model_dump(mode="json")
        if not current_design:
            for field in ("minimum", "maximum"):
                standard, chosen = expected_variable[field], actual_variable[field]
                if standard is not None and (chosen is None or (
                    chosen < standard if field == "minimum" else chosen > standard
                )):
                    raise ValueError("System input cannot loosen its scientific bounds")
                expected_variable[field] = chosen
        if actual_variable != expected_variable:
            field = next(key for key in expected_variable if actual_variable.get(key) != expected_variable[key])
            variable_index = next(i for i, item in enumerate(raw_variables) if item["code"] == variable.code)
            raise ContractViolation("System input definition, name or unit differs: %s" % variable.code, ["variables", variable_index, field], "invalid_indicator")
        for field in ("source", "unit_kind", "method", "catalog_binding"):
            if requirement.model_dump(mode="json")[field] != expected["requirement"][field]:
                raise ContractViolation("System input source, support or method cannot be overridden: %s" % variable.code, ["collection_requirements", index, field], "invalid_source")
        bound_codes.add(variable.code)
    if require_catalog:
        recipes = definition.get("input_recipes", {})
        if not isinstance(recipes, dict) or any(not isinstance(r, dict) for r in recipes.values()):
            raise ValueError("System input recipes must be objects")
        codes = [r.get("variable_codes", []) for r in recipes.values() if r.get("kind") == "observations"]
        if any(not isinstance(values, list) or any(not isinstance(c, str) for c in values) for values in codes):
            raise ValueError("System observation input codes must be string arrays")
        external = {c for values in codes for c in values}
        if not external <= bound_codes:
            raise ValueError("Every external observation requires a system input binding")


def validate_input_adoption(definition: dict, retained_definition: dict | None = None) -> None:
    """新采用只用当前批准来源；可信既有方案可保留准确原绑定供独立执行门禁检查。"""
    def token(requirement: dict) -> str:
        """来源、属性与方法共同决定一次采用，角色和显示文本不改变来源。"""
        return identity_sha256({k: requirement.get(k) for k in ("variable_code", "catalog_binding", "method")})
    retained = {token(r) for r in (retained_definition or {}).get("collection_requirements", []) if r.get("catalog_binding")}
    current = input_catalog()["items"]
    for requirement in definition.get("collection_requirements", []):
        binding = requirement.get("catalog_binding")
        if binding is None or token(requirement) in retained:
            continue
        entry = next((e for e in current if e["source"]["binding"] and all(
            e["source"]["binding"][k] == binding.get(k) for k in ("kind", "code", "definition_version", "contract_sha256")
        ) and e["source"]["method"] == requirement["method"]), None)
        if entry is None:
            raise ValueError("Source is available for historical interpretation, not new adoption")


def input_readiness(definition: dict) -> list[dict]:
    """说明每一项取数位置与阻断条件，不执行网络请求或假装已有数据。"""
    result = []
    for requirement in definition.get("collection_requirements", []):
        binding = requirement.get("catalog_binding")
        entry = resolve_input(binding, requirement["method"]) if binding else None
        result.append({
            "variable_code": requirement["variable_code"],
            "source_name": entry["source"]["name"] if entry else "历史/合成演示输入",
            "category": entry["category"] if entry else None,
            "unit_kind": requirement["unit_kind"],
            "selectors": binding["selectors"] if binding else {},
            "execution": deepcopy(entry["execution"]) if entry else {
                "available": False, "reason": "普通研究需要从系统目录重新选择此输入。", "channel": None},
            "data_available": None,
        })
    return result


def seal_input_sources(definition: dict, table: dict, data_kind: str,
                       subject: str, *, allow_legacy: bool = False,
                       source_snapshots: list[dict] = ()) -> dict:
    """在运行边界核验实际数据通道，冻结主体、准确来源与内容摘要。"""
    validate_input_bindings(definition, require_catalog=data_kind != "synthetic" and not allow_legacy)
    requirements = {r["variable_code"]: r for r in definition["collection_requirements"]}
    readiness = {r["variable_code"]: r for r in input_readiness(definition)}
    variables = {v["code"]: Variable.model_validate(v) for v in definition["variables"]}
    records = []
    if len({s["snapshot_id"] for s in source_snapshots}) != len(source_snapshots):
        raise ValueError("Source snapshot references must be unique")
    for column in table["columns"]:
        code = column["code"]
        if code not in requirements or code not in variables:
            raise ValueError("Observation column is not a declared external input: %s" % code)
        variable, requirement = variables[code], requirements[code]
        binding = requirement.get("catalog_binding")
        if column["unit"] != variable.unit:
            raise ValueError("Observation unit differs from the selected system input: %s" % code)
        if binding and column["name"] != variable.name:
            raise ValueError("Observation name differs from the fixed system input: %s" % code)
        if data_kind != "synthetic" and binding:
            status = readiness[code]["execution"]
            if not status["available"]:
                raise ValueError("Input data channel or scientific-unit adapter is unavailable: %s" % code)
            if column["value_kind"] != binding["value_nature"]:
                raise ValueError("Observation nature differs from its fixed source: %s" % code)
        for row in table["rows"]:
            variable.validate_value(row["values"][code])
        adopted = []
        if data_kind != "synthetic" and binding and requirement["source"] == "third_party":
            candidates = [s for s in source_snapshots if s["snapshot"]["binding"] == binding]
            parsed = []
            for candidate in candidates:
                snapshot = SourceSnapshot.model_validate(candidate["snapshot"])
                if identity_sha256(candidate["snapshot"]) != candidate["sha256"]:
                    raise ValueError("Source snapshot content checksum differs")
                parsed.append(snapshot)
                adopted.append({"snapshot_id": candidate["snapshot_id"], "sha256": candidate["sha256"],
                                "adapter": snapshot.adapter, "support": snapshot.support,
                                "quality": snapshot.quality, "acquired_at": snapshot.acquired_at.isoformat()})
            match_snapshots(parsed, requirement, table, code)
        record = {"variable": variable.model_dump(mode="json"),
                        "requirement": requirement,
                        "channel": "synthetic_demo" if data_kind == "synthetic" else (
                            "source_snapshot" if adopted else "workspace_manual_entry" if binding else "legacy_upload"),
                        "catalog_binding": binding}
        if len(adopted) == 1:
            source = adopted[0]
            record.update(source_snapshot={k: source[k] for k in ("snapshot_id", "sha256")},
                          **{k: source[k] for k in ("adapter", "support", "quality", "acquired_at")})
        elif adopted:
            record["source_snapshots"] = adopted
        records.append(record)
    used = {s["snapshot_id"] for r in records for s in (
        [r["source_snapshot"]] if "source_snapshot" in r else r.get("source_snapshots", []))}
    if used != {s["snapshot_id"] for s in source_snapshots}:
        raise ValueError("Source snapshot references contain unused or conflicting inputs")
    from .input_sources.contracts import validate_co_observations

    validate_co_observations([SourceSnapshot.model_validate(item["snapshot"]) for item in source_snapshots], table)
    evidence = {
        "format": "research_input_sources_v1", "catalog_sha256": _snapshot()["sha256"],
        "subject": subject, "data_kind": data_kind, "inputs": records,
        "table_sha256": identity_sha256(table), "row_count": len(table["rows"]),
        "business_date_start": min(r["business_date"] for r in table["rows"]),
        "business_date_end": max(r["business_date"] for r in table["rows"]),
    }
    return {**evidence, "sha256": identity_sha256(evidence)}
