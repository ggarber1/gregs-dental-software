from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import joinedload

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.sqs import delete_message_sync, enqueue_message_sync, poll_messages_sync
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

_SCHEDULER_INTERVAL_SECONDS = 300  # 5 minutes
_LOOK_AHEAD_MINUTES = 10


async def run() -> None:
    logger.info("Reminder worker starting")
    await asyncio.gather(
        _scheduler_loop(),
        _sqs_poll_loop(),
    )


async def _scheduler_loop() -> None:
    while True:
        try:
            await _enqueue_due_reminders()
        except Exception:
            logger.exception("Scheduler error — continuing")
        await asyncio.sleep(_SCHEDULER_INTERVAL_SECONDS)


async def _enqueue_due_reminders() -> None:
    look_ahead = datetime.now(UTC) + timedelta(minutes=_LOOK_AHEAD_MINUTES)
    queue_name = get_settings().sqs_queue_reminders
    factory: async_sessionmaker[AsyncSession] = get_session_factory()

    async with factory() as session:
        result = await session.scalars(
            select(AppointmentReminder).where(
                AppointmentReminder.status == "pending",
                AppointmentReminder.send_at <= look_ahead,
                AppointmentReminder.deleted_at.is_(None),
            )
        )
        rows = result.all()

        for row in rows:
            try:
                msg_body = {
                    "reminder_id": str(row.id),
                    "appointment_id": str(row.appointment_id),
                    "practice_id": str(row.practice_id),
                }
                msg_id = await asyncio.to_thread(enqueue_message_sync, queue_name, msg_body)
                row.sqs_message_id = msg_id
                row.status = "enqueued"
                logger.info(
                    "Enqueued reminder %s (appt %s) as SQS message %s",
                    row.id,
                    row.appointment_id,
                    msg_id,
                )
            except Exception:
                logger.exception("Failed to enqueue reminder %s", row.id)

        await session.commit()


async def _sqs_poll_loop() -> None:
    queue_name = get_settings().sqs_queue_reminders
    while True:
        try:
            messages = await asyncio.to_thread(poll_messages_sync, queue_name, wait_seconds=20)
            for msg in messages:
                await _process_message(msg)
        except Exception:
            logger.exception("SQS poll error — continuing")


async def _process_message(msg: dict[str, Any]) -> None:
    queue_name = get_settings().sqs_queue_reminders
    receipt_handle: str = msg["ReceiptHandle"]

    try:
        body = json.loads(msg["Body"])
        reminder_id = uuid.UUID(body["reminder_id"])
    except (KeyError, ValueError, json.JSONDecodeError):
        logger.error("Malformed SQS message id=%s", msg.get("MessageId"))
        await asyncio.to_thread(delete_message_sync, queue_name, receipt_handle)
        return

    factory = get_session_factory()
    async with factory() as session:
        reminder = await session.scalar(
            select(AppointmentReminder)
            .where(AppointmentReminder.id == reminder_id)
            .options(
                joinedload(AppointmentReminder.patient),
                joinedload(AppointmentReminder.appointment).joinedload(Appointment.practice),
            )
        )

        if reminder is None:
            logger.warning("Reminder %s not found — deleting SQS message", reminder_id)
            await asyncio.to_thread(delete_message_sync, queue_name, receipt_handle)
            return

        if reminder.status != "enqueued":
            logger.info(
                "Reminder %s status=%s — skipping (already sent or cancelled)",
                reminder_id,
                reminder.status,
            )
            await asyncio.to_thread(delete_message_sync, queue_name, receipt_handle)
            return

        # Idempotency: if we already stored a delivery SID this reminder was sent.
        # Guard against the case where the worker crashed after sending but before
        # deleting the SQS message.
        if reminder.twilio_message_sid is not None or reminder.sent_at is not None:
            logger.info(
                "Reminder %s already delivered — deleting duplicate SQS message", reminder_id
            )
            await asyncio.to_thread(delete_message_sync, queue_name, receipt_handle)
            return

        patient: Patient = reminder.patient
        appointment: Appointment = reminder.appointment
        practice: Practice = appointment.practice

        try:
            delivered = await _deliver(reminder, patient, appointment, practice)
        except Exception as exc:
            # Delivery failed (e.g. Twilio/SES API error). Mark as failed so the
            # status is visible in the DB, but do NOT delete the SQS message — the
            # visibility timeout will expire and the message redelivered for a retry.
            # DLQ will catch repeated failures after maxReceiveCount is exceeded.
            reminder.status = "failed"
            reminder.failed_at = datetime.now(UTC)
            reminder.failure_reason = str(exc)
            await session.commit()
            logger.error(
                "Delivery failed for reminder %s (type=%s): %s",
                reminder_id,
                reminder.reminder_type,
                exc,
            )
            return  # intentionally skip SQS delete

        if delivered:
            reminder.status = "sent"
            reminder.sent_at = datetime.now(UTC)
        else:
            # Skipped: opt-out or missing contact info. Cancel so it's not retried.
            reminder.status = "cancelled"

        await session.commit()

    await asyncio.to_thread(delete_message_sync, queue_name, receipt_handle)
    logger.info("Processed reminder %s (type=%s)", reminder_id, reminder.reminder_type)


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
