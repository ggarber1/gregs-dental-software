"""Add submission_history and claim_frequency_code to claims (claim recovery)

Revision ID: 0037
Revises: 0036
Create Date: 2026-06-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0037"
down_revision: str | Sequence[str] | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("submission_history", JSONB, nullable=True),
    )
    op.add_column(
        "claims",
        sa.Column(
            "claim_frequency_code",
            sa.String(2),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("claims", "claim_frequency_code")
    op.drop_column("claims", "submission_history")
