# -*- coding: utf-8 -*-
# @Time    : 2026/11/11 16:05
# @Author  : Codex
# @File    : migrate.py
"""提供独立研究库的迁移入口，连接信息由迁移角色单独配置。"""

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine


def migration_config() -> Config:
    """从安装后的包定位版本链。"""
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).with_name("migrations"))
    )
    return config


def main() -> None:
    """将配置的独立研究库升级到当前版本。"""
    url = os.getenv("MODARCHITECT_MIGRATION_DATABASE_URL")
    if not url:
        sys.exit("MODARCHITECT_MIGRATION_DATABASE_URL is required")
    engine = create_engine(url, hide_parameters=True)
    if engine.dialect.name != "postgresql":
        sys.exit("The research database requires PostgreSQL")
    try:
        with engine.connect() as connection:
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
