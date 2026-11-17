# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 13:53
# @Author  : Codex
# @File    : scheduler.py
"""核对真实海豚的日触发计划，不在应用进程内建立另一套定时时钟。"""

import os
import json
from datetime import date, datetime, timedelta
import httpx

from ..business import BusinessUnavailable
from ..runtime.scheduler import DolphinScheduler
from ..runtime.store import now
from .contracts import SHANGHAI, trigger_time


def require_daily_schedule(start: date, end: date) -> None:
    """启用研究前确认固定日计划在线、02:00及上海日界完全相符。"""
    workflow = os.getenv("MODARCHITECT_DS_DAILY_WORKFLOW")
    if not workflow:
        raise BusinessUnavailable("Daily report scheduler is not configured")
    scheduler = None
    try:
        scheduler = DolphinScheduler()
        account = _require_shanghai_account(scheduler)
        response = scheduler.client.get(
            "projects/" + scheduler.project + "/schedules",
            params={
                "workflowDefinitionCode": workflow,
                "pageNo": 1,
                "pageSize": 100,
            },
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get("data"), dict):
            raise BusinessUnavailable("Daily report scheduler contract differs")
        rows = body["data"].get("totalList", [])
        if body.get("code") != 0 or len(rows) != 1:
            raise BusinessUnavailable("Daily report scheduler is unavailable")
        row = rows[0]
        if (
            row.get("releaseState") != "ONLINE"
            or row.get("crontab") != "0 0 2 * * ?"
            or row.get("timezoneId") != "Asia/Shanghai"
        ):
            raise BusinessUnavailable("Daily report scheduler contract differs")
        bounds = []
        for field in ("startTime", "endTime"):
            value = datetime.fromisoformat(row[field])
            bounds.append(
                value.replace(tzinfo=SHANGHAI)
                if value.tzinfo is None
                else value.astimezone(SHANGHAI)
            )
        clock = now().astimezone(SHANGHAI)
        next_tick = trigger_time(clock.date() - timedelta(days=1))
        if clock >= next_tick:
            next_tick += timedelta(days=1)
        first = max(next_tick, trigger_time(start))
        last = max(first, trigger_time(end))
        if bounds[0] > first or bounds[1] < last:
            raise BusinessUnavailable(
                "Daily report schedule does not cover the observation period"
            )
        if _require_shanghai_account(scheduler) != account:
            raise ValueError("Daily scheduler account changed during verification")
    except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError) as exc:
        raise BusinessUnavailable("Daily report scheduler is unavailable") from exc
    finally:
        if scheduler is not None:
            scheduler.close()


