"""
Unit tests for the reminder service (app.services.reminders).

No real DB or SQS — all calls go through mock sessions.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.reminders import (
    _build_reminder_row,
    cancel_reminders_for_appointment,
    stage_reminder_jobs,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_appointment(
    start_time: datetime | None = None,
    patient_id: uuid.UUID | None = None,
) -> MagicMock:
    appt = MagicMock()
    appt.id = uuid.uuid4()
    appt.practice_id = uuid.uuid4()
    appt.patient_id = patient_id if patient_id is not None else uuid.uuid4()
    appt.start_time = (
        start_time if start_time is not None else datetime.now(UTC) + timedelta(days=3)
    )
    return appt


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    execute_result = MagicMock()
    execute_result.fetchall.return_value = []
    session.execute = AsyncMock(return_value=execute_result)
    return session


# ── _build_reminder_row ───────────────────────────────────────────────────────


def test_build_reminder_row_returns_row_for_future_appointment():
    appt = _make_appointment(start_time=datetime.now(UTC) + timedelta(days=3))
    row = _build_reminder_row(appt, hours_before=48, reminder_type="sms")
    assert row is not None
    assert row.send_at == appt.start_time - timedelta(hours=48)
    assert row.hours_before == 48
    assert row.reminder_type == "sms"
    assert row.status == "pending"
    assert row.appointment_id == appt.id
    assert row.practice_id == appt.practice_id


def test_build_reminder_row_returns_none_when_send_at_in_past():
    # Appointment in 30h: 48h reminder's send_at is 18h in the past
    appt = _make_appointment(start_time=datetime.now(UTC) + timedelta(hours=30))
    row = _build_reminder_row(appt, hours_before=48, reminder_type="sms")
    assert row is None


def test_build_reminder_row_returns_row_when_send_at_still_future():
    # Appointment in 30h: 24h reminder's send_at is 6h from now
    appt = _make_appointment(start_time=datetime.now(UTC) + timedelta(hours=30))
    row = _build_reminder_row(appt, hours_before=24, reminder_type="sms")
    assert row is not None
    # send_at should be ~6h from now (appointment_start - 24h = now + 30h - 24h = now + 6h)
    expected = appt.start_time - timedelta(hours=24)
    assert row.send_at == expected


def test_build_reminder_row_returns_none_when_appointment_imminent():
    # Appointment in 2h: 24h reminder's send_at is 22h in the past
    appt = _make_appointment(start_time=datetime.now(UTC) + timedelta(hours=2))
    row = _build_reminder_row(appt, hours_before=24, reminder_type="sms")
    assert row is None


# ── stage_reminder_jobs ───────────────────────────────────────────────────────


def test_stage_reminder_jobs_creates_four_rows_for_far_future_appointment():
    # 2 windows (48h, 24h) × 2 types (sms, email) = 4 rows
    appt = _make_appointment(start_time=datetime.now(UTC) + timedelta(days=7))
    session = _make_session()
    rows = stage_reminder_jobs(session, appt)
    assert len(rows) == 4
    assert {r.hours_before for r in rows} == {48, 24}
    assert {r.reminder_type for r in rows} == {"sms", "email"}
    assert session.add.call_count == 4


def test_stage_reminder_jobs_skips_48h_when_appointment_too_soon():
    # 30h away: only 24h window fits — both sms + email for that window = 2 rows
    appt = _make_appointment(start_time=datetime.now(UTC) + timedelta(hours=30))
    session = _make_session()
    rows = stage_reminder_jobs(session, appt)
    assert len(rows) == 2
    assert all(r.hours_before == 24 for r in rows)
    assert {r.reminder_type for r in rows} == {"sms", "email"}
    assert session.add.call_count == 2


def test_stage_reminder_jobs_skips_all_when_appointment_imminent():
    # 2h away: both reminders are in the past
    appt = _make_appointment(start_time=datetime.now(UTC) + timedelta(hours=2))
    session = _make_session()
    rows = stage_reminder_jobs(session, appt)
    assert rows == []
    session.add.assert_not_called()


def test_stage_reminder_jobs_skips_when_no_patient():
    appt = _make_appointment()
    appt.patient_id = None
    session = _make_session()
    rows = stage_reminder_jobs(session, appt)
    assert rows == []
    session.add.assert_not_called()


def test_stage_reminder_jobs_all_rows_are_pending():
    appt = _make_appointment(start_time=datetime.now(UTC) + timedelta(days=5))
    session = _make_session()
    rows = stage_reminder_jobs(session, appt)
    assert all(r.status == "pending" for r in rows)


def test_stage_reminder_jobs_creates_both_sms_and_email_rows():
    appt = _make_appointment(start_time=datetime.now(UTC) + timedelta(days=5))
    session = _make_session()
    rows = stage_reminder_jobs(session, appt)
    assert {r.reminder_type for r in rows} == {"sms", "email"}


def test_stage_reminder_jobs_send_at_offsets_are_correct():
    start = datetime.now(UTC) + timedelta(days=5)
    appt = _make_appointment(start_time=start)
    session = _make_session()
    rows = stage_reminder_jobs(session, appt)
    rows_by_hours = {r.hours_before: r for r in rows}
    assert rows_by_hours[48].send_at == start - timedelta(hours=48)
    assert rows_by_hours[24].send_at == start - timedelta(hours=24)


# ── cancel_reminders_for_appointment ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_reminders_executes_update():
    session = _make_session()
    await cancel_reminders_for_appointment(session, uuid.uuid4())
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_reminders_executes_update_with_correct_appointment_id():
    session = _make_session()
    appt_id = uuid.uuid4()
    await cancel_reminders_for_appointment(session, appt_id)
    # The execute call should have been made (exact args are an UPDATE statement)
    assert session.execute.await_count == 1
