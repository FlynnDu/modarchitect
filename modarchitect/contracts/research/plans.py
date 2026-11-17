# -*- coding: utf-8 -*-
# @Time    : 2026/11/4 22:32
# @Author  : feidu
# @File    : plans.py
"""完整研究配置、采集需求和对象分配；缺少实际观测不阻止方案成立。"""

from typing import Annotated, Literal

from pydantic import Field, StrictBool, model_validator

from modarchitect.contracts.model_center.components import (
    Code,
    Composition,
    Contract,
    Text,
)
from .variables import StudyContext, UnitKind, Variable
from .evaluation import NumericEvaluationGate
from .catalog_bindings import CatalogBinding
from .field_selection import SelectedResearchFields
from .report_layout import ReportOptions

STATE_PRODUCT = "wofost_report_state"

Purpose = Literal["explore", "simulate", "fit", "train", "predict", "evaluate"]


def sampling_points_required(unit_kind: object, flag: object = None) -> bool:
    """旧方案从观测单位补读采集开关，新方案按显式布尔值判断。"""
    point_unit = unit_kind == "point"
    if flag is None:
        return point_unit
    if not isinstance(flag, bool) or (unit_kind is not None and flag != point_unit):
        raise ValueError("Sampling point requirement differs from the observation unit")
    return flag


class CollectionMethod(Contract):
    """冻结采样标准及版本、实际方法和操作说明；不接受执行脚本。"""

    protocol_code: Code
    protocol_version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]
    method_code: Code
    instructions: Text
    evidence_required: bool = False


class CollectionRequirement(Contract):
    """一项变量/方法/科学支撑的采集要求，实例化后生成业务计划规则。"""

    code: Code
    variable_code: Code
    method: CollectionMethod
    unit_kind: UnitKind
    requires_sampling_points: StrictBool | None = None
    required_for: Annotated[tuple[Purpose, ...], Field(min_length=1)]
    source: Literal["manual", "third_party", "business_system"]
    catalog_binding: CatalogBinding | None = None
    start_offset_days: Annotated[int, Field(strict=True, ge=0, le=730)] = 0
    end_offset_days: Annotated[int | None, Field(strict=True, ge=0, le=730)] = None
    interval_days: Annotated[int | None, Field(strict=True, ge=1, le=366)] = None
    minimum_observations_per_unit: Annotated[int, Field(strict=True, ge=1, le=10000)]
    minimum_independent_units: Annotated[int, Field(strict=True, ge=1, le=10000)]

    @model_validator(mode="after")
    def valid_window(self):
        """缺省终点由实例种植季解析；最低数量是明确计划门槛而非自动功效结论。"""
        sampling_points_required(self.unit_kind, self.requires_sampling_points)
        if self.end_offset_days is not None:
            if self.end_offset_days < self.start_offset_days:
                raise ValueError("Collection requirement window is reversed")
        if len(set(self.required_for)) != len(self.required_for):
            raise ValueError("Collection requirement purposes must be unique")
        return self

    @property
    def needs_sampling_points(self) -> bool:
        """沿用准确观测单位与显式开关推导采集点需求。"""
        return sampling_points_required(self.unit_kind, self.requires_sampling_points)


def collection_schedule_schema() -> dict:
    """投影表单现有的采集频率和最低有效记录约束，复用方案校验的字段定义。"""
    schema = CollectionRequirement.model_json_schema()
    editable = (
        "minimum_observations_per_unit",
        "minimum_independent_units",
        "interval_days",
    )
    return {
        "type": "object",
        "properties": {key: schema["properties"][key] for key in editable},
        "required": [key for key in editable if key in schema["required"]],
    }


