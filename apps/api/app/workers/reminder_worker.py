from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.sqs import delete_message_sync, enqueue_message_sync, poll_messages_sync
from app.models.appointment_reminder import AppointmentReminder

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
    factory: async_sessionmaker = get_session_factory()

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


async def _process_message(msg: dict) -> None:
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
        reminder = await session.get(AppointmentReminder, reminder_id)

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

        # Module 4.2 replaces this placeholder with actual SMS/email delivery.
        logger.info(
            "Processing %s reminder for appointment %s [delivery wired in 4.2]",
            reminder.reminder_type,
            reminder.appointment_id,
        )

        reminder.status = "sent"
        reminder.sent_at = datetime.now(UTC)
        await session.commit()

    await asyncio.to_thread(delete_message_sync, queue_name, receipt_handle)
    logger.info("Processed reminder %s", reminder_id)
