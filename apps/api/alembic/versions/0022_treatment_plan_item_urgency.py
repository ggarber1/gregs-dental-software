"""Add urgency column to treatment_plan_items

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "treatment_plan_items",
        sa.Column(
            "urgency",
            sa.Text,
            sa.CheckConstraint(
                "urgency IN ('urgent', 'soon', 'elective')",
                name="ck_treatment_plan_items_urgency",
            ),
            nullable=False,
            server_default="soon",
        ),
    )


def downgrade() -> None:
    op.drop_column("treatment_plan_items", "urgency")
