# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 16:11
# @Author  : Codex
# @File    : environments.py
"""只读解析海豚环境的准确名称和编号，配置正文不进入日志或业务合同。"""

from dataclasses import dataclass, field

import httpx


@dataclass(frozen=True)
class SchedulerEnvironment:
    """配置只在受信执行边界存活，打印对象不会暴露秘密。"""

    code: str
    name: str
    config: str = field(repr=False)


def read_environment(client: httpx.Client, name: str) -> SchedulerEnvironment:
    """分页读取获准环境并精确匹配；避免海豚3.4的PG模糊搜索参数类型缺陷。"""
    if not name or name != name.strip():
        raise ValueError("A precise scheduler environment name is required")
    matches, page = [], 1
    while True:
        response = client.get("environment/list-paging", params={"pageNo": page, "pageSize": 100})
        response.raise_for_status()
        body = response.json()
        if body.get("code") != 0 or not isinstance(body.get("data"), dict):
            raise ValueError("Scheduler environment query failed")
        data = body["data"]
        records = data["totalList"]
        matches.extend(row for row in records if row["name"] == name)
        if page*100 >= data["total"]:
            break
        if not records or page >= 100:
            raise ValueError("Scheduler environment query exceeds its page budget")
        page += 1
    if len(matches) != 1:
        raise ValueError("Scheduler environment name is missing or ambiguous")
    row = matches[0]
    code = str(row["code"])
    if not code.isdigit() or int(code) <= 0 or not isinstance(row["config"], str):
        raise ValueError("Scheduler environment identity differs")
    return SchedulerEnvironment(code, name, row["config"])
