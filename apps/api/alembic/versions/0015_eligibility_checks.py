"""Eligibility checks table for clearinghouse 270/271 verification

Revision ID: 0015
Revises: 0014, 0014b
Create Date: 2026-04-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = ("0014", "0014b")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eligibility_checks",
        # ── Primary key ────────────────────────────────────────────────────
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # ── Practice / patient scope ───────────────────────────────────────
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_insurance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
        # ── Workflow ───────────────────────────────────────────────────────
        sa.Column("idempotency_key", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("trigger", sa.String(30), nullable=False),
        sa.Column("clearinghouse", sa.String(20), nullable=False),
        sa.Column("payer_id_used", sa.String(50), nullable=False),
        sa.Column("payer_name", sa.String(255), nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
        # ── Coverage summary ───────────────────────────────────────────────
        sa.Column("coverage_status", sa.String(20), nullable=True),
        sa.Column("coverage_start_date", sa.Date, nullable=True),
        sa.Column("coverage_end_date", sa.Date, nullable=True),
        # ── Deductibles ────────────────────────────────────────────────────
        sa.Column("deductible_individual", sa.Numeric(10, 2), nullable=True),
        sa.Column("deductible_individual_met", sa.Numeric(10, 2), nullable=True),
        sa.Column("deductible_family", sa.Numeric(10, 2), nullable=True),
        sa.Column("deductible_family_met", sa.Numeric(10, 2), nullable=True),
        # ── Out-of-pocket max ──────────────────────────────────────────────
        sa.Column("oop_max_individual", sa.Numeric(10, 2), nullable=True),
        sa.Column("oop_max_individual_met", sa.Numeric(10, 2), nullable=True),
        # ── Annual maximum ─────────────────────────────────────────────────
        sa.Column("annual_max_individual", sa.Numeric(10, 2), nullable=True),
        sa.Column("annual_max_individual_used", sa.Numeric(10, 2), nullable=True),
        sa.Column("annual_max_individual_remaining", sa.Numeric(10, 2), nullable=True),
        # ── Coinsurance (patient share: 0.20 = patient pays 20%) ──────────
        sa.Column("coinsurance_preventive", sa.Numeric(5, 4), nullable=True),
        sa.Column("coinsurance_basic", sa.Numeric(5, 4), nullable=True),
        sa.Column("coinsurance_major", sa.Numeric(5, 4), nullable=True),
        sa.Column("coinsurance_ortho", sa.Numeric(5, 4), nullable=True),
        # ── Waiting periods ────────────────────────────────────────────────
        sa.Column("waiting_period_basic_months", sa.Integer, nullable=True),
        sa.Column("waiting_period_major_months", sa.Integer, nullable=True),
        sa.Column("waiting_period_ortho_months", sa.Integer, nullable=True),
        # ── Frequency limits (flexible JSONB) ──────────────────────────────
        sa.Column("frequency_limits", postgresql.JSONB, nullable=True),
        # ── Full raw clearinghouse response ────────────────────────────────
        sa.Column("raw_response", postgresql.JSONB, nullable=False),
        # ── Workflow timestamps ────────────────────────────────────────────
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        # ── PHI audit columns ──────────────────────────────────────────────
        sa.Column("last_accessed_by", sa.String(255), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        # ── Standard timestamps ────────────────────────────────────────────
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # ── Check constraints ──────────────────────────────────────────────
        sa.CheckConstraint(
            "status IN ('pending', 'verified', 'failed', 'not_supported')",
            name="ck_eligibility_checks_status",
        ),
        sa.CheckConstraint(
            "trigger IN ('manual', 'pre_appointment_batch')",
            name="ck_eligibility_checks_trigger",
        ),
        sa.CheckConstraint(
            "coverage_status IN ('active', 'inactive', 'unknown') OR coverage_status IS NULL",
            name="ck_eligibility_checks_coverage_status",
        ),
    )

    op.create_index(
        "ix_eligibility_checks_idempotency_key",
        "eligibility_checks",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_eligibility_checks_patient_id",
        "eligibility_checks",
        ["patient_id"],
    )
    op.create_index(
        "ix_eligibility_checks_appointment_id",
        "eligibility_checks",
        ["appointment_id"],
    )
    op.create_index(
        "ix_eligibility_checks_practice_patient",
        "eligibility_checks",
        ["practice_id", "patient_id"],
    )
    op.create_index(
        "ix_eligibility_checks_practice_deleted",
        "eligibility_checks",
        ["practice_id", "deleted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_eligibility_checks_practice_deleted", table_name="eligibility_checks")
    op.drop_index("ix_eligibility_checks_practice_patient", table_name="eligibility_checks")
    op.drop_index("ix_eligibility_checks_appointment_id", table_name="eligibility_checks")
    op.drop_index("ix_eligibility_checks_patient_id", table_name="eligibility_checks")
    op.drop_index("ix_eligibility_checks_idempotency_key", table_name="eligibility_checks")
    op.drop_table("eligibility_checks")
