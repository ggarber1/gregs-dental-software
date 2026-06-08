from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin, TimestampMixin


class CdtCode(Base, TimestampMixin):
    __tablename__ = "cdt_codes"

    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    default_fee_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    __table_args__ = (
        CheckConstraint(
            "category IN ('diagnostic', 'preventive', 'basic', 'major', 'ortho', 'other')",
            name="ck_cdt_codes_category",
        ),
    )


class AppointmentProcedure(Base, PHIMixin):
    __tablename__ = "appointment_procedures"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    cdt_code_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    procedure_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    procedure_name: Mapped[str] = mapped_column(Text, nullable=False)
    tooth_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    surface: Mapped[str | None] = mapped_column(Text, nullable=True)
    fee_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    insurance_est_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    patient_est_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimate_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "cdt_code_id IS NOT NULL OR procedure_code IS NOT NULL",
            name="ck_appointment_procedures_code_present",
        ),
        CheckConstraint(
            "estimate_source IS NULL OR "
            "estimate_source IN ('manual', 'eligibility', 'prior_eob')",
            name="ck_appointment_procedures_estimate_source",
        ),
        Index("ix_appointment_procedures_appointment_id", "appointment_id"),
        Index("ix_appointment_procedures_patient_created_at", "patient_id", "created_at"),
        Index("ix_appointment_procedures_cdt_code_id", "cdt_code_id"),
    )
