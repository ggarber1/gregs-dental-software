"""Add reminder_hours JSONB column to practices

Revision ID: 0014b
Revises: 0013
Create Date: 2026-04-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0014b"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "practices",
        sa.Column(
            "reminder_hours",
            JSONB,
            nullable=False,
            server_default="[48, 24]",
        ),
    )


def downgrade() -> None:
    op.drop_column("practices", "reminder_hours")
