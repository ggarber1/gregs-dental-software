"""Inbound webhook handlers for external services.

These routes are PUBLIC (no JWT auth). Twilio signature validation is used
instead of JWT for the Twilio webhook.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Form, Header, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.models.appointment import Appointment
from app.models.appointment_reminder import AppointmentReminder
from app.models.patient import Patient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

_TWIML_EMPTY = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def _normalize_phone(phone: str) -> str:
    """Strip all non-digit characters for loose matching."""
    return re.sub(r"\D", "", phone)


def _validate_twilio_signature(request: Request, signature: str | None) -> bool:
    """Return True if the request is authentically from Twilio.

    In development (no Twilio credentials configured) validation is skipped so
    the endpoint can be exercised locally.
    """
    settings = get_settings()
    if not settings.twilio_auth_token:
        return True  # dev mode — skip

    if not signature:
        return False

    try:
        from twilio.request_validator import RequestValidator
    except ImportError:
        logger.error("twilio package not installed — cannot validate signature")
        return False

    validator = RequestValidator(settings.twilio_auth_token)
    # Reconstruct the full URL Twilio signed (scheme + host + path + query).
    url = str(request.url)
    result: bool = validator.validate(url, {}, signature)
    return result


@router.post("/twilio/inbound")
async def twilio_inbound(
    request: Request,
    x_twilio_signature: str | None = Header(default=None),
    from_number: str = Form(..., alias="From"),
    body: str = Form(..., alias="Body"),
    message_sid: str = Form(default="", alias="MessageSid"),
) -> Response:
    """Handle inbound SMS replies from patients.

    Recognized keywords (case-insensitive after strip):
    - YES  → confirm the patient's soonest upcoming scheduled appointment
    - NO   → record the decline; appointment status unchanged
    - STOP → opt patient out of SMS reminders; cancel pending reminders
    """
    if not _validate_twilio_signature(request, x_twilio_signature):
        logger.warning("Invalid Twilio signature on inbound SMS from %s", from_number)
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    keyword = body.strip().upper()
    from_digits = _normalize_phone(from_number)

    logger.info(
        "Twilio inbound SMS: From=%s Body=%r SID=%s",
        from_number,
        body,
        message_sid,
    )

    factory = get_session_factory()
    async with factory() as session:
        # Look up patient by normalized phone within any practice.
        patients_result = await session.scalars(
            select(Patient).where(
                Patient.deleted_at.is_(None),
                func.regexp_replace(Patient.phone, r"\D", "", "g") == from_digits,
            )
        )
        patients = list(patients_result.all())

        if not patients:
            logger.info("Inbound SMS from unknown number %s — ignoring", from_number)
            return Response(content=_TWIML_EMPTY, media_type="application/xml")

        for patient in patients:
            if keyword == "STOP":
                await _handle_stop(session, patient)
            elif keyword == "YES":
                await _handle_yes(session, patient)
            elif keyword == "NO":
                await _handle_no(session, patient)
            else:
                logger.info(
                    "Unrecognized keyword %r from patient %s — ignoring",
                    keyword,
                    patient.id,
                )

        await session.commit()

    return Response(content=_TWIML_EMPTY, media_type="application/xml")


async def _handle_stop(session: AsyncSession, patient: Patient) -> None:
    """Mark patient as opted out and cancel all pending/enqueued SMS reminders."""
    if not patient.sms_opt_out:
        patient.sms_opt_out = True
        logger.info("Patient %s opted out of SMS reminders", patient.id)

    # Cancel pending/enqueued reminders (only SMS — email is unaffected by STOP).
    await session.execute(
        update(AppointmentReminder)
        .where(
            AppointmentReminder.patient_id == patient.id,
            AppointmentReminder.reminder_type == "sms",
            AppointmentReminder.status.in_(("pending", "enqueued")),
            AppointmentReminder.deleted_at.is_(None),
        )
        .values(status="cancelled", updated_at=func.now())
    )


async def _handle_yes(session: AsyncSession, patient: Patient) -> None:
    """Confirm the patient's soonest upcoming scheduled appointment."""
    now = datetime.now(UTC)
    appt_result = await session.scalars(
        select(Appointment)
        .where(
            Appointment.patient_id == patient.id,
            Appointment.status == "scheduled",
            Appointment.start_time > now,
            Appointment.deleted_at.is_(None),
        )
        .order_by(Appointment.start_time.asc())
        .limit(1)
    )
    appointment = appt_result.first()

    if appointment is None:
        logger.info(
            "YES from patient %s but no upcoming scheduled appointment found",
            patient.id,
        )
        return

    appointment.status = "confirmed"
    logger.info(
        "Appointment %s confirmed via SMS reply from patient %s",
        appointment.id,
        patient.id,
    )

    # Record the response on the most recent sent/enqueued reminder for this appointment.
    await _record_response(session, patient.id, appointment.id, "YES")


async def _handle_no(session: AsyncSession, patient: Patient) -> None:
    """Record a NO reply without changing the appointment status."""
    now = datetime.now(UTC)
    appt_result = await session.scalars(
        select(Appointment)
        .where(
            Appointment.patient_id == patient.id,
            Appointment.status.in_(("scheduled", "confirmed")),
            Appointment.start_time > now,
            Appointment.deleted_at.is_(None),
        )
        .order_by(Appointment.start_time.asc())
        .limit(1)
    )
    appointment = appt_result.first()

    if appointment is None:
        logger.info(
            "NO from patient %s but no upcoming appointment found",
            patient.id,
        )
        return

    await _record_response(session, patient.id, appointment.id, "NO")


async def _record_response(
    session: AsyncSession,
    patient_id: uuid.UUID,
    appointment_id: uuid.UUID,
    response: str,
) -> None:
    """Set response_received + responded_at on the most recent SMS reminder."""
    now = datetime.now(UTC)
    reminder_result = await session.scalars(
        select(AppointmentReminder)
        .where(
            AppointmentReminder.patient_id == patient_id,
            AppointmentReminder.appointment_id == appointment_id,
            AppointmentReminder.reminder_type == "sms",
            AppointmentReminder.status.in_(("sent", "enqueued")),
            AppointmentReminder.deleted_at.is_(None),
        )
        .order_by(AppointmentReminder.send_at.desc())
        .limit(1)
    )
    reminder = reminder_result.first()
    if reminder:
        reminder.response_received = response
        reminder.responded_at = now
