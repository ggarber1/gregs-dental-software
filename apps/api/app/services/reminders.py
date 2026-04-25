from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.appointment_reminder import AppointmentReminder

logger = logging.getLogger(__name__)

_REMINDER_WINDOWS_HOURS: tuple[int, ...] = (48, 24)


def _build_reminder_row(
    appointment: Appointment,
    hours_before: int,
    reminder_type: str,
) -> AppointmentReminder | None:
    send_at = appointment.start_time - timedelta(hours=hours_before)
    if send_at <= datetime.now(UTC):
        return None
    return AppointmentReminder(
        id=uuid.uuid4(),
        practice_id=appointment.practice_id,
        appointment_id=appointment.id,
        patient_id=appointment.patient_id,
        reminder_type=reminder_type,
        hours_before=hours_before,
        send_at=send_at,
        status="pending",
    )


_REMINDER_TYPES: tuple[str, ...] = ("sms", "email")


def stage_reminder_jobs(
    session: AsyncSession, appointment: Appointment
) -> list[AppointmentReminder]:
    """Add pending AppointmentReminder rows to the session. Caller must commit."""
    if appointment.patient_id is None:
        return []

    created: list[AppointmentReminder] = []
    for hours in _REMINDER_WINDOWS_HOURS:
        for reminder_type in _REMINDER_TYPES:
            row = _build_reminder_row(appointment, hours, reminder_type)
            if row is not None:
                session.add(row)
                created.append(row)
    return created


async def cancel_reminders_for_appointment(
    session: AsyncSession, appointment_id: uuid.UUID
) -> None:
    """Cancel all pending/enqueued reminders for an appointment."""
    await session.execute(
        update(AppointmentReminder)
        .where(
            AppointmentReminder.appointment_id == appointment_id,
            AppointmentReminder.status.in_(("pending", "enqueued")),
            AppointmentReminder.deleted_at.is_(None),
        )
        .values(status="cancelled", updated_at=func.now())
    )
    logger.info("Cancelled reminders for appointment %s", appointment_id)