class InputRecipe(Contract):
    """把外部输入映射到观测表、结构化配置或已冻结成果，拒绝任意动态代码。"""

    kind: Literal["observations", "configuration", "artifact", "deferred"]
    variable_codes: tuple[Code, ...] = ()
    value: dict | None = None
    artifact_output: Code | None = None
    runtime_fields: dict[
        Code,
        Literal[
            "cutoff_date",
            "fit_cutoff_date",
            "cutoff_timestamp",
            "object",
            "season_start",
            "season_end",
        ],
    ] = Field(default_factory=dict)

    @model_validator(mode="after")
    def source_contract(self):
        """每个输入只采用一种来源；成果引用在实例内按准确运行输出解析。"""
        if self.kind == "deferred":
            valid = self.value is None and self.artifact_output is None
        elif self.kind == "observations":
            valid = (
                bool(self.variable_codes)
                and self.value is None
                and self.artifact_output is None
            )
        elif self.kind == "configuration":
            valid = (
                self.value is not None
                and not self.variable_codes
                and self.artifact_output is None
            )
        else:
            valid = (
                self.artifact_output is not None
                and not self.variable_codes
                and self.value is None
            )
        if not valid or len(set(self.variable_codes)) != len(self.variable_codes):
            raise ValueError("Research input recipe is inconsistent")
        if self.runtime_fields and self.kind != "configuration":
            raise ValueError("Runtime fields require a configuration input")
        return self


class EvaluationPolicy(Contract):
    """先明确目标、评价用途及分组边界；无独立证据不得声明生产资格。"""

    target_codes: tuple[Code, ...]
    purpose: Literal["exploratory", "independent_prediction", "mechanistic_validation"]
    split_unit: Literal["experimental_unit", "field_season", "time"]
    holdout_unit_refs: tuple[Text, ...] = ()
    success_criteria: Text
    update_policy: Literal["manual_candidate", "qualified_candidate"] = (
        "manual_candidate"
    )
    maximum_runs: Annotated[int, Field(strict=True, ge=1, le=1000)] = 10
    numeric_gate: NumericEvaluationGate | None = None


