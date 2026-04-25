"""
Integration tests for the Twilio inbound SMS webhook (Module 4.2).

Requires Postgres at localhost:5432 (dental/dental).
Run with: pytest -m integration tests/integration/test_webhook_twilio.py -v
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from tests.integration.conftest import mut

pytestmark = pytest.mark.integration


async def _create_appointment(client, headers, patient, provider, operatory, days_ahead: int = 7):
    start = datetime.now(UTC) + timedelta(days=days_ahead)
    end = start + timedelta(hours=1)
    resp = await client.post(
        "/api/v1/appointments",
        json={
            "patientId": str(patient.id),
            "providerId": str(provider.id),
            "operatoryId": str(operatory.id),
            "startTime": start.isoformat(),
            "endTime": end.isoformat(),
        },
        headers=mut(headers),
    )
    assert resp.status_code == 201
    return uuid.UUID(resp.json()["id"])


async def _fetch_appointment(session, appt_id):
    from app.models.appointment import Appointment
    return await session.get(Appointment, appt_id)


async def _fetch_patient(session, patient_id):
    from app.models.patient import Patient
    return await session.get(Patient, patient_id)


async def _fetch_reminders(session, patient_id, appt_id):
    from app.models.appointment_reminder import AppointmentReminder
    result = await session.scalars(
        select(AppointmentReminder).where(
            AppointmentReminder.patient_id == patient_id,
            AppointmentReminder.appointment_id == appt_id,
            AppointmentReminder.deleted_at.is_(None),
        )
    )
    return result.all()


def _inbound_payload(phone: str, body: str) -> dict:
    return {
        "From": phone,
        "Body": body,
        "MessageSid": f"SM{uuid.uuid4().hex}",
    }


# ── YES: confirms soonest upcoming scheduled appointment ──────────────────────


@pytest.mark.asyncio
async def test_yes_reply_confirms_appointment(
    client, auth_headers, db_session, patient, provider, operatory
):
    appt_id = await _create_appointment(client, auth_headers, patient, provider, operatory)

    resp = await client.post(
        "/api/v1/webhooks/twilio/inbound",
        data=_inbound_payload(patient.phone, "YES"),
    )
    assert resp.status_code == 200
    assert b"<Response>" in resp.content

    await db_session.commit()
    appt = await _fetch_appointment(db_session, appt_id)
    await db_session.refresh(appt)
    assert appt.status == "confirmed"


@pytest.mark.asyncio
async def test_yes_reply_case_insensitive(
    client, auth_headers, db_session, patient, provider, operatory
):
    appt_id = await _create_appointment(client, auth_headers, patient, provider, operatory)

    resp = await client.post(
        "/api/v1/webhooks/twilio/inbound",
        data=_inbound_payload(patient.phone, "yes"),
    )
    assert resp.status_code == 200

    await db_session.commit()
    appt = await _fetch_appointment(db_session, appt_id)
    await db_session.refresh(appt)
    assert appt.status == "confirmed"


# ── NO: records response, does not change status ──────────────────────────────


@pytest.mark.asyncio
async def test_no_reply_does_not_change_appointment_status(
    client, auth_headers, db_session, patient, provider, operatory
):
    appt_id = await _create_appointment(client, auth_headers, patient, provider, operatory)

    resp = await client.post(
        "/api/v1/webhooks/twilio/inbound",
        data=_inbound_payload(patient.phone, "NO"),
    )
    assert resp.status_code == 200

    await db_session.commit()
    appt = await _fetch_appointment(db_session, appt_id)
    await db_session.refresh(appt)
    assert appt.status == "scheduled"


# ── STOP: opts out and cancels pending reminders ──────────────────────────────


@pytest.mark.asyncio
async def test_stop_sets_sms_opt_out(
    client, auth_headers, db_session, patient, provider, operatory
):
    await _create_appointment(client, auth_headers, patient, provider, operatory)

    resp = await client.post(
        "/api/v1/webhooks/twilio/inbound",
        data=_inbound_payload(patient.phone, "STOP"),
    )
    assert resp.status_code == 200

    await db_session.commit()
    p = await _fetch_patient(db_session, patient.id)
    await db_session.refresh(p)
    assert p.sms_opt_out is True


@pytest.mark.asyncio
async def test_stop_cancels_pending_sms_reminders(
    client, auth_headers, db_session, patient, provider, operatory
):
    appt_id = await _create_appointment(client, auth_headers, patient, provider, operatory)

    resp = await client.post(
        "/api/v1/webhooks/twilio/inbound",
        data=_inbound_payload(patient.phone, "STOP"),
    )
    assert resp.status_code == 200

    await db_session.commit()
    reminders = await _fetch_reminders(db_session, patient.id, appt_id)
    for r in reminders:
        await db_session.refresh(r)

    sms_reminders = [r for r in reminders if r.reminder_type == "sms"]
    assert sms_reminders, "Expected SMS reminders to exist"
    assert all(r.status == "cancelled" for r in sms_reminders)


@pytest.mark.asyncio
async def test_stop_does_not_cancel_email_reminders(
    client, auth_headers, db_session, patient, provider, operatory
):
    appt_id = await _create_appointment(client, auth_headers, patient, provider, operatory)

    resp = await client.post(
        "/api/v1/webhooks/twilio/inbound",
        data=_inbound_payload(patient.phone, "STOP"),
    )
    assert resp.status_code == 200

    await db_session.commit()
    reminders = await _fetch_reminders(db_session, patient.id, appt_id)
    for r in reminders:
        await db_session.refresh(r)

    email_reminders = [r for r in reminders if r.reminder_type == "email"]
    assert email_reminders, "Expected email reminders to exist"
    # Email reminders should still be pending — STOP only affects SMS
    assert all(r.status == "pending" for r in email_reminders)


# ── Unknown number: graceful no-op ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_number_returns_200_twiml(client):
    resp = await client.post(
        "/api/v1/webhooks/twilio/inbound",
        data=_inbound_payload("+19999999999", "YES"),
    )
    assert resp.status_code == 200
    assert b"<Response>" in resp.content


# ── stage_reminder_jobs now creates both SMS and email rows ───────────────────


@pytest.mark.asyncio
async def test_create_appointment_creates_sms_and_email_reminders(
    client, auth_headers, db_session, patient, provider, operatory, appointment_type
):
    appt_id = await _create_appointment(client, auth_headers, patient, provider, operatory)

    from app.models.appointment_reminder import AppointmentReminder
    result = await db_session.scalars(
        select(AppointmentReminder).where(
            AppointmentReminder.appointment_id == appt_id,
            AppointmentReminder.deleted_at.is_(None),
        )
    )
    reminders = result.all()

    # 2 windows × 2 types = 4 rows
    assert len(reminders) == 4
    assert {r.reminder_type for r in reminders} == {"sms", "email"}
    assert {r.hours_before for r in reminders} == {48, 24}
