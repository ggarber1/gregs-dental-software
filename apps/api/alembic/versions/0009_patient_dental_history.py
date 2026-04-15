"""Add last_dental_visit and previous_dentist to patients

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-14

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "patients",
        sa.Column("last_dental_visit", sa.Text(), nullable=True),
    )
    op.add_column(
        "patients",
        sa.Column("previous_dentist", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("patients", "previous_dentist")
    op.drop_column("patients", "last_dental_visit")
