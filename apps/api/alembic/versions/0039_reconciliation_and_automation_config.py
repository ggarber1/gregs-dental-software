"""Add reconciliation_confirmed_at to claims; add automation_config to practices

Revision ID: 0039
Revises: 0038
Create Date: 2026-07-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0039"
down_revision: str | Sequence[str] | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("reconciliation_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "practices",
        sa.Column(
            "automation_config",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("practices", "automation_config")
    op.drop_column("claims", "reconciliation_confirmed_at")
