"""V4: add voice_recordings table for L1/L2/L3 open-ended audio capture

Revision ID: 6a1b2c3d4e5f
Revises: 5f0e1d2c3b4a
Create Date: 2026-05-29

★ 中文：这是一个「数据库迁移脚本」。alembic/versions/ 下每个文件都是
数据库表结构的一次变更记录。

为什么需要：生产库里有真实数据，不能删了重建。改表结构必须用
「在现有数据上执行的变更语句」（ALTER TABLE …），这就是迁移脚本。

★ 怎么串起来的：每个脚本记着自己的 revision（我是谁）和
down_revision（我的上一步是谁），连成一条链。容器启动时执行
`alembic upgrade head`，它会自动从数据库当前所在的位置一路执行到最新。

★ 改了 models.py 之后必须生成对应的迁移脚本，否则本地测试（每次都重建表）
是好的，但生产库的表结构不会变，一上线就报「列不存在」。
生成命令：`alembic revision --autogenerate -m "说明"`，
生成后**务必人工检查**——autogenerate 经常会漏掉或误判。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "6a1b2c3d4e5f"                                    # 本次变更的编号
down_revision: Union[str, Sequence[str], None] = "5f0e1d2c3b4a"   # 上一次变更的编号
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：把表结构往前推一步。容器启动时自动执行。"""
    op.create_table(
        "voice_recordings",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("question_id", sa.String(length=128), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_voice_recordings_session",
        "voice_recordings",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_voice_recordings_session_question",
        "voice_recordings",
        ["session_id", "question_id"],
        unique=False,
    )


def downgrade() -> None:
    """回滚：撤销这次变更。

    ★ 注意顺序和 upgrade 相反：先删索引再删表。
    ★ 也注意这是**破坏性**的——drop_table 会连数据一起删掉。
    生产环境几乎不会执行 downgrade；真要回滚请先备份。
    """
    op.drop_index("ix_voice_recordings_session_question", table_name="voice_recordings")
    op.drop_index("ix_voice_recordings_session", table_name="voice_recordings")
    op.drop_table("voice_recordings")
