# -*- coding: utf-8 -*-
# @Time    : 2026/11/13 13:48
# @Author  : Codex
# @File    : contracts.py
"""声明观察日期、业务启动和可信日触发的最小合同。"""

from datetime import date, datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from pydantic import Field, model_validator

from ..contracts.model_center.components import Contract
from ..contracts.research.field_selection import SelectedResearchFields
from ..input_sources.contracts import ReferencePoint
from ..runtime.contracts import ObjectReference

SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")


class ReportObject(Contract):
    """自有研究的完整对象和声明参考点，不授予企业地块授权。"""

    object: ObjectReference
    reference_point: ReferencePoint


class StudyPeriod(Contract):
    """观察范围是资料日期闭区间，末日资料在次日02:00处理。"""

    design_version_id: UUID
    observation_start: date
    observation_end: date

    @model_validator(mode="after")
    def bounded_period(self):
        """限制批次数量，拒绝倒序和过长研究；历史范围允许明确补齐。"""
        if not 0 <= (self.observation_end - self.observation_start).days <= 730:
            raise ValueError(
                "Report observation period is reversed or exceeds 731 days"
            )
        return self


class ReportPeriod(StudyPeriod):
    """日报允许引用指定预测模型。"""

    model_id: UUID | None = None


class WorkspaceReportStart(ReportPeriod):
    """个人工作区仅在声明的自有对象上启用持续研究。"""

    objects: Annotated[tuple[ReportObject, ...], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def unique_objects(self):
        """同一地块作物种植季不得绑定两个相互冲突的位置。"""
        keys = [
            (item.object.field_ref, item.object.crop_code, item.object.season_ref)
            for item in self.objects
        ]
        if len(set(keys)) != len(keys):
            raise ValueError("Report objects must be unique")
        return self


class BusinessReportStart(ReportPeriod):
    """业务选地必须由服务端重新核验，调用方不自报已授权坐标。"""

    fields: SelectedResearchFields


class ReportStateChange(Contract):
    """暂停和恢复使用乐观修订，不能以重发覆盖并发管理操作。"""

    expected_revision: Annotated[int, Field(strict=True, ge=1)]


class DailyTick(Contract):
    """海豚传逻辑触发时刻与真实实例，补跑不能使用进程当前时间代替。"""

    scheduled_at: datetime
    scheduler_id: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,18}$")]

    @model_validator(mode="after")
    def aware_clock(self):
        """逻辑时钟必须带时区，业务日期统一按上海日界推导。"""
        if self.scheduled_at.utcoffset() is None:
            raise ValueError("Daily trigger time requires a timezone")
        return self


def observation_day(tick: DailyTick) -> date:
    """每日02:00处理前一天，逻辑日期与实际执行延迟分别记录。"""
    logical = tick.scheduled_at.astimezone(SHANGHAI)
    if (logical.hour, logical.minute, logical.second, logical.microsecond) != (
        2,
        0,
        0,
        0,
    ):
        raise ValueError("Daily trigger must refer to 02:00 Asia/Shanghai")
    return logical.date() - timedelta(days=1)


def trigger_time(day: date) -> datetime:
    """将观测日映射为次日02:00，跨月跨年保持自然日期语义。"""
    return datetime.combine(
        day + timedelta(days=1), datetime.min.time(), SHANGHAI
    ) + timedelta(hours=2)
