"""Add vertical_zone to tooth_conditions

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Vertical position on the tooth. Most caries are crown-level (default),
    # but cervical (Class V, at the gumline) and root caries change treatment
    # and prognosis enough that they're worth distinguishing on the chart.
    op.add_column(
        "tooth_conditions",
        sa.Column(
            "vertical_zone",
            sa.Text,
            sa.CheckConstraint(
                "vertical_zone IN ('crown', 'cervical', 'root')",
                name="ck_tooth_conditions_vertical_zone",
            ),
            nullable=False,
            server_default="crown",
        ),
    )


def downgrade() -> None:
    op.drop_column("tooth_conditions", "vertical_zone")
