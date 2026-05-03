from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin


class ClinicalNote(Base, PHIMixin):
    __tablename__ = "clinical_notes"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    visit_date: Mapped[date] = mapped_column(Date, nullable=False)

    chief_complaint: Mapped[str | None] = mapped_column(Text, nullable=True)
    anesthesia: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_tolerance: Mapped[str | None] = mapped_column(Text, nullable=True)
    complications: Mapped[str | None] = mapped_column(Text, nullable=True)
    treatment_rendered: Mapped[str] = mapped_column(Text, nullable=False)
    next_visit_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_type: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_signed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_by_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "patient_tolerance IN ('excellent', 'good', 'fair', 'poor')",
            name="ck_clinical_notes_patient_tolerance",
        ),
        CheckConstraint(
            "template_type IN ('exam', 'prophy', 'extraction', 'crown_prep', "
            "'crown_seat', 'root_canal', 'filling', 'srp', 'other')",
            name="ck_clinical_notes_template_type",
        ),
        UniqueConstraint("appointment_id", name="uq_clinical_notes_appointment_id"),
        Index("ix_clinical_notes_patient_visit_date", "patient_id", "visit_date"),
        Index("ix_clinical_notes_appointment_id", "appointment_id"),
        Index("ix_clinical_notes_practice_visit_date", "practice_id", "visit_date"),
    )
