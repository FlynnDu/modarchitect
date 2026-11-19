# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 19:27
# @Author  : Codex
# @File    : table_lineage.py
"""在研究图中跟踪已知列的来源性质和基线截点。"""

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class TableColumns:
    """列是否为实测，以及所有行严格晚于的已知日期。"""

    observed: dict[str, bool]
    after: date | None = None
    external: dict[str, frozenset[str]] = field(default_factory=dict)
    date_columns: frozenset[str] = frozenset()


def project_tables(
    declarations: dict, inputs: dict[str, TableColumns | None], parameters: dict
) -> dict[str, TableColumns]:
    """按组件合同传播声明的输出列，未知输入留给运行时检查。"""
    outputs = {}
    for port, declaration in declarations.items():
        if "inherit" not in declaration:
            outputs[port] = TableColumns(
                {
                    code: False
                    for field in declaration["predicted"]
                    for code in (
                        parameters[field]
                        if isinstance(parameters[field], list)
                        else [parameters[field]]
                    )
                },
                date.fromisoformat(parameters[declaration["fit_through"]]),
            )
            continue
        parent = inputs.get(declaration["inherit"])
        for merged_port in declaration.get("merge", []):
            other = inputs.get(merged_port)
            if parent is None or other is None:
                parent = None
                break
            if set(parent.observed) & set(other.observed):
                raise ValueError("Table output columns overlap")
            parent = TableColumns({**parent.observed, **other.observed},
                                  max((value for value in (parent.after, other.after) if value), default=None),
                                  {**parent.external, **other.external}, parent.date_columns | other.date_columns)
        if parent is not None and declaration.get("computed"):
            codes = [parameters[field] for field in declaration["computed"]]
            if set(codes) & set(parent.observed):
                raise ValueError("Computed table column must have a new identity")
            parent = TableColumns({**parent.observed, **{code: False for code in codes}}, parent.after,
                                  {**parent.external, **{code: frozenset() for code in codes}},
                                  parent.date_columns | frozenset(parameters[field] for field in declaration.get("exact_dates", [])))
        if "append" not in declaration:
            if parent is not None:
                outputs[port] = parent
            continue
        append = declaration["append"]
        source = inputs.get(append["port"])
        if parent is None or source is None:
            continue
        original = parameters[append["column"]]
        code = parameters[append["as"]]
        cutoffs = [item for item in (parent.after, source.after) if item is not None]
        outputs[port] = TableColumns(
            {**parent.observed, code: source.observed[original]},
            max(cutoffs, default=None),
            {**parent.external, code: source.external.get(original, frozenset())},
            parent.date_columns | (frozenset({code}) if original in source.date_columns else frozenset()),
        )
    return outputs
