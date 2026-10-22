"""Scheduled reminder sender.

Each run claims due reminders straight from appointment_reminders (no queue), sends
them, and records the outcome. Safe to run concurrently and after crashes:
- claiming uses FOR UPDATE SKIP LOCKED, so overlapping runs never take the same row;
- a claim ("enqueued" + claimed_at) older than the lease is reclaimed by a later run;
- a reminder that already has a Twilio SID is marked sent, never sent twice;
- outcomes are written only while the row is still "enqueued", so a cancellation
  that lands mid-send wins.

Runs on AWS Lambda every 15 minutes (app.workers.lambda_handlers.reminders) or
locally with `python -m app.workers.reminder_worker` (one pass).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from app.models.appointment import Appointment
from app.models.appointment_reminder import AppointmentReminder
from app.models.patient import Patient
from app.models.practice import Practice
from app.services.email import send_email
from app.services.reminder_templates import (
    build_email_html,
    build_email_subject,
    build_email_text,
    build_sms_body,
)
from app.services.sms import send_sms

logger = logging.getLogger(__name__)

BATCH_LIMIT = 200
CLAIM_LEASE = timedelta(minutes=15)
_INACTIVE_APPOINTMENT_STATUSES = frozenset({"cancelled", "no_show"})


@dataclass
class ReminderRunSummary:
    claimed: int = 0
    sent: int = 0
    skipped: int = 0
    failed: int = 0


async def send_due_reminders(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    limit: int = BATCH_LIMIT,
    lease: timedelta = CLAIM_LEASE,
) -> ReminderRunSummary:
    """Claim up to `limit` due reminders and deliver each one."""
    now = datetime.now(UTC)
    summary = ReminderRunSummary()
    async with session_factory() as session:
        claimed_ids = await _claim_due(session, now=now, limit=limit, lease=lease)
        summary.claimed = len(claimed_ids)
        if not claimed_ids:
            return summary
        reminders = await _load_claimed(session, claimed_ids)
        for reminder in reminders:
            outcome = await _process(session, reminder, now=now)
            setattr(summary, outcome, getattr(summary, outcome) + 1)
    logger.info(
        "Reminder run: claimed=%d sent=%d skipped=%d failed=%d",
        summary.claimed,
        summary.sent,
        summary.skipped,
        summary.failed,
    )
    return summary


async def _claim_due(
    session: AsyncSession, *, now: datetime, limit: int, lease: timedelta
) -> list[uuid.UUID]:
    due = (
        select(AppointmentReminder.id)
        .where(
            AppointmentReminder.deleted_at.is_(None),
            AppointmentReminder.send_at <= now,
            or_(
                AppointmentReminder.status == "pending",
                and_(
                    AppointmentReminder.status == "enqueued",
                    AppointmentReminder.claimed_at < now - lease,
                ),
            ),
        )
        .order_by(AppointmentReminder.send_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    claimed = (
        await session.scalars(
            update(AppointmentReminder)
            .where(AppointmentReminder.id.in_(due.scalar_subquery()))
            .values(status="enqueued", claimed_at=now)
            .returning(AppointmentReminder.id)
        )
    ).all()
    await session.commit()
    return list(claimed)


async def _load_claimed(
    session: AsyncSession, reminder_ids: list[uuid.UUID]
) -> list[AppointmentReminder]:
    rows = await session.scalars(
        select(AppointmentReminder)
        .where(AppointmentReminder.id.in_(reminder_ids))
        .options(
            joinedload(AppointmentReminder.patient),
            joinedload(AppointmentReminder.appointment).joinedload(Appointment.practice),
        )
        .order_by(AppointmentReminder.send_at)
    )
    return list(rows.unique().all())


async def _process(session: AsyncSession, reminder: AppointmentReminder, *, now: datetime) -> str:
    """Deliver one claimed reminder and record the outcome. Returns the summary field."""
    appointment = reminder.appointment
    if reminder.twilio_message_sid is not None or reminder.sent_at is not None:
        # Delivered by a run that crashed before recording it.
        await _finish(session, reminder, status="sent", sent_at=reminder.sent_at or now)
        return "sent"
    if (
        appointment.deleted_at is not None
        or appointment.status in _INACTIVE_APPOINTMENT_STATUSES
        or appointment.start_time <= now
    ):
        await _finish(session, reminder, status="cancelled")
        return "skipped"
    try:
        delivered = await _deliver(reminder, reminder.patient, appointment, appointment.practice)
    except Exception as exc:
        logger.error(
            "Reminder %s (%s) delivery failed: %s", reminder.id, reminder.reminder_type, exc
        )
        await _finish(
            session, reminder, status="failed", failed_at=datetime.now(UTC), failure_reason=str(exc)
        )
        return "failed"
    if not delivered:
        # Opted out or no contact info — nothing to retry.
        await _finish(session, reminder, status="cancelled")
        return "skipped"
    await _finish(
        session,
        reminder,
        status="sent",
        sent_at=datetime.now(UTC),
        twilio_message_sid=reminder.twilio_message_sid,
    )
    return "sent"


async def _finish(session: AsyncSession, reminder: AppointmentReminder, **values: Any) -> None:
    """Record an outcome only if the row is still claimed (a cancellation wins)."""
    await session.execute(
        update(AppointmentReminder)
        .where(AppointmentReminder.id == reminder.id, AppointmentReminder.status == "enqueued")
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    await session.commit()


async def _deliver(
    reminder: AppointmentReminder,
    patient: Patient,
    appointment: Appointment,
    practice: Practice,
) -> bool:
    """Send the reminder and store the delivery ID. Returns False if skipped."""
    if reminder.reminder_type == "sms":
        return await _deliver_sms(reminder, patient, appointment, practice)
    if reminder.reminder_type == "email":
        return await _deliver_email(reminder, patient, appointment, practice)
    logger.warning("Unknown reminder_type=%s for reminder %s", reminder.reminder_type, reminder.id)
    return False


async def _deliver_sms(
    reminder: AppointmentReminder,
    patient: Patient,
    appointment: Appointment,
    practice: Practice,
) -> bool:
    if patient.sms_opt_out:
        logger.info("SMS reminder %s skipped — patient %s opted out", reminder.id, patient.id)
        return False
    if not patient.phone:
        logger.info("SMS reminder %s skipped — patient %s has no phone", reminder.id, patient.id)
        return False

    text = build_sms_body(
        patient_first_name=patient.first_name,
        practice_name=practice.name,
        appointment_start=appointment.start_time,
        practice_timezone=practice.timezone,
        hours_before=reminder.hours_before,
    )
    sid = await send_sms(patient.phone, text)
    reminder.twilio_message_sid = sid
    return True


async def _deliver_email(
    reminder: AppointmentReminder,
    patient: Patient,
    appointment: Appointment,
    practice: Practice,
) -> bool:
    if patient.email_opt_out:
        logger.info("Email reminder %s skipped — patient %s opted out", reminder.id, patient.id)
        return False
    if not patient.email:
        logger.info("Email reminder %s skipped — patient %s has no email", reminder.id, patient.id)
        return False

    subject = build_email_subject(
        practice_name=practice.name,
        appointment_start=appointment.start_time,
        practice_timezone=practice.timezone,
    )
    html = build_email_html(
        patient_first_name=patient.first_name,
        practice_name=practice.name,
        appointment_start=appointment.start_time,
        practice_timezone=practice.timezone,
        practice_phone=practice.phone,
    )
    text = build_email_text(
        patient_first_name=patient.first_name,
        practice_name=practice.name,
        appointment_start=appointment.start_time,
        practice_timezone=practice.timezone,
        practice_phone=practice.phone,
    )
    await send_email(patient.email, subject, html, text)
    return True


async def _main() -> None:
    from app.core.db import dispose_engine, get_session_factory

    try:
        await send_due_reminders(get_session_factory())
    finally:
        await dispose_engine()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
