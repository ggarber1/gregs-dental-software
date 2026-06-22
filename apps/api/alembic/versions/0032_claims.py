"""claims table (Module 7a — 837D submission)

Revision ID: 0032
Revises: 0031
Create Date: 2026-06-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0032"
down_revision: str | Sequence[str] | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("insurance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("submission_attempt", sa.Integer, nullable=False, server_default="1"),
        sa.Column("patient_control_number", sa.String(38), nullable=False),
        sa.Column("payer_id", sa.String(20), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("total_charge_cents", sa.Integer, nullable=False),
        sa.Column("clearinghouse_claim_id", sa.String(64), nullable=True),
        sa.Column("clearinghouse_status", sa.String(50), nullable=True),
        sa.Column("submission_errors", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("raw_submission", postgresql.JSONB, nullable=True),
        sa.Column("raw_response", postgresql.JSONB, nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_check_constraint(
        "ck_claims_status",
        "claims",
        "status IN ('draft', 'submitted', 'clearinghouse_rejected', 'submission_failed', "
        "'acknowledged', 'pending', 'paid', 'partially_paid', 'denied', 'appealing')",
    )
    op.create_unique_constraint("uq_claims_idempotency_key", "claims", ["idempotency_key"])
    op.create_unique_constraint(
        "uq_claims_pcn_payer", "claims", ["patient_control_number", "payer_id"]
    )
    op.create_index("ix_claims_appointment_id", "claims", ["appointment_id"])
    op.create_index("ix_claims_status", "claims", ["status"])
    op.create_index("ix_claims_patient_control_number", "claims", ["patient_control_number"])
    op.create_index("ix_claims_practice_deleted", "claims", ["practice_id", "deleted_at"])


def downgrade() -> None:
    op.drop_table("claims")
