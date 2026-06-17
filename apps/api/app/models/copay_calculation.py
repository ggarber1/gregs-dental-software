from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin


class CopayCalculation(Base, PHIMixin):
    """Snapshot of one co-pay calculation run for an appointment (audit + override)."""

    __tablename__ = "copay_calculations"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    eligibility_check_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    plan_type: Mapped[str] = mapped_column(String(20), nullable=False)
    total_provider_fee_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    total_write_off_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    total_insurance_owes_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    total_patient_owes_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    deductible_remaining_after_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    annual_max_remaining_after_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    override_patient_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    override_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    line_items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    has_secondary_insurance: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    __table_args__ = (
        Index("ix_copay_calculations_appointment_id", "appointment_id"),
    )