def require_daily_instance(identity: str, scheduled_at: datetime) -> None:
    """按准确海豚实例核验调度命令、时区及保留变量没有被自定义覆盖。"""
    scheduler = None
    try:
        workflow = os.environ["MODARCHITECT_DS_DAILY_WORKFLOW"]
        version = int(os.environ["MODARCHITECT_DS_DAILY_VERSION"])
        scheduler = DolphinScheduler()
        account = _require_shanghai_account(scheduler)
        base = "projects/" + scheduler.project
        response = scheduler.client.get(base + "/workflow-instances/" + identity)
        response.raise_for_status()
        body = response.json()
        row = body["data"]
        if (
            body["code"] != 0
            or str(row["id"]) != identity
            or str(row["projectCode"]) != scheduler.project
            or str(row["workflowDefinitionCode"]) != workflow
            or row["workflowDefinitionVersion"] != version
        ):
            raise ValueError("Daily workflow identity differs")
        command = (
            json.loads(row["commandParam"])
            if isinstance(row["commandParam"], str)
            else row["commandParam"]
        )
        if (
            row["commandType"] not in {"SCHEDULER", "COMPLEMENT_DATA"}
            or command.get("timeZone") != "Asia/Shanghai"
            or not row.get("scheduleTime")
        ):
            raise ValueError(
                "Daily workflow is not an explicit Shanghai scheduled trigger"
            )
        logical = datetime.fromisoformat(row["scheduleTime"])
        if logical.tzinfo is None:
            logical = logical.replace(tzinfo=SHANGHAI)
        if logical != scheduled_at:
            raise ValueError(
                "Daily callback logical time differs from its scheduler instance"
            )
        command_value = command.get("commandType")
        command_code = {"SCHEDULER": 6, "COMPLEMENT_DATA": 5}[row["commandType"]]
        if command_value not in {row["commandType"], command_code, str(command_code)}:
            raise ValueError("Daily scheduler command evidence differs")
        if command.get("subWorkflowInstance") not in {None, False, "false"}:
            raise ValueError("Daily driver cannot be a subworkflow instance")
        dag = row["dagData"]
        if (
            len(dag["taskDefinitionList"]) != 1
            or dag["taskDefinitionList"][0]["taskType"] != "SHELL"
        ):
            raise ValueError("Daily driver must use its registered single shell task")
        # 海豚补数日期是调度元数据，不是待解析的自定义参数JSON。
        if "backfillTimeList" in command:
            times = command["backfillTimeList"]
            if row["commandType"] != "COMPLEMENT_DATA" or not isinstance(times, list) or not times:
                raise ValueError("Daily backfill date list differs")
            for value in times:
                if (not isinstance(value, str) or len(value) != 19
                        or datetime.fromisoformat(value).time() != datetime.min.time().replace(hour=2)):
                    raise ValueError("Daily backfill must use explicit 02:00 dates")
        _reject_reserved_parameters({k: v for k, v in command.items() if k != "backfillTimeList"})
        _reject_reserved_parameters(row["globalParams"])
        _reject_reserved_parameters(row.get("varPool") or [])
        _reject_reserved_parameters(dag["workflowDefinition"].get("globalParams") or [])
        for task in dag["taskDefinitionList"]:
            parameters = (
                json.loads(task["taskParams"])
                if isinstance(task["taskParams"], str)
                else task["taskParams"]
            )
            _reject_reserved_parameters(parameters.get("localParams") or [])
            if any(p.get("direct") == "OUT" for p in parameters.get("localParams", [])):
                raise ValueError("Daily driver cannot export mutable parameters")
        page = 1
        while True:
            response = scheduler.client.get(
                base + "/project-parameter", params={"pageNo": page, "pageSize": 100}
            )
            response.raise_for_status()
            body = response.json()
            if body["code"] != 0:
                raise ValueError("Daily project parameters are unavailable")
            records = body["data"]["totalList"]
            for record in records:
                _reject_reserved_parameters(record.get("paramName", ""), name=True)
            if page * 100 >= body["data"]["total"]:
                break
            if not records:
                raise ValueError("Daily project parameter pagination differs")
            page += 1
        if _require_shanghai_account(scheduler) != account:
            raise ValueError("Daily scheduler account changed during verification")
    except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError) as exc:
        raise BusinessUnavailable(
            "Daily report scheduler instance cannot be verified"
        ) from exc
    finally:
        if scheduler is not None:
            scheduler.close()


def _require_shanghai_account(scheduler: DolphinScheduler) -> str:
    """海豚Date序列化使用Token用户时区，首期固定并在线核对，不改账号配置。"""
    response = scheduler.client.get("users/get-user-info")
    response.raise_for_status()
    body = response.json()
    if body["code"] != 0 or body["data"].get("timeZone") != "Asia/Shanghai":
        raise ValueError(
            "Daily scheduler account must serialize dates in Asia/Shanghai"
        )
    return str(body["data"]["id"])


def _reject_reserved_parameters(value, *, name: bool = False) -> None:
    """仅检查参数名称，不误拒绝脚本或参数值中对内置变量的正常引用。"""
    if name:
        if not isinstance(value, str) or value.startswith("system."):
            raise ValueError("Daily scheduler reserved parameter override is forbidden")
    elif isinstance(value, str):
        if value.strip():
            _reject_reserved_parameters(json.loads(value))
    elif isinstance(value, list):
        for item in value:
            _reject_reserved_parameters(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _reject_reserved_parameters(key, name=True)
            if key in {"prop", "paramName"}:
                _reject_reserved_parameters(item, name=True)
            elif isinstance(item, (list, dict)) or key in {
                "commandParams",
                "startParams",
                "startParamsMap",
            }:
                _reject_reserved_parameters(item)
