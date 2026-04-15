from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.appointment_type import AppointmentType
    from app.models.operatory import Operatory
    from app.models.patient import Patient
    from app.models.practice import Practice
    from app.models.provider import Provider


class Appointment(Base, TimestampMixin):
    __tablename__ = "appointments"

    practice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("practices.id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("providers.id", ondelete="SET NULL"),
        nullable=True,
    )
    operatory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("operatories.id", ondelete="SET NULL"),
        nullable=True,
    )
    appointment_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appointment_types.id", ondelete="SET NULL"),
        nullable=True,
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="scheduled",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('scheduled', 'confirmed', 'checked_in', 'in_chair', "
            "'completed', 'cancelled', 'no_show')",
            name="ck_appointments_status",
        ),
        CheckConstraint(
            "end_time > start_time",
            name="ck_appointments_end_after_start",
        ),
        Index("ix_appointments_practice_start_end", "practice_id", "start_time", "end_time"),
        Index("ix_appointments_provider_start_end", "provider_id", "start_time", "end_time"),
        Index("ix_appointments_operatory_start_end", "operatory_id", "start_time", "end_time"),
        Index("ix_appointments_patient_id", "patient_id"),
        Index("ix_appointments_practice_status", "practice_id", "status"),
    )

    practice: Mapped[Practice] = relationship("Practice", back_populates="appointments")
    patient: Mapped[Patient | None] = relationship("Patient")
    provider: Mapped[Provider | None] = relationship("Provider")
    operatory: Mapped[Operatory | None] = relationship("Operatory")
    appointment_type: Mapped[AppointmentType | None] = relationship("AppointmentType")
