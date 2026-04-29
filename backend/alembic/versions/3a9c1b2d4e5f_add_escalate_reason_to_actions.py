"""add escalate_reason to actions

Revision ID: 3a9c1b2d4e5f
Revises: 2f60ea61eade
Create Date: 2026-04-28

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3a9c1b2d4e5f"
down_revision: Union[str, Sequence[str], None] = "2f60ea61eade"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "actions",
        sa.Column("escalate_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("actions", "escalate_reason")
