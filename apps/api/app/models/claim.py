from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin

# 7a writes: draft | submitted | clearinghouse_rejected | submission_failed
# Reserved for 7b / status-polling worker:
#   acknowledged | pending | paid | partially_paid | denied | appealing
_CLAIM_STATUSES = (
    "draft",
    "submitted",
    "clearinghouse_rejected",
    "submission_failed",
    "acknowledged",
    "pending",
    "paid",
    "partially_paid",
    "denied",
    "appealing",
)


class Claim(Base, PHIMixin):
    """One 837D dental claim for an appointment's procedures, billed to primary insurance.

    Holds PHI -> PHIMixin. Money is integer cents. The full status enum is defined
    in the check constraint so Module 7b and the status-polling worker never migrate;
    7a only writes draft/submitted/clearinghouse_rejected/submission_failed.
    """

    __tablename__ = "claims"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    insurance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    submission_attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    patient_control_number: Mapped[str] = mapped_column(String(38), nullable=False)
    payer_id: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")

    total_charge_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    clearinghouse_claim_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    clearinghouse_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    submission_errors: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    raw_submission: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Module 7b: ERA auto-post (claim-level) ---
    insurance_paid_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    patient_responsibility_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payer_claim_control_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    adjustments: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    denial_codes: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remittance_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    insurance_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'submitted', 'clearinghouse_rejected', 'submission_failed', "
            "'acknowledged', 'pending', 'paid', 'partially_paid', 'denied', 'appealing')",
            name="ck_claims_status",
        ),
        UniqueConstraint("idempotency_key", name="uq_claims_idempotency_key"),
        UniqueConstraint("patient_control_number", "payer_id", name="uq_claims_pcn_payer"),
        Index("ix_claims_appointment_id", "appointment_id"),
        Index("ix_claims_status", "status"),
        Index("ix_claims_patient_control_number", "patient_control_number"),
        Index("ix_claims_practice_deleted", "practice_id", "deleted_at"),
    )
