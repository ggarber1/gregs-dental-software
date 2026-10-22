"""Integration tests for the scheduled reminder job (send_due_reminders).

Twilio and SES are mocked; the database is real so claiming (FOR UPDATE SKIP LOCKED),
leases and conditional status updates are exercised as they run in production.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models.appointment import Appointment
from app.models.appointment_reminder import AppointmentReminder
from app.models.patient import Patient
from app.workers.reminder_worker import send_due_reminders

pytestmark = pytest.mark.integration

_P_SMS = "app.workers.reminder_worker.send_sms"
_P_EMAIL = "app.workers.reminder_worker.send_email"


async def _seed_appointment(
    session: AsyncSession, practice, *, status: str = "scheduled", starts_in=timedelta(hours=24)
) -> Appointment:
    patient = Patient(
        id=uuid.uuid4(),
        practice_id=practice.id,
        first_name="Rem",
        last_name="Inder",
        date_of_birth=date(1990, 1, 1),
        phone="+16175550100",
        email="rem@example.com",
    )
    start = datetime.now(UTC) + starts_in
    appt = Appointment(
        id=uuid.uuid4(),
        practice_id=practice.id,
        patient_id=patient.id,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        status=status,
    )
    session.add_all([patient, appt])
    await session.flush()
    return appt


async def _seed_reminder(
    session: AsyncSession,
    appt: Appointment,
    *,
    reminder_type: str = "sms",
    send_at: datetime | None = None,
    status: str = "pending",
    claimed_at: datetime | None = None,
    twilio_message_sid: str | None = None,
) -> AppointmentReminder:
    row = AppointmentReminder(
        id=uuid.uuid4(),
        practice_id=appt.practice_id,
        appointment_id=appt.id,
        patient_id=appt.patient_id,
        reminder_type=reminder_type,
        hours_before=24,
        send_at=send_at or datetime.now(UTC) - timedelta(minutes=1),
        status=status,
        claimed_at=claimed_at,
        twilio_message_sid=twilio_message_sid,
    )
    session.add(row)
    await session.flush()
    return row


async def _status(session: AsyncSession, reminder_id: uuid.UUID) -> AppointmentReminder:
    """Re-read a reminder as the job left it (rows were updated in other sessions)."""
    row = await session.scalar(
        select(AppointmentReminder)
        .where(AppointmentReminder.id == reminder_id)
        .execution_options(populate_existing=True)
    )
    assert row is not None
    return row


def _factory(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


async def test_due_reminders_are_sent_once(db_engine, db_session, practice) -> None:
    appt = await _seed_appointment(db_session, practice)
    sms = await _seed_reminder(db_session, appt, reminder_type="sms")
    email = await _seed_reminder(db_session, appt, reminder_type="email")
    await db_session.commit()

    with (
        patch(_P_SMS, AsyncMock(return_value="SM123")) as send_sms,
        patch(_P_EMAIL, AsyncMock()) as send_email,
    ):
        first = await send_due_reminders(_factory(db_engine))
        second = await send_due_reminders(_factory(db_engine))

    assert (first.claimed, first.sent) == (2, 2)
    assert second.claimed == 0
    send_sms.assert_awaited_once()
    send_email.assert_awaited_once()
    sms_row = await _status(db_session, sms.id)
    assert sms_row.status == "sent" and sms_row.twilio_message_sid == "SM123"
    assert sms_row.sent_at is not None
    assert (await _status(db_session, email.id)).status == "sent"


async def test_reminders_not_yet_due_are_left_alone(db_engine, db_session, practice) -> None:
    appt = await _seed_appointment(db_session, practice)
    later = await _seed_reminder(db_session, appt, send_at=datetime.now(UTC) + timedelta(hours=1))
    await db_session.commit()

    with patch(_P_SMS, AsyncMock()) as send_sms:
        summary = await send_due_reminders(_factory(db_engine))

    assert summary.claimed == 0
    send_sms.assert_not_awaited()
    assert (await _status(db_session, later.id)).status == "pending"


@pytest.mark.parametrize("appt_status", ["cancelled", "no_show"])
async def test_reminder_for_inactive_appointment_is_cancelled(
    db_engine, db_session, practice, appt_status
) -> None:
    appt = await _seed_appointment(db_session, practice, status=appt_status)
    rem = await _seed_reminder(db_session, appt)
    await db_session.commit()

    with patch(_P_SMS, AsyncMock()) as send_sms:
        summary = await send_due_reminders(_factory(db_engine))

    send_sms.assert_not_awaited()
    assert summary.skipped == 1
    assert (await _status(db_session, rem.id)).status == "cancelled"


async def test_reminder_for_appointment_already_started_is_cancelled(
    db_engine, db_session, practice
) -> None:
    appt = await _seed_appointment(db_session, practice, starts_in=-timedelta(minutes=5))
    rem = await _seed_reminder(db_session, appt)
    await db_session.commit()

    with patch(_P_SMS, AsyncMock()) as send_sms:
        await send_due_reminders(_factory(db_engine))

    send_sms.assert_not_awaited()
    assert (await _status(db_session, rem.id)).status == "cancelled"


async def test_concurrent_runs_send_each_reminder_exactly_once(
    db_engine, db_session, practice
) -> None:
    appt = await _seed_appointment(db_session, practice)
    for _ in range(6):
        await _seed_reminder(db_session, appt)
    await db_session.commit()

    async def slow_sms(*_: object) -> str:
        await asyncio.sleep(0.05)
        return f"SM{uuid.uuid4().hex[:8]}"

    with patch(_P_SMS, AsyncMock(side_effect=slow_sms)) as send_sms:
        a, b = await asyncio.gather(
            send_due_reminders(_factory(db_engine)), send_due_reminders(_factory(db_engine))
        )

    assert a.claimed + b.claimed == 6
    assert send_sms.await_count == 6


async def test_stale_claim_is_recovered(db_engine, db_session, practice) -> None:
    appt = await _seed_appointment(db_session, practice)
    stuck = await _seed_reminder(
        db_session, appt, status="enqueued", claimed_at=datetime.now(UTC) - timedelta(minutes=30)
    )
    fresh = await _seed_reminder(
        db_session, appt, status="enqueued", claimed_at=datetime.now(UTC) - timedelta(minutes=1)
    )
    await db_session.commit()

    with patch(_P_SMS, AsyncMock(return_value="SMabc")):
        summary = await send_due_reminders(_factory(db_engine))

    assert summary.claimed == 1
    assert (await _status(db_session, stuck.id)).status == "sent"
    assert (await _status(db_session, fresh.id)).status == "enqueued"


async def test_reminder_already_delivered_is_not_resent(db_engine, db_session, practice) -> None:
    appt = await _seed_appointment(db_session, practice)
    rem = await _seed_reminder(
        db_session,
        appt,
        status="enqueued",
        claimed_at=datetime.now(UTC) - timedelta(minutes=30),
        twilio_message_sid="SMalready",
    )
    await db_session.commit()

    with patch(_P_SMS, AsyncMock()) as send_sms:
        await send_due_reminders(_factory(db_engine))

    send_sms.assert_not_awaited()
    row = await _status(db_session, rem.id)
    assert row.status == "sent" and row.twilio_message_sid == "SMalready"


async def test_delivery_failure_is_recorded(db_engine, db_session, practice) -> None:
    appt = await _seed_appointment(db_session, practice)
    rem = await _seed_reminder(db_session, appt)
    await db_session.commit()

    with patch(_P_SMS, AsyncMock(side_effect=RuntimeError("twilio 500"))):
        summary = await send_due_reminders(_factory(db_engine))

    assert summary.failed == 1
    row = await _status(db_session, rem.id)
    assert row.status == "failed" and row.failed_at is not None
    assert row.failure_reason == "twilio 500"


async def test_batch_limit_spreads_work_across_runs(db_engine, db_session, practice) -> None:
    appt = await _seed_appointment(db_session, practice)
    for _ in range(5):
        await _seed_reminder(db_session, appt)
    await db_session.commit()

    with patch(_P_SMS, AsyncMock(return_value="SMx")):
        first = await send_due_reminders(_factory(db_engine), limit=3)
        second = await send_due_reminders(_factory(db_engine), limit=3)

    assert (first.claimed, second.claimed) == (3, 2)
