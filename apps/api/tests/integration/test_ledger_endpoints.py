"""Integration tests for the patient ledger endpoints (Module 8a)."""
from __future__ import annotations

import datetime
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import mut

pytestmark = pytest.mark.integration

# ── Auth patch targets (mirrored from test_era_endpoints.py) ──────────────────

_P_HEADER = "app.middleware.auth.jwt.get_unverified_header"
_P_KEY = "app.middleware.auth._get_public_key"
_P_DECODE = "app.middleware.auth.jwt.decode"


# ── Seed helper (mirrors test_era_endpoints.py _seed, plus a Patient) ─────────


async def _seed(session: AsyncSession, ledger_enabled: bool = True, role: str = "admin"):
    from app.models.patient import Patient
    from app.models.practice import Practice
    from app.models.user import PracticeUser, User

    practice = Practice(
        id=uuid.uuid4(),
        name="Ledger Endpoint Test Practice",
        features={"billing_ledger": ledger_enabled},
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
            role=role,
            is_active=True,
        )
    )

    patient = Patient(
        id=uuid.uuid4(),
        practice_id=practice.id,
        first_name="Pat",
        last_name="Ledger",
        date_of_birth=datetime.date(1990, 1, 1),
    )
    session.add(patient)

    await session.commit()
    return practice, user, cognito_sub, patient


def _decoded(user, cognito_sub, groups=("admin",)):
    return {
        "sub": cognito_sub,
        "email": user.email,
        "cognito:groups": list(groups),
    }


def _auth_patches(decoded):
    return (
        patch(_P_HEADER, return_value={"kid": "test-kid"}),
        patch(_P_KEY, new=AsyncMock(return_value="fake-public-key")),
        patch(_P_DECODE, return_value=decoded),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestPaymentAndLedger:
    async def test_record_payment_then_get_ledger(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Post a $50 payment, then GET the ledger → balance -5000 with one entry."""
        practice, user, sub, patient = await _seed(db_session)
        decoded = _decoded(user, sub)
        headers = {
            "Authorization": "Bearer test-token",
            "X-Practice-ID": str(practice.id),
        }

        h, k, d = _auth_patches(decoded)
        with h, k, d:
            pay_resp = await client.post(
                f"/api/v1/patients/{patient.id}/payments",
                headers=mut(headers),
                json={"amountCents": 5000, "paymentMethod": "cash"},
            )
        assert pay_resp.status_code == 201, pay_resp.text
        pay_body = pay_resp.json()
        # Payments are stored as a negative entry.
        assert pay_body["amountCents"] == -5000
        assert pay_body["entryType"] == "patient_payment"

        h, k, d = _auth_patches(decoded)
        with h, k, d:
            ledger_resp = await client.get(
                f"/api/v1/patients/{patient.id}/ledger",
                headers=headers,
            )
        assert ledger_resp.status_code == 200, ledger_resp.text
        ledger = ledger_resp.json()
        assert ledger["balanceCents"] == -5000
        assert len(ledger["entries"]) == 1
        assert ledger["entries"][0]["runningBalanceCents"] == -5000

    async def test_payment_negative_amount_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """A negative amountCents is rejected by request validation (422)."""
        practice, user, sub, patient = await _seed(db_session)
        decoded = _decoded(user, sub)
        headers = {
            "Authorization": "Bearer test-token",
            "X-Practice-ID": str(practice.id),
        }

        h, k, d = _auth_patches(decoded)
        with h, k, d:
            resp = await client.post(
                f"/api/v1/patients/{patient.id}/payments",
                headers=mut(headers),
                json={"amountCents": -100, "paymentMethod": "cash"},
            )
        assert resp.status_code == 422, resp.text

    async def test_payment_patient_not_found_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """POST a payment for a patient_id not in the practice → 404 PATIENT_NOT_FOUND."""
        practice, user, sub, _patient = await _seed(db_session)
        decoded = _decoded(user, sub)
        headers = {
            "Authorization": "Bearer test-token",
            "X-Practice-ID": str(practice.id),
        }

        missing_patient_id = uuid.uuid4()
        h, k, d = _auth_patches(decoded)
        with h, k, d:
            resp = await client.post(
                f"/api/v1/patients/{missing_patient_id}/payments",
                headers=mut(headers),
                json={"amountCents": 5000, "paymentMethod": "cash"},
            )
        assert resp.status_code == 404, resp.text
        assert resp.json()["error"]["code"] == "PATIENT_NOT_FOUND"

    async def test_payment_non_write_role_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """A read_only user (non-write role + group) is rejected from posting a payment → 403."""
        practice, user, sub, patient = await _seed(db_session, role="read_only")
        decoded = _decoded(user, sub, groups=("read_only",))
        headers = {
            "Authorization": "Bearer test-token",
            "X-Practice-ID": str(practice.id),
        }

        h, k, d = _auth_patches(decoded)
        with h, k, d:
            resp = await client.post(
                f"/api/v1/patients/{patient.id}/payments",
                headers=mut(headers),
                json={"amountCents": 5000, "paymentMethod": "cash"},
            )
        assert resp.status_code == 403, resp.text
        assert resp.json()["error"]["code"] == "INSUFFICIENT_ROLE"

    async def test_get_ledger_feature_gate_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """GET ledger against a practice without billing_ledger enabled → 403."""
        practice, user, sub, patient = await _seed(db_session, ledger_enabled=False)
        decoded = _decoded(user, sub)
        headers = {
            "Authorization": "Bearer test-token",
            "X-Practice-ID": str(practice.id),
        }

        h, k, d = _auth_patches(decoded)
        with h, k, d:
            resp = await client.get(
                f"/api/v1/patients/{patient.id}/ledger",
                headers=headers,
            )
        assert resp.status_code == 403, resp.text


class TestAdjustment:
    async def test_adjustment_empty_memo_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """An empty memo is rejected by request validation (min length 1) → 422."""
        practice, user, sub, patient = await _seed(db_session)
        decoded = _decoded(user, sub)
        headers = {
            "Authorization": "Bearer test-token",
            "X-Practice-ID": str(practice.id),
        }

        h, k, d = _auth_patches(decoded)
        with h, k, d:
            resp = await client.post(
                f"/api/v1/patients/{patient.id}/adjustments",
                headers=mut(headers),
                json={"amountCents": -1000, "memo": ""},
            )
        assert resp.status_code == 422, resp.text
