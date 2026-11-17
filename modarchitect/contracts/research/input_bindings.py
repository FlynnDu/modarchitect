# -*- coding: utf-8 -*-
# @Time    : 2026/11/9 16:14
# @Author  : feidu
# @File    : input_bindings.py
"""核对科研配置引用的观测列，实际成果及观测仍在运行时核验。"""

from datetime import date

from modarchitect.contracts.research.plans import ResearchPlan
from modarchitect.contracts.research.table_lineage import TableColumns, project_tables


class ResearchInputBindingError(ValueError):
    """保留编辑器可定位的请求字段和实际输入端口。"""

    def __init__(
        self, node: str, port: str, recipe: str, field: str, reason: str
    ) -> None:
        """记录编辑器定位问题所需的节点、端口和字段。"""
        self.node = node
        self.port = port
        self.path = ["input_recipes", recipe, "value", field]
        super().__init__(
            "Node %s input %s, request field %s: %s" % (node, port, field, reason)
        )


def validate_research_input_bindings(
    plan: ResearchPlan,
    order: list[str],
    requests: dict[str, tuple[str, dict, dict]],
    projections: dict[str, dict],
) -> None:
    """只推导方案明确声明的观测列及保留列的表操作，避免猜测模型成果内容。"""
    nodes = {node.code: node for node in plan.composition.nodes}
    variables = {v.code: v for v in plan.variables}
    non_observed = {
        r.variable_code
        for r in plan.collection_requirements
        if plan.purpose in r.required_for
        and r.catalog_binding is not None
        and r.catalog_binding.value_nature != "observed"
    }
    columns: dict[tuple[str | None, str], TableColumns] = {
        (None, port): TableColumns(
            {code: code not in non_observed for code in recipe.variable_codes}
        )
        for port, recipe in plan.input_recipes.items()
        if recipe.kind == "observations"
    }
    for code in order:
        node = nodes[code]
        component = node.component.code
        inputs = {
            binding.port: columns.get((binding.source.node, binding.source.port))
            for binding in node.bindings
        }
        if component == "research_table_upgrade":
            table = inputs["table"]
            if table is not None:
                columns[code, "table"] = table
        elif component == "research_table_join":
            left, right = inputs["left"], inputs["right"]
            if left is not None and right is not None:
                after = max(
                    (bound for bound in (left.after, right.after) if bound),
                    default=None,
                )
                columns[code, "table"] = TableColumns(
                    {**left.observed, **right.observed}, after
                )

        request = requests.get(code)
        if request is None:
            continue
        recipe, value, schema = request
        _check_variable_fields(
            code,
            recipe,
            value,
            schema,
            inputs,
            variables,
            set(plan.evaluation.target_codes),
            contextual=plan.schema_version == "1.5",
        )
        for out, table in project_tables(
            projections.get(code, {}), inputs, value
        ).items():
            columns[code, out] = table
        if component == "multivariate_linear_regression":
            table = inputs["observations"]
            if (
                table is not None
                and table.after is not None
                and date.fromisoformat(value["training_end"]) <= table.after
            ):
                raise ResearchInputBindingError(
                    code,
                    "observations",
                    recipe,
                    "training_end",
                    "Regression training end must follow the baseline fit cutoff",
                )
        if component == "factor_relationship_analysis":
            port = "table"
            referenced = [("factors", factor) for factor in value["factors"]]
            referenced.append(("target", value["target"]))
        elif component == "logistic_growth_curve":
            port = "observations"
            referenced = [("x_code", value["x_code"])]
            parent = inputs[port]
            columns[code, "curve"] = TableColumns(
                {
                    value["x_code"]: parent is not None
                    and parent.observed.get(value["x_code"], False),
                    value["target_code"]: False,
                    "logistic_extrapolated": False,
                }
            )
            if value["operation"] == "fit":
                referenced.append(("target_code", value["target_code"]))
        elif component == "prediction_holdout_evaluation":
            port = "observations"
            referenced = [("target_code", value["target_code"])]
        else:
            continue
        table = inputs[port]
        if table is None:
            continue
        for field, variable_code in referenced:
            if variable_code not in table.observed:
                raise ResearchInputBindingError(
                    code,
                    port,
                    recipe,
                    field,
                    "Variable %s is not bound to this observation table"
                    % variable_code,
                )
            variable = variables[variable_code]
            if component == "logistic_growth_curve":
                if field == "x_code":
                    unit = (
                        "day" if value["axis_kind"] == "elapsed_days" else "deg_c_day"
                    )
                    if variable.unit != unit:
                        raise ResearchInputBindingError(
                            code,
                            port,
                            recipe,
                            field,
                            "Logistic driver must use unit %s" % unit,
                        )
                if value["operation"] == "fit" and not table.observed[variable_code]:
                    raise ResearchInputBindingError(
                        code,
                        port,
                        recipe,
                        field,
                        "Logistic fitting requires an observed variable",
                    )
                if (
                    field == "target_code"
                    and variable.role != "target"
                    and plan.schema_version != "1.5"
                ):
                    raise ResearchInputBindingError(
                        code,
                        port,
                        recipe,
                        field,
                        "Logistic fitting requires a target variable",
                    )
            elif component == "prediction_holdout_evaluation" and (
                variable.role not in {"target", "validation"}
                or not table.observed[variable_code]
            ):
                raise ResearchInputBindingError(
                    code,
                    port,
                    recipe,
                    field,
                    "Holdout evaluation requires an observed target or validation variable",
                )


def _check_variable_fields(
    node: str,
    recipe: str,
    value: dict,
    schema: dict,
    inputs: dict,
    variables: dict,
    targets: set[str],
    *,
    contextual: bool = False,
) -> None:
    """按声明校验观测端口、变量角色和数值目标的观测性质。"""
    for field, property_schema in schema.get("properties", {}).items():
        spec = property_schema.get("x-research-variables")
        if spec is None or field not in value:
            continue
        port = spec["table_port"]
        columns = inputs.get(port)
        codes = (
            value[field] if property_schema.get("type") == "array" else [value[field]]
        )
        for code in codes:
            variable = variables.get(code)
            if (
                variable is None
                or port not in inputs
                or (not contextual and variable.role not in spec["roles"])
                or (spec.get("unit") and variable.unit != spec["unit"])
                or (spec.get("evaluation_target") and code not in targets)
            ):
                raise ResearchInputBindingError(
                    node,
                    port,
                    recipe,
                    field,
                    "Variable %s does not satisfy the declared observation binding"
                    % code,
                )
            if spec.get("new_column"):
                source_field = spec["source_field"]
                source_variable = variables.get(value.get(source_field))
                if (columns is not None and code in columns.observed) or (
                    source_field in value
                    and (
                        source_variable is None or source_variable.unit != variable.unit
                    )
                ):
                    raise ResearchInputBindingError(
                        node,
                        port,
                        recipe,
                        field,
                        "Forecast feature must have a new column code and the same unit",
                    )
            elif columns is not None:
                if code not in columns.observed:
                    raise ResearchInputBindingError(
                        node,
                        port,
                        recipe,
                        field,
                        "The upstream table does not supply variable %s" % code,
                    )
                if spec.get("observed") and not columns.observed[code]:
                    raise ResearchInputBindingError(
                        node,
                        port,
                        recipe,
                        field,
                        "The training target requires an observed column",
                    )
