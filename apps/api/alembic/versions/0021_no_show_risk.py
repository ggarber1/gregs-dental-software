"""Add no_show_risk columns to appointments

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column(
            "no_show_risk",
            sa.Text,
            sa.CheckConstraint(
                "no_show_risk IN ('low', 'medium', 'high')",
                name="ck_appointments_no_show_risk",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "appointments",
        sa.Column("no_show_risk_computed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("appointments", "no_show_risk_computed_at")
    op.drop_column("appointments", "no_show_risk")
