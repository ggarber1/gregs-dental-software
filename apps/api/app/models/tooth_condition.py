from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, Index, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin


class ToothCondition(Base, PHIMixin):
    __tablename__ = "tooth_conditions"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    tooth_number: Mapped[str] = mapped_column(Text, nullable=False)
    notation_system: Mapped[str] = mapped_column(Text, nullable=False, server_default="universal")

    condition_type: Mapped[str] = mapped_column(Text, nullable=False)
    # Legacy free-text notation (e.g. "MOD") — kept for back-compat with rows
    # written before per-surface normalization.
    surface: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Normalized per-surface flags: any subset of B, M, O, D, L, I.
    surfaces: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
        default=list,
    )
    material: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="existing")
    # Vertical position: crown (default), cervical (Class V), or root caries.
    vertical_zone: Mapped[str] = mapped_column(Text, nullable=False, server_default="crown")

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
        CheckConstraint(
            "vertical_zone IN ('crown', 'cervical', 'root')",
            name="ck_tooth_conditions_vertical_zone",
        ),
        Index("ix_tooth_conditions_patient_recorded_at", "patient_id", "recorded_at"),
        Index("ix_tooth_conditions_patient_tooth_number", "patient_id", "tooth_number"),
        Index("ix_tooth_conditions_appointment_id", "appointment_id"),
    )
