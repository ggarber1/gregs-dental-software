from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.patient import Patient
    from app.models.practice import Practice


class AppointmentReminder(Base, TimestampMixin):
    __tablename__ = "appointment_reminders"

    practice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("practices.id", ondelete="CASCADE"),
        nullable=False,
    )
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
    )
    reminder_type: Mapped[str] = mapped_column(String(10), nullable=False)
    hours_before: Mapped[int] = mapped_column(Integer, nullable=False)
    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    sqs_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    twilio_message_sid: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_received: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("reminder_type IN ('sms', 'email')", name="ck_reminders_type"),
        CheckConstraint(
            "status IN ('pending', 'enqueued', 'sent', 'failed', 'cancelled')",
            name="ck_reminders_status",
        ),
        Index("ix_appointment_reminders_appointment_id", "appointment_id"),
        Index("ix_appointment_reminders_status_send_at", "status", "send_at"),
        Index(
            "ix_appointment_reminders_practice_appointment",
            "practice_id",
            "appointment_id",
        ),
    )

    practice: Mapped[Practice] = relationship("Practice")
    appointment: Mapped[Appointment] = relationship("Appointment")
    patient: Mapped[Patient] = relationship("Patient")
