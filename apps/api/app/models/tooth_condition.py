from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin


class ToothCondition(Base, PHIMixin):
    __tablename__ = "tooth_conditions"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    tooth_number: Mapped[str] = mapped_column(Text, nullable=False)
    notation_system: Mapped[str] = mapped_column(Text, nullable=False, server_default="universal")

    condition_type: Mapped[str] = mapped_column(Text, nullable=False)
    surface: Mapped[str | None] = mapped_column(Text, nullable=True)
    material: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="existing")

    recorded_at: Mapped[date] = mapped_column(Date, nullable=False)
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "notation_system IN ('universal', 'fdi')",
            name="ck_tooth_conditions_notation_system",
        ),
        CheckConstraint(
            "condition_type IN ('existing_restoration', 'missing', 'implant', 'crown', "
            "'bridge_pontic', 'bridge_abutment', 'root_canal', 'decay', 'fracture', "
            "'watch', 'other')",
            name="ck_tooth_conditions_condition_type",
        ),
        CheckConstraint(
            "status IN ('existing', 'treatment_planned', 'completed_today')",
            name="ck_tooth_conditions_status",
        ),
        Index("ix_tooth_conditions_patient_recorded_at", "patient_id", "recorded_at"),
        Index("ix_tooth_conditions_patient_tooth_number", "patient_id", "tooth_number"),
        Index("ix_tooth_conditions_appointment_id", "appointment_id"),
    )
