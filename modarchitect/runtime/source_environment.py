# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 16:11
# @Author  : Codex
# @File    : source_environment.py
"""为独立Worker装配海豚环境凭据，来源实现无需知道调度器。"""

import os

import httpx

from ..input_sources.settings import SourceSettings
from ..input_sources.transport import SourceUnavailable
from .environments import read_environment
from .scheduler import DolphinScheduler


def source_settings(names: frozenset[str]) -> SourceSettings:
    """按配置名重新读取当前环境，查询失败不继续使用旧账户或个人profile。"""
    name = os.getenv("MODARCHITECT_DS_SOURCE_ENVIRONMENT_NAME")
    if not name:
        raise SourceUnavailable("Source scheduler environment name is not configured")
    scheduler = None
    try:
        scheduler = DolphinScheduler()
        environment = read_environment(scheduler.client, name)
        values = SourceSettings.from_exports(environment.config, names)
        policy = {"MODARCHITECT_WEATHER_ACCESS": os.getenv("MODARCHITECT_WEATHER_ACCESS")} if "MODARCHITECT_WEATHER_ACCESS" in names else {}
        return SourceSettings.from_mapping({**policy, **values.values})
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise SourceUnavailable("Source scheduler environment cannot be read") from exc
    finally:
        if scheduler is not None:
            scheduler.close()
