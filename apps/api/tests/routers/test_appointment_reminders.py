"""Tests for reminder summary in appointment responses and GET /appointments/{id}/reminders."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

_PRACTICE_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_PATIENT_ID = uuid.uuid4()
_PROVIDER_ID = uuid.uuid4()
_OPERATORY_ID = uuid.uuid4()
_APPOINTMENT_ID = uuid.uuid4()
_REMINDER_SMS_ID = uuid.uuid4()
_REMINDER_EMAIL_ID = uuid.uuid4()
_SUB = "cognito-sub-test"
_JWT_CLAIMS = {"sub": _SUB, "email": "staff@clinic.com", "cognito:groups": []}


def _get_app():
    import os

    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    os.environ.setdefault("APP_ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ=")
    from app.main import create_app

    return create_app()


@contextmanager
def _auth_patches(practice_id: uuid.UUID | None = _PRACTICE_ID, role: str = "front_desk"):
    membership_result = (_USER_ID, role) if practice_id is not None else None
    headers: dict[str, str] = {"Authorization": "Bearer fake.jwt.token"}
    if practice_id is not None:
        headers["X-Practice-ID"] = str(practice_id)

    with (
        patch("jose.jwt.get_unverified_header", return_value={"kid": "fake-kid"}),
        patch("app.middleware.auth._get_public_key", new=AsyncMock(return_value=object())),
        patch("jose.jwt.decode", return_value=_JWT_CLAIMS),
        patch(
            "app.middleware.auth._resolve_practice_membership",
            new=AsyncMock(return_value=membership_result),
        ),
        patch(
            "app.middleware.idempotency.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), setex=AsyncMock()),
        ),
    ):
        yield headers


def _make_patient_mock(sms_opt_out: bool = False) -> MagicMock:
    patient = MagicMock()
    patient.id = _PATIENT_ID
    patient.first_name = "Jane"
    patient.last_name = "Doe"
    patient.sms_opt_out = sms_opt_out
    patient.deleted_at = None
    return patient


def _make_appointment_mock(patient: MagicMock | None = None) -> MagicMock:
    provider = MagicMock()
    provider.full_name = "Dr. Smith"
    operatory = MagicMock()
    operatory.name = "Op 1"

    row = MagicMock()
    row.id = _APPOINTMENT_ID
    row.practice_id = _PRACTICE_ID
    row.patient_id = _PATIENT_ID
    row.provider_id = _PROVIDER_ID
    row.operatory_id = _OPERATORY_ID
    row.appointment_type_id = None
    row.start_time = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
    row.end_time = datetime(2026, 6, 15, 9, 30, tzinfo=UTC)
    row.status = "scheduled"
    row.notes = None
    row.cancellation_reason = None
    row.deleted_at = None
    row.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    row.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    row.patient = patient or _make_patient_mock()
    row.provider = provider
    row.operatory = operatory
    row.appointment_type = None
    return row


def _make_reminder_row(
    reminder_type: str = "sms",
    status: str = "sent",
    hours_before: int = 24,
) -> MagicMock:
    row = MagicMock()
    row.id = uuid.uuid4()
    row.appointment_id = _APPOINTMENT_ID
    row.reminder_type = reminder_type
    row.hours_before = hours_before
    row.status = status
    row.send_at = datetime(2026, 6, 14, 9, 0, tzinfo=UTC)
    row.sent_at = datetime(2026, 6, 14, 9, 0, tzinfo=UTC) if status == "sent" else None
    row.failed_at = None
    row.failure_reason = None
    row.response_received = None
    row.responded_at = None
    row.deleted_at = None
    return row


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.commit = AsyncMock()
    return session


# ── reminder_summary in appointment list response ─────────────────────────────


@pytest.mark.asyncio
async def test_appointment_list_includes_sent_reminder_summary():
    """GET /appointments returns reminderSummary with channel statuses."""
    app = _get_app()
    appt = _make_appointment_mock()

    # Simulate scalars returning appointments
    scalars_result = MagicMock()
    scalars_result.all.return_value = [appt]

    # Simulate execute returning reminder rows (Row tuples)
    def _make_row_tuple(appt_id: uuid.UUID, rtype: str, status: str) -> Any:
        row = MagicMock()
        # Simulate positional access used by _batch_reminder_summary
        row.__iter__ = MagicMock(return_value=iter([appt_id, rtype, status]))
        # Support unpacking via tuple protocol
        return (appt_id, rtype, status)

    execute_result = MagicMock()
    execute_result.all.return_value = [
        (_APPOINTMENT_ID, "sms", "sent"),
        (_APPOINTMENT_ID, "email", "pending"),
    ]

    session = _mock_session()
    session.scalars = AsyncMock(return_value=scalars_result)
    session.execute = AsyncMock(return_value=execute_result)

    with _auth_patches() as headers, patch(
        "app.routers.appointments.get_session_factory", return_value=lambda: session
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.get("/api/v1/appointments", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    summary = data[0]["reminderSummary"]
    assert summary is not None
    assert summary["smsStatus"] == "sent"
    assert summary["emailStatus"] == "pending"
    assert summary["patientSmsOptedOut"] is False


@pytest.mark.asyncio
async def test_appointment_list_reflects_sms_opt_out():
    """reminderSummary.patientSmsOptedOut is True when patient.sms_opt_out is True."""
    app = _get_app()
    opted_out_patient = _make_patient_mock(sms_opt_out=True)
    appt = _make_appointment_mock(patient=opted_out_patient)

    scalars_result = MagicMock()
    scalars_result.all.return_value = [appt]
    execute_result = MagicMock()
    execute_result.all.return_value = []

    session = _mock_session()
    session.scalars = AsyncMock(return_value=scalars_result)
    session.execute = AsyncMock(return_value=execute_result)

    with _auth_patches() as headers, patch(
        "app.routers.appointments.get_session_factory", return_value=lambda: session
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.get("/api/v1/appointments", headers=headers)

    assert resp.status_code == 200
    summary = resp.json()[0]["reminderSummary"]
    assert summary["patientSmsOptedOut"] is True


# ── GET /appointments/{id}/reminders ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_appointment_reminders_returns_history():
    app = _get_app()
    sms_reminder = _make_reminder_row("sms", "sent", 24)
    email_reminder = _make_reminder_row("email", "pending", 24)

    scalars_result = MagicMock()
    scalars_result.all.return_value = [sms_reminder, email_reminder]

    session = _mock_session()
    # First scalar call: check appointment exists
    session.scalar = AsyncMock(return_value=_APPOINTMENT_ID)
    session.scalars = AsyncMock(return_value=scalars_result)

    with _auth_patches() as headers, patch(
        "app.routers.appointments.get_session_factory", return_value=lambda: session
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.get(
                f"/api/v1/appointments/{_APPOINTMENT_ID}/reminders",
                headers=headers,
            )

    assert resp.status_code == 200
    records = resp.json()
    assert len(records) == 2
    assert records[0]["reminderType"] == "sms"
    assert records[0]["status"] == "sent"
    assert records[1]["reminderType"] == "email"
    assert records[1]["status"] == "pending"


@pytest.mark.asyncio
async def test_list_appointment_reminders_returns_404_for_unknown():
    app = _get_app()
    session = _mock_session()
    session.scalar = AsyncMock(return_value=None)

    with _auth_patches() as headers, patch(
        "app.routers.appointments.get_session_factory", return_value=lambda: session
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.get(
                f"/api/v1/appointments/{uuid.uuid4()}/reminders",
                headers=headers,
            )

    assert resp.status_code == 404
