"""Add surfaces array to tooth_conditions

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Normalized per-surface flags. Values are single-letter surface codes:
    #   B = buccal, M = mesial, O = occlusal, D = distal, L = lingual,
    #   I = incisal (anterior teeth only).
    # The legacy free-text `surface` column is kept intact for back-compat
    # with rows recorded before normalization (e.g. "MOD").
    op.add_column(
        "tooth_conditions",
        sa.Column(
            "surfaces",
            postgresql.ARRAY(sa.Text),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tooth_conditions", "surfaces")
