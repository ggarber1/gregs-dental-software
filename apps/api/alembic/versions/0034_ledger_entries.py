"""Patient ledger (Module 8a) — append-only ledger_entries

Revision ID: 0034
Revises: 0033
Create Date: 2026-06-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0034"
down_revision: str | Sequence[str] | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("guarantor_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entry_type", sa.String(20), nullable=False),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("appointment_procedure_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("remittance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reverses_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payment_method", sa.String(20), nullable=True),
        sa.Column("memo", sa.Text, nullable=True),
        sa.Column("posted_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column(
            "posted_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
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
        sa.CheckConstraint(
            "entry_type IN ('charge', 'insurance_payment', 'patient_payment', 'adjustment')",
            name="ck_ledger_entries_entry_type",
        ),
        sa.CheckConstraint(
            "payment_method IS NULL OR ("
            "entry_type = 'patient_payment' AND payment_method IN "
            "('cash', 'check', 'card', 'external_terminal', 'other'))",
            name="ck_ledger_entries_payment_method",
        ),
    )
    op.create_index(
        "ix_ledger_entries_patient_posted", "ledger_entries", ["patient_id", "posted_at"]
    )
    op.create_index(
        "ix_ledger_entries_practice_deleted", "ledger_entries", ["practice_id", "deleted_at"]
    )
    op.create_index(
        "ix_ledger_entries_proc_charge",
        "ledger_entries",
        ["appointment_procedure_id"],
        postgresql_where=sa.text("entry_type = 'charge'"),
    )
    op.create_index("ix_ledger_entries_appointment", "ledger_entries", ["appointment_id"])


def downgrade() -> None:
    op.drop_table("ledger_entries")
