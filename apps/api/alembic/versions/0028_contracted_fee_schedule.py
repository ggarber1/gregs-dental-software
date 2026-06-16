"""Contracted fee schedule (per-carrier allowed amounts)

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0028"
down_revision: str | Sequence[str] | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contracted_fee_schedule",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payer_id", sa.String(50), nullable=False),
        sa.Column("cdt_code_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("allowed_amount_cents", sa.Integer, nullable=True),
        sa.Column("not_covered", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("requires_prior_auth", sa.Boolean, nullable=False, server_default="false"),
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
            name="fk_contracted_fee_schedule_cdt_code",
        ),
    )
    op.create_index(
        "ix_contracted_fee_schedule_lookup",
        "contracted_fee_schedule", ["practice_id", "payer_id"],
    )
    op.create_index(
        "uq_contracted_fee_schedule_active",
        "contracted_fee_schedule",
        ["practice_id", "payer_id", "cdt_code_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("contracted_fee_schedule")
