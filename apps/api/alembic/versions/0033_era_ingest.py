"""ERA ingest (Module 7b) — claim payment columns + era_remittances + unmatched_era_payments

Revision ID: 0033
Revises: 0032
Create Date: 2026-06-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0033"
down_revision: str | Sequence[str] | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Claim payment columns (auto-post target)
    op.add_column("claims", sa.Column("insurance_paid_cents", sa.Integer, nullable=True))
    op.add_column("claims", sa.Column("patient_responsibility_cents", sa.Integer, nullable=True))
    op.add_column("claims", sa.Column("payer_claim_control_number", sa.String(50), nullable=True))
    op.add_column("claims", sa.Column("adjustments", postgresql.JSONB, nullable=True))
    op.add_column("claims", sa.Column("denial_codes", postgresql.ARRAY(sa.Text), nullable=True))
    op.add_column("claims", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "claims", sa.Column("remittance_id", postgresql.UUID(as_uuid=True), nullable=True)
    )

    op.create_table(
        "era_remittances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stedi_transaction_id", sa.String(64), nullable=False),
        sa.Column("payer_name", sa.String(200), nullable=True),
        sa.Column("trace_number", sa.String(50), nullable=True),
        sa.Column("payment_cents", sa.Integer, nullable=True),
        sa.Column("payment_date", sa.Date, nullable=True),
        sa.Column("claim_count", sa.Integer, nullable=True),
        sa.Column("matched_count", sa.Integer, nullable=True),
        sa.Column("unmatched_count", sa.Integer, nullable=True),
        sa.Column("raw_response", postgresql.JSONB, nullable=False),
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
    op.create_unique_constraint(
        "uq_era_remittances_stedi_txn", "era_remittances", ["stedi_transaction_id"]
    )
    op.create_index(
        "ix_era_remittances_practice_deleted", "era_remittances", ["practice_id", "deleted_at"]
    )

    op.create_table(
        "unmatched_era_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("remittance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_control_number", sa.String(50), nullable=True),
        sa.Column("payer_claim_control_number", sa.String(50), nullable=True),
        sa.Column("paid_cents", sa.Integer, nullable=True),
        sa.Column("raw_claim_payment", postgresql.JSONB, nullable=False),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        "ix_unmatched_era_practice_resolved", "unmatched_era_payments", ["practice_id", "resolved"]
    )
    op.create_index("ix_unmatched_era_remittance", "unmatched_era_payments", ["remittance_id"])


def downgrade() -> None:
    op.drop_table("unmatched_era_payments")
    op.drop_table("era_remittances")
    for col in (
        "remittance_id", "paid_at", "denial_codes", "adjustments",
        "payer_claim_control_number", "patient_responsibility_cents", "insurance_paid_cents",
    ):
        op.drop_column("claims", col)
