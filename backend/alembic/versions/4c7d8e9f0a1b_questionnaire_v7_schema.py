"""questionnaire v7: participant fields, case_surveys columns, action reason

Revision ID: 4c7d8e9f0a1b
Revises: 3a9c1b2d4e5f
Create Date: 2026-05-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "4c7d8e9f0a1b"
down_revision: Union[str, Sequence[str], None] = "3a9c1b2d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "actions",
        sa.Column("action_reason_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "actions",
        sa.Column("action_reason_text", sa.Text(), nullable=True),
    )

    op.add_column(
        "case_surveys",
        sa.Column("case_decision_confidence", sa.Integer(), nullable=True),
    )
    op.add_column(
        "case_surveys",
        sa.Column("case_draft_helpfulness", sa.Integer(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE case_surveys SET case_decision_confidence = confidence_in_judgment, "
            "case_draft_helpfulness = ai_draft_helpful"
        )
    )
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("case_surveys") as batch_op:
            batch_op.alter_column(
                "case_decision_confidence",
                existing_type=sa.Integer(),
                nullable=False,
            )
            batch_op.alter_column(
                "case_draft_helpfulness",
                existing_type=sa.Integer(),
                nullable=False,
            )
    else:
        op.alter_column(
            "case_surveys",
            "case_decision_confidence",
            existing_type=sa.Integer(),
            nullable=False,
        )
        op.alter_column(
            "case_surveys",
            "case_draft_helpfulness",
            existing_type=sa.Integer(),
            nullable=False,
        )
    op.drop_column("case_surveys", "safe_to_send")
    op.drop_column("case_surveys", "confidence_in_judgment")
    op.drop_column("case_surveys", "ai_draft_helpful")

    op.drop_column("participants", "prior_ai_use")
    op.drop_column("participants", "ai_brands_used")


def downgrade() -> None:
    op.add_column(
        "participants",
        sa.Column("prior_ai_use", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "participants",
        sa.Column("ai_brands_used", sa.JSON(), nullable=True),
    )

    op.add_column(
        "case_surveys",
        sa.Column("safe_to_send", sa.Integer(), nullable=True),
    )
    op.add_column(
        "case_surveys",
        sa.Column("confidence_in_judgment", sa.Integer(), nullable=True),
    )
    op.add_column(
        "case_surveys",
        sa.Column("ai_draft_helpful", sa.Integer(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE case_surveys SET confidence_in_judgment = case_decision_confidence, "
            "ai_draft_helpful = case_draft_helpfulness, safe_to_send = 3"
        )
    )
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("case_surveys") as batch_op:
            batch_op.alter_column(
                "safe_to_send",
                existing_type=sa.Integer(),
                nullable=False,
            )
            batch_op.alter_column(
                "confidence_in_judgment",
                existing_type=sa.Integer(),
                nullable=False,
            )
            batch_op.alter_column(
                "ai_draft_helpful",
                existing_type=sa.Integer(),
                nullable=False,
            )
    else:
        op.alter_column(
            "case_surveys",
            "safe_to_send",
            existing_type=sa.Integer(),
            nullable=False,
        )
        op.alter_column(
            "case_surveys",
            "confidence_in_judgment",
            existing_type=sa.Integer(),
            nullable=False,
        )
        op.alter_column(
            "case_surveys",
            "ai_draft_helpful",
            existing_type=sa.Integer(),
            nullable=False,
        )
    op.drop_column("case_surveys", "case_decision_confidence")
    op.drop_column("case_surveys", "case_draft_helpfulness")

    op.drop_column("actions", "action_reason_text")
    op.drop_column("actions", "action_reason_code")
