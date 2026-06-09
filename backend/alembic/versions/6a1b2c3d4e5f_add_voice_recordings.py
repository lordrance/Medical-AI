"""V4: add voice_recordings table for L1/L2/L3 open-ended audio capture

Revision ID: 6a1b2c3d4e5f
Revises: 5f0e1d2c3b4a
Create Date: 2026-05-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "6a1b2c3d4e5f"
down_revision: Union[str, Sequence[str], None] = "5f0e1d2c3b4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
    op.drop_index("ix_voice_recordings_session_question", table_name="voice_recordings")
    op.drop_index("ix_voice_recordings_session", table_name="voice_recordings")
    op.drop_table("voice_recordings")
