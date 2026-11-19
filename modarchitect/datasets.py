# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 13:41
# @Author  : Codex
# @File    : datasets.py
"""按科学列及完整对象日期装配数据，封存可复用的受权研究输入。"""

from uuid import UUID

from .contracts.enterprise.identity import VerifiedPrincipal
from .contracts.identifiers import identity_sha256
from .designs import ResearchDesigns
from .persistence.dataset_store import DatasetStore
from .persistence.source_store import SourceStore
from .runtime.contracts import ObservationTable
from .system_inputs import seal_input_sources


class SourceCoverageMissing(ValueError):
    """来源缺对象日期记录；持续研究可保留截止日并等待补齐。"""


def record_key(row: dict) -> tuple[str, str]:
    """完整对象包含地块、作物和种植季，不能仅用日期或地块号配对。"""
    return identity_sha256(row["object"]), row["business_date"]


def assemble_tables(tables: list[dict], *, base: dict | None = None) -> dict:
    """来源列按键连接，基础观测限定日期；无基础时要求所有列完整覆盖并集。"""
    columns, values, objects = {}, {}, {}
    for table in tables:
        parsed = ObservationTable.model_validate(table).model_dump(mode="json")
        for column in parsed["columns"]:
            code = column["code"]
            if code in columns and columns[code] != column:
                raise ValueError("Dataset scientific columns differ: %s" % code)
            columns[code] = column
            for row in parsed["rows"]:
                key = record_key(row)
                objects[key] = row["object"]
                value_key = key + (code,)
                if value_key in values:
                    raise ValueError("Dataset records overlap: %s" % code)
                values[value_key] = row["values"][code]
    if base is not None:
        parsed_base = ObservationTable.model_validate(base).model_dump(mode="json")
        for column in parsed_base["columns"]:
            if column["code"] in columns:
                raise ValueError("Manual columns cannot replace acquired source values")
            columns[column["code"]] = column
        keys = []
        for row in parsed_base["rows"]:
            key = record_key(row)
            keys.append(key)
            objects[key] = row["object"]
            for code, value in row["values"].items():
                values[key + (code,)] = value
    else:
        keys = sorted(objects)
    rows = []
    for key in keys:
        if any(key + (code,) not in values for code in columns):
            raise SourceCoverageMissing(
                "Dataset sources do not cover every object, date and column"
            )
        rows.append(
            {
                "object": objects[key],
                "business_date": key[1],
                "values": {code: values[key + (code,)] for code in columns},
            }
        )
    return ObservationTable.model_validate(
        {"columns": list(columns.values()), "rows": rows}
    ).sealed()


class ResearchDatasets:
    """数据集入口只核验并封存来源，不采集、训练或决定模型发布。"""

    def __init__(
        self, designs: ResearchDesigns, store: DatasetStore, sources: SourceStore
    ):
        """显式注入已有方案、数据集存储和来源读取。"""
        self.designs, self.store, self.sources = designs, store, sources

    def create(
        self,
        owner: VerifiedPrincipal,
        design_id: UUID,
        source_ids: tuple[UUID, ...],
        observations: ObservationTable | None,
        data_kind: str,
        *,
        definition: dict | None = None,
    ) -> dict:
        """以方案定义核验准确来源和可选人工列，返回不可变数据集身份。"""
        definition = (
            definition
            if definition is not None
            else self.designs.read(owner, design_id)["configuration"]["definition"]
        )
        content = self.prepare(owner, definition, source_ids, observations, data_kind)
        return self.store.save(owner, design_id, content)

    def prepare(
        self,
        owner: VerifiedPrincipal,
        definition: dict,
        source_ids: tuple[UUID, ...],
        observations: ObservationTable | None,
        data_kind: str,
        *,
        study_id: UUID | None = None,
        allow_prior_unbound: bool = False,
    ) -> dict:
        """事务外解析不可变来源并准备准确内容，交给普通或批次原子事务保存。"""
        sources = self.sources.resolve(owner, source_ids, study_id=study_id, allow_prior_unbound=allow_prior_unbound)
        if data_kind == "synthetic" and sources:
            raise ValueError(
                "Synthetic labels cannot be promoted using real provider sources"
            )
        if not sources and observations is None:
            raise ValueError("Dataset requires acquired sources or observations")
        tables = [s["snapshot"]["observations"] for s in sources]
        table = assemble_tables(
            tables, base=observations.sealed() if observations else None
        )
        manifest = seal_input_sources(
            definition, table, data_kind, owner.subject, source_snapshots=sources
        )
        content = {
            "format": "research_dataset_v1",
            "observations": table,
            "data_kind": data_kind,
            "source_snapshot_ids": [str(v) for v in source_ids],
            "input_sources": manifest,
        }
        return content

    def resolve(self, owner: VerifiedPrincipal, identity: UUID) -> dict:
        """回读准确数据及来源引用，不因当前提供方更新而重新取数。"""
        return self.store.read(owner, identity)["content_json"]
