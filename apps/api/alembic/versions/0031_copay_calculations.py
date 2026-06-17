"""copay_calculations snapshot table

Revision ID: 0031
Revises: 0030
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0031"
down_revision: str | Sequence[str] | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "copay_calculations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("eligibility_check_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("plan_type", sa.String(20), nullable=False),
        sa.Column("total_provider_fee_cents", sa.Integer, nullable=False),
        sa.Column("total_write_off_cents", sa.Integer, nullable=False),
        sa.Column("total_insurance_owes_cents", sa.Integer, nullable=False),
        sa.Column("total_patient_owes_cents", sa.Integer, nullable=False),
        sa.Column("deductible_remaining_after_cents", sa.Integer, nullable=True),
        sa.Column("annual_max_remaining_after_cents", sa.Integer, nullable=True),
        sa.Column("override_patient_cents", sa.Integer, nullable=True),
        sa.Column("override_note", sa.Text, nullable=True),
        sa.Column("overridden_by", sa.String(255), nullable=True),
        sa.Column("line_items", postgresql.JSONB, nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=False),
        sa.Column("has_secondary_insurance", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_by", sa.String(255), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_copay_calculations_appointment_id", "copay_calculations", ["appointment_id"]
    )
    op.create_index(
        "uq_copay_calculations_idempotency_key",
        "copay_calculations", ["idempotency_key"], unique=True,
    )


def downgrade() -> None:
    op.drop_table("copay_calculations")