class ResearchPlan(Contract):
    """保存点位方案时核验所选地块，实际观测与业务授权仍在实例内绑定。"""

    schema_version: Literal["1.0", "1.1", "1.2", "1.3", "1.4", "1.5"] = "1.0"
    name: Annotated[str, Field(min_length=1, max_length=128)]
    question: Text
    objective: Literal["association", "prediction", "treatment_effect", "mechanistic"]
    purpose: Purpose
    variables: tuple[Variable, ...]
    collection_requirements: tuple[CollectionRequirement, ...]
    sampling_selection: SelectedResearchFields | None = None
    composition: Composition
    input_recipes: dict[Code, InputRecipe]
    evaluation: EvaluationPolicy
    report: ReportOptions | None = None
    layout: dict = Field(default_factory=dict)

    def requires_source_selection_evidence(
        self, requirement: CollectionRequirement
    ) -> bool:
        """1.4 对受取数属性影响的有效结果要求回传实际属性，旧方案保留原口径。"""
        return (
            self.schema_version in {"1.4", "1.5"}
            and requirement.catalog_binding is not None
            and bool(requirement.catalog_binding.selectors)
        )

    @model_validator(mode="after")
    def complete_research(self):
        """校验语义引用和数据来源完整性，实际值缺失留给实例的待采集状态。"""
        if self.schema_version not in {"1.2", "1.3", "1.4", "1.5"} and any(
            r.catalog_binding is not None for r in self.collection_requirements
        ):
            raise ValueError("Research source binding requires plan schema 1.2")
        variables = {v.code: v for v in self.variables}
        if not variables and (
            self.schema_version != "1.5"
            or self.purpose not in {"explore", "simulate"}
            or not self.input_recipes
            or not any(recipe.kind in {"artifact", "deferred"} for recipe in self.input_recipes.values())
            or any(recipe.kind not in {"artifact", "configuration", "deferred"} for recipe in self.input_recipes.values())
        ):
            raise ValueError("Observation research requires explicit variable definitions")
        gate = self.evaluation.numeric_gate
        if self.schema_version == "1.0" and gate is not None:
            raise ValueError("Numeric evaluation requires research plan schema 1.1")
        if gate is not None:
            if (
                gate.target_code not in self.evaluation.target_codes
                or self.evaluation.split_unit != "time"
            ):
                raise ValueError("Numeric evaluation target or split differs")
        if len(variables) != len(self.variables):
            raise ValueError("Research variable codes must be unique")
        requirements = {r.code: r for r in self.collection_requirements}
        if len(requirements) != len(self.collection_requirements):
            raise ValueError("Collection requirement codes must be unique")
        for requirement in self.collection_requirements:
            if requirement.variable_code not in variables:
                raise ValueError("Collection requirement variable is unresolved")
            if (
                requirement.catalog_binding is not None
                and variables[requirement.variable_code].role
                in {"target", "validation"}
                and requirement.catalog_binding.value_nature != "observed"
            ):
                raise ValueError(
                    "Research targets require observed measurement sources"
                )
        targets = set(self.evaluation.target_codes)
        if not targets <= set(variables) or (
            not targets
            and (
                self.schema_version != "1.5"
                or self.purpose not in {"explore", "simulate"}
            )
        ):
            raise ValueError("Evaluation targets are unresolved")
        if self.schema_version != "1.5" and any(
            variables[c].role not in {"target", "validation"} for c in targets
        ):
            raise ValueError("Evaluation targets have incompatible research roles")
        external = {item.code for item in self.composition.inputs}
        if set(self.input_recipes) != external:
            raise ValueError("Research input recipes differ from composition inputs")
        # 当前发布路径只信同一方案图内模拟节点产生的报告状态。
        if any(
            item.data_type.semantic == STATE_PRODUCT for item in self.composition.inputs
        ):
            raise ValueError(
                "WOFOST report state must come from an upstream simulation"
            )
        required_variables = {r.variable_code for r in self.collection_requirements}
        current_variables = {
            r.variable_code
            for r in self.collection_requirements
            if self.purpose in r.required_for
        }
        for recipe in self.input_recipes.values():
            if not set(recipe.variable_codes) <= set(variables):
                raise ValueError("Input recipe variable is unresolved")
            if not set(recipe.variable_codes) <= required_variables:
                raise ValueError("Observation input lacks collection requirements")
            if (
                recipe.kind == "observations"
                and not set(recipe.variable_codes) <= current_variables
            ):
                raise ValueError(
                    "Observation input lacks requirements for the declared purpose"
                )
        if self.objective == "treatment_effect" and not any(
            v.role == "treatment" for v in self.variables
        ):
            raise ValueError(
                "Treatment research requires an explicit treatment variable"
            )
        return self

    def validate_context(self, context: StudyContext) -> None:
        """校验真实单位的分组/处理和数量，不把观测次数当独立试验重复。"""
        assignments = {
            v.code: v for v in self.variables if v.role in {"treatment", "group"}
        }
        units = {unit.unit_ref: unit for unit in context.units}
        for unit in context.units:
            root = units[unit.experimental_unit_ref]
            if set(root.assignments) != set(assignments):
                raise ValueError(
                    "Experimental assignments differ from the research design"
                )
            for code, value in root.assignments.items():
                assignments[code].validate_value(value)
            if unit.unit_ref != root.unit_ref and unit.assignments:
                if unit.assignments != root.assignments:
                    raise ValueError(
                        "Observation unit assignments differ from its experiment"
                    )
        for requirement in self.collection_requirements:
            selected = [u for u in context.units if u.kind == requirement.unit_kind]
            if not selected:
                raise ValueError(
                    "Collection requirement has no matching scientific units"
                )
            if (
                len(
                    {
                        u.experimental_unit_ref
                        for u in selected
                        if self.purpose not in {"fit", "train"}
                        or u.experimental_unit_ref
                        not in self.evaluation.holdout_unit_refs
                    }
                )
                < requirement.minimum_independent_units
            ):
                raise ValueError("Study design has insufficient independent units")
        holdout = set(self.evaluation.holdout_unit_refs)
        if not holdout <= {u.experimental_unit_ref for u in context.units}:
            raise ValueError("Evaluation holdout units are unresolved")
        gate = self.evaluation.numeric_gate
        if (
            gate is not None
            and not context.season_start
            < gate.holdout_start
            <= gate.holdout_end
            <= context.season_end
        ):
            raise ValueError("Research holdout is outside the study season")
