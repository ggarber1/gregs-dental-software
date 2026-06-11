"""Eligibility checks (real-time insurance verification results)

Revision ID: 0027
Revises: 0026
Create Date: 2026-06-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eligibility_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_insurance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("trigger", sa.String(30), nullable=False, server_default="manual"),
        sa.Column("clearinghouse", sa.String(20), nullable=False),
        sa.Column("payer_id_used", sa.String(50), nullable=False),
        sa.Column("payer_name", sa.String(255), nullable=True),
        sa.Column("plan_name", sa.String(255), nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("coverage_status", sa.String(10), nullable=True),
        sa.Column("coverage_start_date", sa.Date, nullable=True),
        sa.Column("coverage_end_date", sa.Date, nullable=True),
        sa.Column("deductible_individual", sa.Integer, nullable=True),
        sa.Column("deductible_individual_met", sa.Integer, nullable=True),
        sa.Column("deductible_family", sa.Integer, nullable=True),
        sa.Column("deductible_family_met", sa.Integer, nullable=True),
        sa.Column("oop_max_individual", sa.Integer, nullable=True),
        sa.Column("oop_max_individual_met", sa.Integer, nullable=True),
        sa.Column("annual_max_individual", sa.Integer, nullable=True),
        sa.Column("annual_max_individual_used", sa.Integer, nullable=True),
        sa.Column("annual_max_individual_remaining", sa.Integer, nullable=True),
        sa.Column("coinsurance_preventive", sa.Numeric(5, 4), nullable=True),
        sa.Column("coinsurance_basic", sa.Numeric(5, 4), nullable=True),
        sa.Column("coinsurance_major", sa.Numeric(5, 4), nullable=True),
        sa.Column("coinsurance_ortho", sa.Numeric(5, 4), nullable=True),
        sa.Column("waiting_period_basic_months", sa.Integer, nullable=True),
        sa.Column("waiting_period_major_months", sa.Integer, nullable=True),
        sa.Column("waiting_period_ortho_months", sa.Integer, nullable=True),
        sa.Column("frequency_limits", postgresql.JSONB, nullable=True),
        sa.Column("raw_response", postgresql.JSONB, nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','verified','failed','not_supported')",
            name="ck_eligibility_checks_status",
        ),
        sa.CheckConstraint(
            "trigger IN ('manual','pre_appointment_batch')",
            name="ck_eligibility_checks_trigger",
        ),
        sa.CheckConstraint(
            "clearinghouse IN ('stedi','dentalxchange','manual')",
            name="ck_eligibility_checks_clearinghouse",
        ),
    )
    op.create_index(
        "uq_eligibility_checks_idempotency", "eligibility_checks",
        ["idempotency_key"], unique=True,
    )
    op.create_index(
        "ix_eligibility_checks_practice_patient", "eligibility_checks",
        ["practice_id", "patient_id"],
    )
    op.create_index(
        "ix_eligibility_checks_patient_insurance", "eligibility_checks",
        ["patient_insurance_id"],
    )
    op.create_index(
        "ix_eligibility_checks_pending", "eligibility_checks", ["status"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_table("eligibility_checks")
