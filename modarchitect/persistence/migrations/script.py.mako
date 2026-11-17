${"# -*- coding: utf-8 -*-"}
# @Time    : ${create_date.strftime('%Y/%m/%d %H:%M')}
# @Author  : ${config.attributes.get("author", "待填写")}
# @File    : ${config.attributes.get("filename", "待填写.py")}
"""记录研究库迁移及其回退条件。"""

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    """应用数据库结构变更。"""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """按版本回退数据库结构。"""
    ${downgrades if downgrades else "pass"}
