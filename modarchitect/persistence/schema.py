# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 16:05
# @Author  : Codex
# @File    : schema.py
"""定义独立研究库首批方案及组件引用的持久化约束。"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    func,
)


metadata = MetaData()

scopes = Table(
    "resource_scopes",
    metadata,
    Column("resource_scope_id", Uuid, primary_key=True),
    Column("company_source", String(128), nullable=False),
    Column("company_id", BigInteger, nullable=False),
    UniqueConstraint("company_source", "company_id", name="uq_scope_company"),
    CheckConstraint("company_id > 0", name="ck_scope_company"),
)

components = Table(
    "model_component_definitions",
    metadata,
    Column("definition_id", Uuid, primary_key=True),
    Column("code", String(96), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("contract_json", JSON, nullable=False),
    Column("contract_sha256", String(64), nullable=False),
    UniqueConstraint("code", "revision", name="uq_component_revision"),
    CheckConstraint("revision >= 1", name="ck_component_revision"),
    CheckConstraint("contract_sha256 ~ '^[a-f0-9]{64}$'", name="ck_component_sha256"),
)

designs = Table(
    "research_designs",
    metadata,
    Column("design_id", Uuid, primary_key=True),
    Column("resource_scope_id", ForeignKey(scopes.c.resource_scope_id), nullable=False),
    Column("subject", String(256), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    UniqueConstraint(
        "resource_scope_id", "subject", "idempotency_key", name="uq_design_request"
    ),
)

drafts = Table(
    "research_design_drafts",
    metadata,
    Column("design_id", ForeignKey(designs.c.design_id), primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("configuration_json", JSON, nullable=False),
    Column("configuration_sha256", String(64), nullable=False),
    Column("initial_sha256", String(64), nullable=False),
    Column("version_name", String(128)),
    Column("initial_version_name", String(128)),
    Column(
        "updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    CheckConstraint("revision >= 1", name="ck_draft_revision"),
    CheckConstraint("configuration_sha256 ~ '^[a-f0-9]{64}$'", name="ck_draft_sha256"),
    CheckConstraint(
        "initial_sha256 ~ '^[a-f0-9]{64}$'", name="ck_draft_initial_sha256"
    ),
)

draft_versions = Table(
    "research_draft_versions",
    metadata,
    Column("design_id", ForeignKey(drafts.c.design_id), primary_key=True),
    Column("revision", Integer, primary_key=True),
    Column("version", String(29), nullable=False),
    Column("configuration_sha256", String(64), nullable=False),
    UniqueConstraint("design_id", "version", name="uq_research_draft_version"),
    CheckConstraint("revision >= 1", name="ck_research_draft_version_revision"),
    CheckConstraint(r"version ~ '^(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})$'", name="ck_research_draft_version_format"),
    CheckConstraint("configuration_sha256 ~ '^[a-f0-9]{64}$'", name="ck_research_draft_version_sha256"),
)

versions = Table(
    "research_design_versions",
    metadata,
    Column("design_version_id", Uuid, primary_key=True),
    Column("design_id", ForeignKey(designs.c.design_id), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("contract_json", JSON, nullable=False),
    Column("contract_sha256", String(64), nullable=False),
    Column("version_name", String(128), nullable=False),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    UniqueConstraint("design_id", "revision", name="uq_design_revision"),
    UniqueConstraint("design_id", "version_name", name="uq_design_version_name"),
    CheckConstraint("btrim(version_name) <> ''", name="ck_design_version_name"),
    UniqueConstraint("design_version_id", "design_id", name="uq_version_design"),
    CheckConstraint("revision >= 1", name="ck_design_revision"),
    CheckConstraint("contract_sha256 ~ '^[a-f0-9]{64}$'", name="ck_design_sha256"),
)

bindings = Table(
    "research_design_components",
    metadata,
    Column("design_version_id", Uuid, primary_key=True),
    Column("node_code", String(96), primary_key=True),
    Column("definition_id", ForeignKey(components.c.definition_id), nullable=False),
    ForeignKeyConstraint(["design_version_id"], [versions.c.design_version_id]),
)

studies = Table(
    "research_studies",
    metadata,
    Column("study_id", Uuid, primary_key=True),
    Column("design_id", Uuid, nullable=False),
    Column("design_version_id", Uuid, nullable=False),
    Column("request_key", String(128)),
    Column("context_json", JSON, nullable=False),
    Column("observation_start", Date, nullable=False),
    Column("observation_end", Date, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("study_id", "design_id", name="uq_study_design"),
    UniqueConstraint("study_id", "design_id", "design_version_id", name="uq_study_version"),
    UniqueConstraint("design_id", "request_key", name="uq_study_request"),
    ForeignKeyConstraint(["design_version_id", "design_id"],
                         ["research_design_versions.design_version_id", "research_design_versions.design_id"]),
    CheckConstraint("observation_end >= observation_start", name="ck_study_observation_dates"),
)
