from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin

ENTRY_TYPES = ("charge", "insurance_payment", "patient_payment", "adjustment")
PAYMENT_METHODS = ("cash", "check", "card", "external_terminal", "other")


class LedgerEntry(Base, PHIMixin):
    """One immutable financial event on a patient's ledger.

    Money is integer cents, **signed**: charge is positive (patient owes more);
    payments and adjustments are negative (patient owes less). Corrections are made
    by posting a reversing entry (`reverses_entry_id` set, sign flipped) — rows are
    never UPDATEd or hard-deleted. Running balance = SUM(amount_cents) per patient.
    """

    __tablename__ = "ledger_entries"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Reserved for future family/guarantor billing (Module 8b); unused in 8a.
    guarantor_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    appointment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    appointment_procedure_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    claim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    remittance_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reverses_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    payment_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_by: Mapped[str] = mapped_column(String(255), nullable=False, server_default="system")
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('charge', 'insurance_payment', 'patient_payment', 'adjustment')",
            name="ck_ledger_entries_entry_type",
        ),
        CheckConstraint(
            "payment_method IS NULL OR ("
            "entry_type = 'patient_payment' AND payment_method IN "
            "('cash', 'check', 'card', 'external_terminal', 'other'))",
            name="ck_ledger_entries_payment_method",
        ),
        Index("ix_ledger_entries_patient_posted", "patient_id", "posted_at"),
        Index("ix_ledger_entries_practice_deleted", "practice_id", "deleted_at"),
        Index(
            "ix_ledger_entries_proc_charge",
            "appointment_procedure_id",
            postgresql_where=text("entry_type = 'charge'"),
        ),
        Index("ix_ledger_entries_appointment", "appointment_id"),
    )
