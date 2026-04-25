"""Unit tests for reminder worker delivery logic (Module 4.2).

No real DB, SQS, Twilio, or SES — all external calls are mocked.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.reminder_worker import _deliver, _deliver_email, _deliver_sms

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_reminder(reminder_type: str = "sms", hours_before: int = 24) -> MagicMock:
    r = MagicMock()
    r.id = uuid.uuid4()
    r.reminder_type = reminder_type
    r.hours_before = hours_before
    r.twilio_message_sid = None
    r.sent_at = None
    return r


def _make_patient(
    phone: str | None = "+15551234567",
    email: str | None = "jane@example.com",
    sms_opt_out: bool = False,
    email_opt_out: bool = False,
) -> MagicMock:
    p = MagicMock()
    p.id = uuid.uuid4()
    p.first_name = "Jane"
    p.phone = phone
    p.email = email
    p.sms_opt_out = sms_opt_out
    p.email_opt_out = email_opt_out
    return p


def _make_appointment() -> MagicMock:
    a = MagicMock()
    a.id = uuid.uuid4()
    a.start_time = datetime.now(UTC) + timedelta(hours=24)
    return a


def _make_practice(phone: str | None = "(617) 555-0000") -> MagicMock:
    p = MagicMock()
    p.name = "Sunrise Dental"
    p.timezone = "America/New_York"
    p.phone = phone
    return p


# ── SMS delivery ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deliver_sms_calls_send_sms_and_stores_sid():
    reminder = _make_reminder("sms")
    patient = _make_patient()
    appointment = _make_appointment()
    practice = _make_practice()

    mock_send = AsyncMock(return_value="SM123")
    with patch("app.workers.reminder_worker.send_sms", new=mock_send):
        result = await _deliver_sms(reminder, patient, appointment, practice)

    assert result is True
    mock_send.assert_awaited_once()
    assert reminder.twilio_message_sid == "SM123"


@pytest.mark.asyncio
async def test_deliver_sms_skips_when_sms_opt_out():
    reminder = _make_reminder("sms")
    patient = _make_patient(sms_opt_out=True)

    mock_send = AsyncMock()
    with patch("app.workers.reminder_worker.send_sms", new=mock_send):
        result = await _deliver_sms(reminder, patient, _make_appointment(), _make_practice())

    assert result is False
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_sms_skips_when_no_phone():
    reminder = _make_reminder("sms")
    patient = _make_patient(phone=None)

    mock_send = AsyncMock()
    with patch("app.workers.reminder_worker.send_sms", new=mock_send):
        result = await _deliver_sms(reminder, patient, _make_appointment(), _make_practice())

    assert result is False
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_sms_propagates_twilio_error():
    reminder = _make_reminder("sms")
    patient = _make_patient()

    mock_send = AsyncMock(side_effect=RuntimeError("Twilio 500"))
    with (
        patch("app.workers.reminder_worker.send_sms", new=mock_send),
        pytest.raises(RuntimeError, match="Twilio 500"),
    ):
        await _deliver_sms(reminder, patient, _make_appointment(), _make_practice())


# ── Email delivery ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deliver_email_calls_send_email():
    reminder = _make_reminder("email")
    patient = _make_patient()
    appointment = _make_appointment()
    practice = _make_practice()

    mock_send = AsyncMock(return_value="msg-id")
    with patch("app.workers.reminder_worker.send_email", new=mock_send):
        result = await _deliver_email(reminder, patient, appointment, practice)

    assert result is True
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_deliver_email_skips_when_email_opt_out():
    reminder = _make_reminder("email")
    patient = _make_patient(email_opt_out=True)

    mock_send = AsyncMock()
    with patch("app.workers.reminder_worker.send_email", new=mock_send):
        result = await _deliver_email(reminder, patient, _make_appointment(), _make_practice())

    assert result is False
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_email_skips_when_no_email():
    reminder = _make_reminder("email")
    patient = _make_patient(email=None)

    mock_send = AsyncMock()
    with patch("app.workers.reminder_worker.send_email", new=mock_send):
        result = await _deliver_email(reminder, patient, _make_appointment(), _make_practice())

    assert result is False
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_deliver_email_propagates_ses_error():
    reminder = _make_reminder("email")
    patient = _make_patient()

    mock_send = AsyncMock(side_effect=RuntimeError("SES error"))
    with (
        patch("app.workers.reminder_worker.send_email", new=mock_send),
        pytest.raises(RuntimeError, match="SES error"),
    ):
        await _deliver_email(reminder, patient, _make_appointment(), _make_practice())


# ── _deliver dispatcher ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deliver_routes_sms_type():
    reminder = _make_reminder("sms")
    mock_deliver = AsyncMock(return_value=True)
    with patch("app.workers.reminder_worker._deliver_sms", new=mock_deliver):
        result = await _deliver(reminder, _make_patient(), _make_appointment(), _make_practice())
    assert result is True
    mock_deliver.assert_awaited_once()


@pytest.mark.asyncio
async def test_deliver_routes_email_type():
    reminder = _make_reminder("email")
    mock_deliver = AsyncMock(return_value=True)
    with patch("app.workers.reminder_worker._deliver_email", new=mock_deliver):
        result = await _deliver(reminder, _make_patient(), _make_appointment(), _make_practice())
    assert result is True
    mock_deliver.assert_awaited_once()


@pytest.mark.asyncio
async def test_deliver_returns_false_for_unknown_type():
    reminder = _make_reminder("fax")  # unknown type
    result = await _deliver(reminder, _make_patient(), _make_appointment(), _make_practice())
    assert result is False
