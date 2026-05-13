"""PDF 编码词：参与者列名、actions 的 case_action_choice / log_final_action / case_action_reason

Revision ID: 5f0e1d2c3b4a
Revises: 4c7d8e9f0a1b
Create Date: 2026-05-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5f0e1d2c3b4a"
down_revision: Union[str, Sequence[str], None] = "4c7d8e9f0a1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- participants: rename to PDF coding words ---
    op.add_column(
        "participants", sa.Column("pre_specialty", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "participants",
        sa.Column("pre_training_level", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "participants", sa.Column("pre_years_post_residency", sa.Integer(), nullable=True)
    )
    op.add_column(
        "participants",
        sa.Column("pre_weekly_msg_volume", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "participants", sa.Column("pre_ai_drafting_familiarity", sa.Integer(), nullable=True)
    )
    op.execute(
        sa.text(
            "UPDATE participants SET pre_specialty = specialty, "
            "pre_training_level = training_level, "
            "pre_years_post_residency = years_practice, "
            "pre_weekly_msg_volume = weekly_message_volume, "
            "pre_ai_drafting_familiarity = ai_familiarity"
        )
    )
    op.drop_column("participants", "specialty")
    op.drop_column("participants", "training_level")
    op.drop_column("participants", "years_practice")
    op.drop_column("participants", "weekly_message_volume")
    op.drop_column("participants", "ai_familiarity")

    # --- actions: PDF 第三节 + 第五节结构化字段 ---
    op.add_column(
        "actions", sa.Column("case_action_choice", sa.Integer(), nullable=True)
    )
    op.add_column(
        "actions", sa.Column("log_final_action", sa.String(length=32), nullable=True)
    )
    op.add_column("actions", sa.Column("case_action_reason", sa.JSON(), nullable=True))

    op.execute(
        sa.text(
            "UPDATE actions SET case_action_choice = CASE selected_action "
            "WHEN 'send_as_is' THEN 1 WHEN 'edit_then_send' THEN 2 "
            "WHEN 'discard_and_rewrite' THEN 3 WHEN 'escalate' THEN 4 ELSE 1 END, "
            "log_final_action = CASE selected_action "
            "WHEN 'send_as_is' THEN '直接发送' WHEN 'edit_then_send' THEN '编辑后发送' "
            "WHEN 'discard_and_rewrite' THEN '弃用并重写' WHEN 'escalate' THEN '升级处理' "
            "ELSE '直接发送' END"
        )
    )

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            sa.text(
                "UPDATE actions SET case_action_reason = "
                "json_object('code', action_reason_code, 'text', action_reason_text) "
                "WHERE action_reason_code IS NOT NULL"
            )
        )
    else:
        op.execute(
            sa.text(
                "UPDATE actions SET case_action_reason = CAST("
                "json_build_object('code', action_reason_code, 'text', action_reason_text) "
                "AS json) WHERE action_reason_code IS NOT NULL"
            )
        )

    op.drop_column("actions", "action_reason_text")
    op.drop_column("actions", "action_reason_code")

    bind2 = op.get_bind()
    if bind2.dialect.name == "sqlite":
        with op.batch_alter_table("actions") as batch_op:
            batch_op.alter_column(
                "case_action_choice",
                existing_type=sa.Integer(),
                nullable=False,
            )
            batch_op.alter_column(
                "log_final_action",
                existing_type=sa.String(length=32),
                nullable=False,
            )
    else:
        op.alter_column(
            "actions",
            "case_action_choice",
            existing_type=sa.Integer(),
            nullable=False,
        )
        op.alter_column(
            "actions",
            "log_final_action",
            existing_type=sa.String(length=32),
            nullable=False,
        )


def downgrade() -> None:
    op.add_column(
        "actions", sa.Column("action_reason_code", sa.String(length=64), nullable=True)
    )
    op.add_column("actions", sa.Column("action_reason_text", sa.Text(), nullable=True))

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            sa.text(
                "UPDATE actions SET action_reason_code = json_extract(case_action_reason, '$.code'), "
                "action_reason_text = json_extract(case_action_reason, '$.text') "
                "WHERE case_action_reason IS NOT NULL"
            )
        )
    else:
        op.execute(
            sa.text(
                "UPDATE actions SET action_reason_code = case_action_reason->>'code', "
                "action_reason_text = case_action_reason->>'text' "
                "WHERE case_action_reason IS NOT NULL"
            )
        )

    op.drop_column("actions", "case_action_reason")
    op.drop_column("actions", "log_final_action")
    op.drop_column("actions", "case_action_choice")

    op.add_column(
        "participants", sa.Column("specialty", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "participants", sa.Column("training_level", sa.String(length=64), nullable=True)
    )
    op.add_column("participants", sa.Column("years_practice", sa.Integer(), nullable=True))
    op.add_column(
        "participants", sa.Column("weekly_message_volume", sa.String(length=32), nullable=True)
    )
    op.add_column("participants", sa.Column("ai_familiarity", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE participants SET specialty = pre_specialty, "
            "training_level = pre_training_level, years_practice = pre_years_post_residency, "
            "weekly_message_volume = pre_weekly_msg_volume, "
            "ai_familiarity = pre_ai_drafting_familiarity"
        )
    )
    op.drop_column("participants", "pre_specialty")
    op.drop_column("participants", "pre_training_level")
    op.drop_column("participants", "pre_years_post_residency")
    op.drop_column("participants", "pre_weekly_msg_volume")
    op.drop_column("participants", "pre_ai_drafting_familiarity")
