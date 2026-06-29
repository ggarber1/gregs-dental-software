"""Integration tests for ledger charge-posting on appointment checkout (Module 8a)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.appointment_procedure import AppointmentProcedure
from app.models.ledger_entry import LedgerEntry
from app.models.patient import Patient
from app.models.practice import Practice
from app.models.user import PracticeUser, User
from tests.integration.conftest import mut

pytestmark = pytest.mark.integration

# ── Auth patch targets (mirrored from test_era_endpoints.py) ──────────────────

_P_HEADER = "app.middleware.auth.jwt.get_unverified_header"
_P_KEY = "app.middleware.auth._get_public_key"
_P_DECODE = "app.middleware.auth.jwt.decode"


async def _seed(session: AsyncSession, *, billing_ledger: bool, with_procedure: bool = True):
    """Seed a practice (+admin user), patient, an in_chair appointment, and (when
    `with_procedure`) one procedure (fee_cents=12000).
    Returns (practice, user, cognito_sub, appointment)."""
    practice = Practice(
        id=uuid.uuid4(),
        name="Ledger Checkout Test Practice",
        features={"billing_ledger": billing_ledger} if billing_ledger else {},
    )
    session.add(practice)

    cognito_sub = f"ledger-sub-{uuid.uuid4().hex}"
    user = User(
        id=uuid.uuid4(),
        cognito_sub=cognito_sub,
        email=f"ledger-staff-{uuid.uuid4().hex[:6]}@test.local",
        full_name="Ledger Staff",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    session.add(
        PracticeUser(
            practice_id=practice.id,
            user_id=user.id,
            role="admin",
            is_active=True,
        )
    )

    patient = Patient(
        id=uuid.uuid4(),
        practice_id=practice.id,
        first_name="Pat",
        last_name="Ient",
        date_of_birth=date(1990, 1, 1),
    )
    session.add(patient)

    start = datetime.now().replace(microsecond=0) + timedelta(hours=1)
    appointment = Appointment(
        id=uuid.uuid4(),
        practice_id=practice.id,
        patient_id=patient.id,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        status="in_chair",
    )
    session.add(appointment)
    await session.flush()

    if with_procedure:
        session.add(
            AppointmentProcedure(
                id=uuid.uuid4(),
                practice_id=practice.id,
                appointment_id=appointment.id,
                patient_id=patient.id,
                procedure_name="Periodic oral evaluation",
                procedure_code="D0120",
                fee_cents=12000,
            )
        )

    await session.commit()
    return practice, user, cognito_sub, appointment


def _auth(cognito_sub: str, email: str):
    return (
        patch(_P_HEADER, return_value={"kid": "test-kid"}),
        patch(_P_KEY, new=AsyncMock(return_value="fake-public-key")),
        patch(
            _P_DECODE,
            return_value={
                "sub": cognito_sub,
                "email": email,
                "cognito:groups": ["admin"],
            },
        ),
    )


async def test_checkout_posts_ledger_charge_when_enabled(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Completing an appointment posts a charge; GET ledger shows balance 12000."""
    practice, user, sub, appt = await _seed(db_session, billing_ledger=True)
    headers = {"Authorization": "Bearer test-token", "X-Practice-ID": str(practice.id)}
    h1, h2, h3 = _auth(sub, user.email)

    with h1, h2, h3:
        resp = await client.patch(
            f"/api/v1/appointments/{appt.id}",
            headers=mut(headers),
            json={"status": "completed"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "completed"

        ledger_resp = await client.get(
            f"/api/v1/patients/{appt.patient_id}/ledger",
            headers=headers,
        )

    assert ledger_resp.status_code == 200, ledger_resp.text
    body = ledger_resp.json()
    assert body["balanceCents"] == 12000
    charges = [e for e in body["entries"] if e["entryType"] == "charge"]
    assert len(charges) == 1
    assert charges[0]["amountCents"] == 12000


async def test_checkout_skips_ledger_when_feature_disabled(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Soft gate: a practice without billing_ledger still completes, but posts no charge."""
    practice, user, sub, appt = await _seed(db_session, billing_ledger=False)
    headers = {"Authorization": "Bearer test-token", "X-Practice-ID": str(practice.id)}
    h1, h2, h3 = _auth(sub, user.email)

    with h1, h2, h3:
        resp = await client.patch(
            f"/api/v1/appointments/{appt.id}",
            headers=mut(headers),
            json={"status": "completed"},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "completed"

    # Feature is off, so the GET ledger endpoint 403s — assert the table directly.
    count = await db_session.scalar(
        select(func.count())
        .select_from(LedgerEntry)
        .where(LedgerEntry.patient_id == appt.patient_id)
    )
    assert count == 0


async def test_checkout_with_no_procedures_posts_no_charge(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """Enabled practice + appointment with zero procedures: checkout succeeds and the
    ledger is empty (no 500, no phantom charge)."""
    practice, user, sub, appt = await _seed(
        db_session, billing_ledger=True, with_procedure=False
    )
    headers = {"Authorization": "Bearer test-token", "X-Practice-ID": str(practice.id)}
    h1, h2, h3 = _auth(sub, user.email)

    with h1, h2, h3:
        resp = await client.patch(
            f"/api/v1/appointments/{appt.id}",
            headers=mut(headers),
            json={"status": "completed"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "completed"

        ledger_resp = await client.get(
            f"/api/v1/patients/{appt.patient_id}/ledger",
            headers=headers,
        )

    assert ledger_resp.status_code == 200, ledger_resp.text
    body = ledger_resp.json()
    assert body["balanceCents"] == 0
    assert body["entries"] == []
