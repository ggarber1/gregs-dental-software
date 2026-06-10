"""Practice fee schedule (per-practice CDT fee overrides)

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "practice_fee_schedule",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cdt_code_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fee_cents", sa.Integer, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["cdt_code_id"], ["cdt_codes.id"],
            name="fk_practice_fee_schedule_cdt_code",
        ),
    )
    op.create_index(
        "ix_practice_fee_schedule_practice_id",
        "practice_fee_schedule", ["practice_id"],
    )
    op.create_index(
        "ix_practice_fee_schedule_cdt_code_id",
        "practice_fee_schedule", ["cdt_code_id"],
    )
    # At most one ACTIVE override per (practice, code); soft-deleted rows are history.
    op.create_index(
        "uq_practice_fee_schedule_active",
        "practice_fee_schedule",
        ["practice_id", "cdt_code_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("practice_fee_schedule")
