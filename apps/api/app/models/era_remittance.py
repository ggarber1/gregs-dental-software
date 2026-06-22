from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin


class ERARemittance(Base, PHIMixin):
    """One ingested 835 ERA (a Stedi remittance transaction).

    Holds PHI -> PHIMixin. `stedi_transaction_id` is the dedup key: re-polling never
    re-ingests or double-posts. `raw_response` keeps the full Stedi JSON so nothing
    is lost even though we post claim-level only.
    """

    __tablename__ = "era_remittances"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    stedi_transaction_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    trace_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payment_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    claim_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matched_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unmatched_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint("stedi_transaction_id", name="uq_era_remittances_stedi_txn"),
        Index("ix_era_remittances_practice_deleted", "practice_id", "deleted_at"),
    )


class UnmatchedERAPayment(Base, PHIMixin):
    """A claim payment (CLP) in an ERA with no matching claim — manual review queue.

    Never silently dropped. `resolved` is cleared by an operator who handled it
    manually (Phase 1 does not re-match to a chosen claim — that is deferred).
    """

    __tablename__ = "unmatched_era_payments"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    remittance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_control_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payer_claim_control_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    paid_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_claim_payment: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_unmatched_era_practice_resolved", "practice_id", "resolved"),
        Index("ix_unmatched_era_remittance", "remittance_id"),
    )
