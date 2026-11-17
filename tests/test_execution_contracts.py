# -*- coding: utf-8 -*-
# @Time    : 2026/11/12 12:54
# @Author  : Codex
# @File    : test_execution_contracts.py
"""通过公开方案编译与包合同验证节点用途和历史兼容边界。"""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from modarchitect.contracts.identifiers import identity_sha256
from modarchitect.contracts.model_center.component_packages import (
    ComponentPackageManifest,
)
from modarchitect.contracts.research.plans import ResearchPlan
from modarchitect.validation import compile_plan

ROOT = Path(__file__).parents[1]


def test_one_variable_can_be_label_and_feature_in_different_nodes():
    """同一标准指标可在候选模型间换用途，旧版本仍执行原全局角色。"""
    plan = json.loads(
        (ROOT / "modarchitect/web/designer/system-study.json").read_bytes()
    )["definition"]
    first = plan["composition"]["nodes"][0]
    second = deepcopy(first)
    second["code"] = "candidate"
    second["bindings"][1]["source"]["port"] = "candidate_config"
    external = deepcopy(plan["composition"]["inputs"][1])
    external["code"] = "candidate_config"
    plan["composition"]["inputs"].append(external)
    plan["composition"]["nodes"].append(second)
    plan["composition"]["outputs"].append(
        {
            "code": "candidate_model",
            "source": {"node": "candidate", "port": "trained_model"},
        }
    )
    recipe = deepcopy(plan["input_recipes"]["regression_config"])
    recipe["value"].update(features=["lai", "canopy_cover"], targets=["agb_kg_ha"])
    plan["input_recipes"]["candidate_config"] = recipe
    with pytest.raises(ValueError):
        compile_plan(ResearchPlan.model_validate(plan))
    plan["schema_version"] = "1.5"
    compiled = compile_plan(ResearchPlan.model_validate(plan))
    uses = {
        (u["node"], u["variable_code"], u["role"]) for u in compiled["variable_usages"]
    }
    assert (first["code"], "lai", "label") in uses
    assert ("candidate", "lai", "feature") in uses
    assert all(
        u["observed_required"]
        for u in compiled["variable_usages"]
        if u["role"] == "label"
    )


def test_package_versions_keep_old_payload_and_reject_false_capabilities():
    """旧清单规范摘要保持准确；新声明不可指向不存在的字段或状态端口。"""
    legacy = json.loads((ROOT / "components/template/component.json").read_bytes())
    legacy["artifact"]["manifest_digest"] = "sha256:" + "a" * 64
    parsed = ComponentPackageManifest.model_validate(legacy)
    assert identity_sha256(
        parsed.model_dump(mode="json", exclude_unset=True)
    ) == identity_sha256(legacy)
    new = deepcopy(legacy)
    new["manifest_version"] = "1.1"
    new["contract"]["execution"] = {"operations": ["analyze"]}
    ComponentPackageManifest.model_validate(new)
    for invalid in [
        {
            "operations": ["analyze"],
            "state_output": "missing",
            "inference": {"code": "infer", "revision": 1},
        },
        {
            "operations": ["analyze"],
            "input_uses": {"unknown": {"role": "analysis", "phases": ["analysis"]}},
        },
        {"operations": ["analyze", "analyze"]},
    ]:
        new["contract"]["execution"] = invalid
        with pytest.raises(ValueError):
            ComponentPackageManifest.model_validate(new)
