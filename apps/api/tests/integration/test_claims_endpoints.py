"""Integration tests for the claims submission POST endpoint."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt
from app.services.claims.base import ClaimResult, ClearinghouseClient, DentalClaimInput
from tests.integration.conftest import mut

pytestmark = pytest.mark.integration

# ── Auth patch targets (mirrored from test_copay_endpoints.py) ────────────────

_P_HEADER = "app.middleware.auth.jwt.get_unverified_header"
_P_KEY = "app.middleware.auth._get_public_key"
_P_DECODE = "app.middleware.auth.jwt.decode"


# ── Fake clearinghouse client ─────────────────────────────────────────────────


class _FakeClient(ClearinghouseClient):
    async def submit_dental_claim(
        self, claim: DentalClaimInput, idempotency_key: str
    ) -> ClaimResult:
        return ClaimResult(
            accepted=True,
            clearinghouse_claim_id="txn-1",
            clearinghouse_status="ACCEPTED",
            errors=[],
            raw_request={},
            raw_response={"transactionId": "txn-1"},
        )


# ── Seed helper (mirrored exactly from test_claims_service.py) ────────────────


async def _seed(session: AsyncSession, claims_submission_enabled: bool = True):
    from app.models.appointment import Appointment
    from app.models.appointment_procedure import AppointmentProcedure
    from app.models.insurance_plan import InsurancePlan
    from app.models.patient import Patient
    from app.models.patient_insurance import PatientInsurance
    from app.models.practice import Practice
    from app.models.provider import Provider
    from app.models.user import PracticeUser, User

    practice = Practice(
        id=uuid.uuid4(),
        name="Claims Endpoint Test Practice",
        features={"claims_submission": claims_submission_enabled},
        billing_npi="1234567890",
        billing_taxonomy_code="1223G0001X",
        billing_tax_id_encrypted=encrypt("123456789"),
        clearinghouse_submitter_id="SUB1",
        clearinghouse_provider="stedi",
        clearinghouse_api_key_ssm_path="/dental/staging/clearinghouse/api_key",
    )
    session.add(practice)

    provider = Provider(
        id=uuid.uuid4(),
        practice_id=practice.id,
        npi="1234567890",
        full_name="Jane Dentist",
        provider_type="dentist",
    )
    patient = Patient(
        id=uuid.uuid4(),
        practice_id=practice.id,
        first_name="John",
        last_name="Smith",
        date_of_birth=date(1980, 1, 1),
    )
    plan = InsurancePlan(
        id=uuid.uuid4(),
        practice_id=practice.id,
        payer_id="CDLA1",
        carrier_name="Cigna DPPO",
    )
    session.add_all([provider, patient, plan])

    insurance = PatientInsurance(
        id=uuid.uuid4(),
        practice_id=practice.id,
        patient_id=patient.id,
        priority="primary",
        carrier="Cigna",
        member_id="U123",
        group_number="GRP1",
        relationship_to_insured="self",
        insurance_plan_id=plan.id,
    )
    appt = Appointment(
        id=uuid.uuid4(),
        practice_id=practice.id,
        patient_id=patient.id,
        provider_id=provider.id,
        start_time=datetime(2026, 6, 18, 14, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 6, 18, 15, 0, tzinfo=timezone.utc),
    )
    session.add_all([insurance, appt])
    await session.flush()

    proc = AppointmentProcedure(
        id=uuid.uuid4(),
        practice_id=practice.id,
        appointment_id=appt.id,
        patient_id=patient.id,
        procedure_code="D2392",
        procedure_name="Resin",
        fee_cents=20000,
        tooth_number="14",
    )
    session.add(proc)

    # Seed the user + practice membership
    cognito_sub = f"claims-sub-{uuid.uuid4().hex}"
    user = User(
        id=uuid.uuid4(),
        cognito_sub=cognito_sub,
        email=f"claims-staff-{uuid.uuid4().hex[:6]}@test.local",
        full_name="Claims Staff",
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

    await session.commit()
    return practice, appt, user, cognito_sub


def _claim_url(appointment_id: uuid.UUID) -> str:
    return f"/api/v1/appointments/{appointment_id}/claim"


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestSubmitClaim:
    async def test_happy_path_201(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """POST /claim with valid seeded data returns 201 with expected body fields."""
        practice, appt, user, cognito_sub = await _seed(db_session)

        with (
            patch(_P_HEADER, return_value={"kid": "test-kid"}),
            patch(_P_KEY, new=AsyncMock(return_value="fake-public-key")),
            patch(
                _P_DECODE,
                return_value={
                    "sub": cognito_sub,
                    "email": user.email,
                    "cognito:groups": ["admin"],
                },
            ),
            patch(
                "app.routers.claims.get_ssm_parameter",
                return_value="fake-key",
            ),
            patch(
                "app.routers.claims.StediClaimsClient",
                return_value=_FakeClient(),
            ),
        ):
            headers = {
                "Authorization": "Bearer test-token",
                "X-Practice-ID": str(practice.id),
            }
            resp = await client.post(_claim_url(appt.id), headers=mut(headers))

        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "submitted"
        assert body["totalChargeCents"] == 20000
        assert body["clearinghouseClaimId"] == "txn-1"

    async def test_feature_gate_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Practice with claims_submission disabled returns 403."""
        practice, appt, user, cognito_sub = await _seed(
            db_session, claims_submission_enabled=False
        )

        with (
            patch(_P_HEADER, return_value={"kid": "test-kid"}),
            patch(_P_KEY, new=AsyncMock(return_value="fake-public-key")),
            patch(
                _P_DECODE,
                return_value={
                    "sub": cognito_sub,
                    "email": user.email,
                    "cognito:groups": ["admin"],
                },
            ),
        ):
            headers = {
                "Authorization": "Bearer test-token",
                "X-Practice-ID": str(practice.id),
            }
            resp = await client.post(_claim_url(appt.id), headers=mut(headers))

        assert resp.status_code == 403, resp.text

    async def test_missing_appointment_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """POST to a non-existent appointment UUID returns 404 with APPOINTMENT_NOT_FOUND."""
        practice, _appt, user, cognito_sub = await _seed(db_session)

        with (
            patch(_P_HEADER, return_value={"kid": "test-kid"}),
            patch(_P_KEY, new=AsyncMock(return_value="fake-public-key")),
            patch(
                _P_DECODE,
                return_value={
                    "sub": cognito_sub,
                    "email": user.email,
                    "cognito:groups": ["admin"],
                },
            ),
            patch(
                "app.routers.claims.get_ssm_parameter",
                return_value="fake-key",
            ),
            patch(
                "app.routers.claims.StediClaimsClient",
                return_value=_FakeClient(),
            ),
        ):
            headers = {
                "Authorization": "Bearer test-token",
                "X-Practice-ID": str(practice.id),
            }
            resp = await client.post(
                _claim_url(uuid.uuid4()),
                headers=mut(headers),
            )

        assert resp.status_code == 404, resp.text
        assert resp.json()["error"]["code"] == "APPOINTMENT_NOT_FOUND"
