"""Integration tests for the nightly risk-scoring job."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.appointment import Appointment
from app.models.appointment_reminder import AppointmentReminder
from app.models.patient import Patient
from app.workers.risk_scoring_worker import score_upcoming_appointments

pytestmark = pytest.mark.integration


def _appt(
    practice_id: uuid.UUID, patient_id: uuid.UUID, start: datetime, status: str
) -> Appointment:
    return Appointment(
        id=uuid.uuid4(),
        practice_id=practice_id,
        patient_id=patient_id,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        status=status,
    )


async def test_scores_upcoming_appointments_without_staging_reminders(
    db_engine, db_session: AsyncSession, practice
) -> None:
    now = datetime.now(UTC)
    patient = Patient(
        id=uuid.uuid4(),
        practice_id=practice.id,
        first_name="Risk",
        last_name="Score",
        date_of_birth=date(1990, 1, 1),
    )
    db_session.add(patient)
    await db_session.flush()
    history = [
        _appt(practice.id, patient.id, now - timedelta(days=d), "no_show") for d in (10, 20, 30)
    ]
    upcoming = _appt(practice.id, patient.id, now + timedelta(days=2), "scheduled")
    beyond_window = _appt(practice.id, patient.id, now + timedelta(days=30), "scheduled")
    db_session.add_all([*history, upcoming, beyond_window])
    await db_session.commit()

    scored = await score_upcoming_appointments(
        async_sessionmaker(db_engine, expire_on_commit=False)
    )

    assert scored == 1
    refreshed = await db_session.scalar(
        select(Appointment)
        .where(Appointment.id == upcoming.id)
        .execution_options(populate_existing=True)
    )
    assert refreshed is not None
    assert refreshed.no_show_risk in ("low", "medium", "high")
    assert refreshed.no_show_risk_computed_at is not None
    untouched = await db_session.scalar(
        select(Appointment)
        .where(Appointment.id == beyond_window.id)
        .execution_options(populate_existing=True)
    )
    assert untouched is not None and untouched.no_show_risk_computed_at is None
    reminders = await db_session.scalar(select(func.count()).select_from(AppointmentReminder))
    assert reminders == 0


async def test_no_upcoming_appointments_scores_nothing(db_engine, practice) -> None:
    scored = await score_upcoming_appointments(
        async_sessionmaker(db_engine, expire_on_commit=False)
    )
    assert scored == 0
