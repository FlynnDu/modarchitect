# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 15:36
# @Author  : Codex
# @File    : test_daily_scheduler.py
"""以准确海豚HTTP响应核验日程覆盖、实例日界与保留参数门禁。"""

from copy import deepcopy
from datetime import date, datetime
import json
from types import SimpleNamespace

import httpx
import pytest

from modarchitect.business import BusinessUnavailable
from modarchitect.report_tasks import scheduler
from modarchitect.report_tasks.contracts import SHANGHAI


def transport(monkeypatch, instance=None, schedule=None, zone="Asia/Shanghai"):
    """只替换HTTP传输，执行真实协议解析和拒绝规则。"""
    monkeypatch.setenv("MODARCHITECT_DS_DAILY_WORKFLOW", "52")
    monkeypatch.setenv("MODARCHITECT_DS_DAILY_VERSION", "1")

    def respond(request):
        """按实际端点返回最小必需字段，不伪造门禁通过结果。"""
        if request.url.path.endswith("/get-user-info"):
            data = {"id": 7, "timeZone": zone}
        elif request.url.path.endswith("/schedules"):
            data = {"totalList": [schedule]}
        elif request.url.path.endswith("/project-parameter"):
            data = {"totalList": [], "total": 0}
        else:
            data = instance
        return httpx.Response(200, json={"code": 0, "data": data})

    def make_client():
        """每次验证独立释放同一准确传输适配的连接。"""
        client = httpx.Client(
            base_url="https://scheduler.invalid/",
            transport=httpx.MockTransport(respond),
        )
        return SimpleNamespace(project="42", client=client, close=client.close)

    monkeypatch.setattr(scheduler, "DolphinScheduler", make_client)


def valid_instance():
    """固定实例为上海11月13日02点，不能和其他业务日期交叉采用。"""
    return {
        "id": 81,
        "projectCode": 42,
        "workflowDefinitionCode": 52,
        "workflowDefinitionVersion": 1,
        "commandType": "SCHEDULER",
        "commandParam": json.dumps(
            {"commandType": "SCHEDULER", "timeZone": "Asia/Shanghai"}
        ),
        "scheduleTime": "2026-11-13 02:00:00",
        "globalParams": "[]",
        "varPool": "[]",
        "dagData": {
            "workflowDefinition": {"globalParams": "[]"},
            "taskDefinitionList": [
                {"taskType": "SHELL", "taskParams": {"localParams": []}}
            ],
        },
    }


def test_actual_scheduler_instance_must_match_date_zone_and_reserved_names(monkeypatch):
    """合法实例可回放；换日、未知序列化时区、子工作流和覆盖built-in均拒绝。"""
    logical = datetime(2026, 11, 13, 2, tzinfo=SHANGHAI)
    row = valid_instance()
    transport(monkeypatch, instance=row)
    scheduler.require_daily_instance("81", logical)
    with pytest.raises(BusinessUnavailable):
        scheduler.require_daily_instance(
            "81", datetime(2026, 11, 12, 2, tzinfo=SHANGHAI)
        )
    transport(monkeypatch, instance=row, zone="UTC")
    with pytest.raises(BusinessUnavailable):
        scheduler.require_daily_instance("81", logical)
    for patch in (
        {"subWorkflowInstance": True},
        {"startParams": json.dumps({"system.biz.curdate": "20260101"})},
    ):
        changed = deepcopy(row)
        changed["commandParam"] = json.dumps(
            {"commandType": "SCHEDULER", "timeZone": "Asia/Shanghai", **patch}
        )
        transport(monkeypatch, instance=changed)
        with pytest.raises(BusinessUnavailable):
            scheduler.require_daily_instance("81", logical)


def test_new_online_schedule_can_fill_history_but_must_cover_next_and_final_trigger(
    monkeypatch,
):
    """历史任务由下一次真实触发补齐，过期或提前结束的在线日程仍拒绝。"""
    monkeypatch.setattr(
        scheduler, "now", lambda: datetime(2026, 11, 13, 15, tzinfo=SHANGHAI)
    )
    row = {
        "releaseState": "ONLINE",
        "crontab": "0 0 2 * * ?",
        "timezoneId": "Asia/Shanghai",
        "startTime": "2026-11-13 00:00:00",
        "endTime": "2026-12-01 03:00:00",
    }
    transport(monkeypatch, schedule=row)
    scheduler.require_daily_schedule(date(2025, 1, 1), date(2025, 1, 2))
    scheduler.require_daily_schedule(date(2026, 11, 14), date(2026, 11, 30))
    with pytest.raises(BusinessUnavailable):
        scheduler.require_daily_schedule(date(2026, 11, 14), date(2026, 12, 1))
    row["endTime"] = "2026-11-13 23:59:59"
    transport(monkeypatch, schedule=row)
    with pytest.raises(BusinessUnavailable):
        scheduler.require_daily_schedule(date(2025, 1, 1), date(2025, 1, 2))


def test_native_backfill_dates_are_not_parameter_json_and_cannot_hide_overrides(monkeypatch):
    """真实补数的日期数组合法，日期中的伪参数及实际参数中的保留名仍拒绝。"""
    logical = datetime(2026, 11, 13, 2, tzinfo=SHANGHAI)
    row = valid_instance()
    row["commandType"] = "COMPLEMENT_DATA"
    command = {"commandType": "COMPLEMENT_DATA", "timeZone": "Asia/Shanghai",
               "backfillTimeList": ["2026-11-13 02:00:00", "2026-11-14 02:00:00"],
               "commandParams": {}}
    row["commandParam"] = json.dumps(command)
    transport(monkeypatch, instance=row)
    scheduler.require_daily_instance("81", logical)
    for patch in (
        {"commandParams": {"system.biz.curdate": "20260101"}},
        {"backfillTimeList": [{"system.biz.curdate": "20260101"}]},
        {"backfillTimeList": ["2026-11-13 03:00:00"]},
    ):
        changed = deepcopy(row)
        changed["commandParam"] = json.dumps({**command, **patch})
        transport(monkeypatch, instance=changed)
        with pytest.raises(BusinessUnavailable):
            scheduler.require_daily_instance("81", logical)
