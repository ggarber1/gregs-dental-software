"""Unit tests for the reminders service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from app.services.reminders import _DEFAULT_REMINDER_HOURS, stage_reminder_jobs


def _make_appointment(hours_ahead: int = 72, patient_id: uuid.UUID | None = None) -> MagicMock:
    appt = MagicMock()
    appt.id = uuid.uuid4()
    appt.practice_id = uuid.uuid4()
    appt.patient_id = patient_id or uuid.uuid4()
    appt.start_time = datetime.now(UTC) + timedelta(hours=hours_ahead)
    return appt


def _make_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    return session


# ── Default reminder hours ────────────────────────────────────────────────────


def test_default_hours_unchanged():
    assert set(_DEFAULT_REMINDER_HOURS) == {48, 24}


def test_stage_reminder_jobs_creates_default_windows():
    session = _make_session()
    appt = _make_appointment(hours_ahead=72)

    created = stage_reminder_jobs(session, appt)

    # Default: 48h + 24h × sms + email = 4 rows
    assert len(created) == 4
    hours_seen = {r.hours_before for r in created}
    assert hours_seen == {48, 24}
    types_seen = {r.reminder_type for r in created}
    assert types_seen == {"sms", "email"}


def test_stage_reminder_jobs_custom_hours():
    session = _make_session()
    appt = _make_appointment(hours_ahead=100)

    created = stage_reminder_jobs(session, appt, reminder_hours=[72, 48, 24])

    assert len(created) == 6  # 3 windows × 2 channels
    hours_seen = {r.hours_before for r in created}
    assert hours_seen == {72, 48, 24}


def test_stage_reminder_jobs_skips_past_send_times():
    session = _make_session()
    # Appointment only 30 hours away — 48h window is in the past, 24h is future
    appt = _make_appointment(hours_ahead=30)

    created = stage_reminder_jobs(session, appt)

    # Only 24h window created (48h send_at would be in the past)
    assert all(r.hours_before == 24 for r in created)
    assert len(created) == 2  # sms + email for 24h


def test_stage_reminder_jobs_no_patient_returns_empty():
    session = _make_session()
    appt = _make_appointment(hours_ahead=72)
    appt.patient_id = None

    created = stage_reminder_jobs(session, appt)

    assert created == []
    session.add.assert_not_called()


def test_stage_reminder_jobs_all_windows_future():
    session = _make_session()
    appt = _make_appointment(hours_ahead=100)

    created = stage_reminder_jobs(session, appt, reminder_hours=[48, 24])

    assert len(created) == 4
    assert session.add.call_count == 4
