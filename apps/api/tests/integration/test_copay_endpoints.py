"""Integration tests for copay-estimate POST/GET/PATCH endpoints."""
from __future__ import annotations

import uuid
from contextlib import ExitStack
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import mut

pytestmark = pytest.mark.integration

_PAYER = "62308"

_P_HEADER = "app.middleware.auth.jwt.get_unverified_header"
_P_KEY = "app.middleware.auth._get_public_key"
_P_DECODE = "app.middleware.auth.jwt.decode"


def _auth_patches(cognito_sub: str, email: str, groups: list[str]) -> ExitStack:
    stack = ExitStack()
    stack.enter_context(patch(_P_HEADER, return_value={"kid": "test-kid"}))
    stack.enter_context(patch(_P_KEY, new=AsyncMock(return_value="fake-public-key")))
    stack.enter_context(
        patch(
            _P_DECODE,
            return_value={"sub": cognito_sub, "email": email, "cognito:groups": groups},
        )
    )
    return stack


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def ce_practice(db_session: AsyncSession):
    """Practice with both feature flags enabled."""
    from app.models.practice import Practice

    p = Practice(
        id=uuid.uuid4(),
        name="Copay Endpoint Test Practice",
        timezone="America/New_York",
        features={"copay_estimation": True, "eligibility_verification": True},
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def ce_staff_user(db_session: AsyncSession, ce_practice):
    """Admin user for ce_practice."""
    from app.models.user import PracticeUser, User

    cognito_sub = f"ce-sub-{uuid.uuid4().hex}"
    user = User(
        id=uuid.uuid4(),
        cognito_sub=cognito_sub,
        email=f"ce-staff-{uuid.uuid4().hex[:6]}@test.local",
        full_name="CE Staff",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    pu = PracticeUser(
        practice_id=ce_practice.id,
        user_id=user.id,
        role="admin",
        is_active=True,
    )
    db_session.add(pu)
    await db_session.commit()
    return user, cognito_sub


@pytest_asyncio.fixture
async def ce_auth_headers(ce_practice, ce_staff_user):
    """Auth headers scoped to ce_practice."""
    user, cognito_sub = ce_staff_user
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
        yield {
            "Authorization": "Bearer test-token",
            "X-Practice-ID": str(ce_practice.id),
        }


@pytest_asyncio.fixture
async def ce_patient(db_session: AsyncSession, ce_practice):
    from app.models.patient import Patient

    pt = Patient(
        id=uuid.uuid4(),
        practice_id=ce_practice.id,
        first_name="Copay",
        last_name="Patient",
        date_of_birth=date(1985, 3, 10),
    )
    db_session.add(pt)
    await db_session.commit()
    await db_session.refresh(pt)
    return pt


@pytest_asyncio.fixture
async def ce_appointment(db_session: AsyncSession, ce_practice, ce_patient):
    from app.models.appointment import Appointment

    start = datetime.now(UTC) + timedelta(days=1)
    appt = Appointment(
        id=uuid.uuid4(),
        practice_id=ce_practice.id,
        patient_id=ce_patient.id,
        start_time=start,
        end_time=start + timedelta(minutes=60),
        status="scheduled",
    )
    db_session.add(appt)
    await db_session.commit()
    await db_session.refresh(appt)
    return appt


async def _seed_cdt_code(
    session: AsyncSession, code: str, category: str, description: str
):
    from app.models.appointment_procedure import CdtCode

    existing = await session.scalar(select(CdtCode).where(CdtCode.code == code))
    if existing:
        return existing
    c = CdtCode(
        id=uuid.uuid4(),
        code=code,
        description=description,
        category=category,
        is_active=True,
    )
    session.add(c)
    await session.flush()
    return c


async def _seed_procedure(
    session: AsyncSession,
    practice_id: uuid.UUID,
    appointment_id: uuid.UUID,
    patient_id: uuid.UUID,
    cdt,
    fee_cents: int,
):
    from app.models.appointment_procedure import AppointmentProcedure

    p = AppointmentProcedure(
        id=uuid.uuid4(),
        practice_id=practice_id,
        appointment_id=appointment_id,
        patient_id=patient_id,
        cdt_code_id=cdt.id,
        procedure_code=cdt.code,
        procedure_name=cdt.description,
        fee_cents=fee_cents,
    )
    session.add(p)
    await session.flush()
    return p


async def _seed_eligibility(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    **overrides: object,
):
    from app.models.eligibility_check import EligibilityCheck

    defaults: dict = {
        "id": uuid.uuid4(),
        "practice_id": practice_id,
        "patient_id": patient_id,
        "patient_insurance_id": uuid.uuid4(),
        "idempotency_key": str(uuid.uuid4()),
        "status": "verified",
        "trigger": "manual",
        "clearinghouse": "stedi",
        "payer_id_used": _PAYER,
        "plan_type": "ppo",
        "network_status": "in_network",
        "deductible_waived_preventive": True,
        "deductible_waived_diagnostic": False,
        "deductible_waived_orthodontic": False,
    }
    defaults.update(overrides)
    check = EligibilityCheck(**defaults)
    session.add(check)
    await session.flush()
    return check


async def _seed_contracted_fee(
    session: AsyncSession,
    practice_id: uuid.UUID,
    cdt_code_id: uuid.UUID,
    allowed_amount_cents: int,
):
    from app.models.contracted_fee_schedule import ContractedFeeSchedule

    cf = ContractedFeeSchedule(
        id=uuid.uuid4(),
        practice_id=practice_id,
        payer_id=_PAYER,
        cdt_code_id=cdt_code_id,
        allowed_amount_cents=allowed_amount_cents,
        not_covered=False,
        requires_prior_auth=False,
    )
    session.add(cf)
    await session.flush()
    return cf


def _post_url(appointment_id: uuid.UUID) -> str:
    return f"/api/v1/appointments/{appointment_id}/copay-estimate"


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestPostCopayEstimate:
    async def test_happy_path_201(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ce_auth_headers: dict,
        ce_practice,
        ce_patient,
        ce_appointment,
    ):
        """POST creates a 201 estimate; line items present; procedure rows updated."""
        cdt = await _seed_cdt_code(
            db_session, "D2392", "basic", "Resin-based composite - two surfaces"
        )
        await _seed_procedure(
            db_session,
            ce_practice.id,
            ce_appointment.id,
            ce_patient.id,
            cdt,
            fee_cents=20000,
        )
        await _seed_contracted_fee(db_session, ce_practice.id, cdt.id, 18000)
        await _seed_eligibility(
            db_session,
            ce_practice.id,
            ce_patient.id,
            coinsurance_by_code={"D2392": 0.20},
            deductible_individual=5000,
            deductible_individual_met=0,
            annual_max_individual_remaining=200000,
        )
        await db_session.commit()

        resp = await client.post(
            _post_url(ce_appointment.id),
            headers=mut(ce_auth_headers),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["totalPatientOwesCents"] == 7600
        assert body["totalInsuranceOwesCents"] == 10400
        assert body["planType"] == "ppo"
        assert len(body["lineItems"]) == 1
        li = body["lineItems"][0]
        # Confirm camelCase keys are present
        assert "cdtCode" in li
        assert "providerFeeCents" in li
        assert "patientOwesCents" in li
        assert li["cdtCode"] == "D2392"
        assert body["appointmentId"] == str(ce_appointment.id)

    async def test_missing_appointment_404(
        self,
        client: AsyncClient,
        ce_auth_headers: dict,
    ):
        resp = await client.post(
            _post_url(uuid.uuid4()),
            headers=mut(ce_auth_headers),
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["error"]["code"] == "APPOINTMENT_NOT_FOUND"

    async def test_no_procedures_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ce_auth_headers: dict,
        ce_practice,
        ce_patient,
        ce_appointment,
    ):
        await _seed_eligibility(db_session, ce_practice.id, ce_patient.id)
        await db_session.commit()

        resp = await client.post(
            _post_url(ce_appointment.id),
            headers=mut(ce_auth_headers),
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["error"]["code"] == "NO_PROCEDURES"


class TestGetCopayEstimate:
    async def test_get_returns_latest_snapshot(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ce_auth_headers: dict,
        ce_practice,
        ce_patient,
        ce_appointment,
    ):
        cdt = await _seed_cdt_code(db_session, "D1110", "preventive", "Prophylaxis adult")
        await _seed_procedure(
            db_session,
            ce_practice.id,
            ce_appointment.id,
            ce_patient.id,
            cdt,
            fee_cents=12000,
        )
        await _seed_contracted_fee(db_session, ce_practice.id, cdt.id, 10000)
        await _seed_eligibility(
            db_session,
            ce_practice.id,
            ce_patient.id,
            coinsurance_by_code={"D1110": 0.0},
            deductible_individual=0,
            deductible_individual_met=0,
            annual_max_individual_remaining=150000,
        )
        await db_session.commit()

        post_resp = await client.post(
            _post_url(ce_appointment.id),
            headers=mut(ce_auth_headers),
        )
        assert post_resp.status_code == 201, post_resp.text
        post_body = post_resp.json()

        get_resp = await client.get(
            _post_url(ce_appointment.id),
            headers=ce_auth_headers,
        )
        assert get_resp.status_code == 200, get_resp.text
        get_body = get_resp.json()
        assert get_body["id"] == post_body["id"]
        assert get_body["totalPatientOwesCents"] == post_body["totalPatientOwesCents"]

    async def test_get_no_estimate_404(
        self,
        client: AsyncClient,
        ce_auth_headers: dict,
        ce_appointment,
    ):
        resp = await client.get(
            _post_url(ce_appointment.id),
            headers=ce_auth_headers,
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["error"]["code"] == "COPAY_ESTIMATE_NOT_FOUND"


class TestPatchCopayEstimate:
    async def test_patch_sets_override(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ce_auth_headers: dict,
        ce_practice,
        ce_patient,
        ce_appointment,
    ):
        cdt = await _seed_cdt_code(db_session, "D0274", "diagnostic", "Bitewing x-rays")
        await _seed_procedure(
            db_session,
            ce_practice.id,
            ce_appointment.id,
            ce_patient.id,
            cdt,
            fee_cents=8000,
        )
        await _seed_contracted_fee(db_session, ce_practice.id, cdt.id, 7000)
        await _seed_eligibility(
            db_session,
            ce_practice.id,
            ce_patient.id,
            coinsurance_by_code={"D0274": 0.20},
            deductible_individual=0,
            deductible_individual_met=0,
            annual_max_individual_remaining=150000,
        )
        await db_session.commit()

        await client.post(_post_url(ce_appointment.id), headers=mut(ce_auth_headers))

        patch_resp = await client.patch(
            _post_url(ce_appointment.id),
            json={"overridePatientCents": 500, "overrideNote": "Patient hardship"},
            headers=mut(ce_auth_headers),
        )
        assert patch_resp.status_code == 200, patch_resp.text
        body = patch_resp.json()
        assert body["overridePatientCents"] == 500
        assert body["overrideNote"] == "Patient hardship"

    async def test_patch_null_clears_override(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        ce_auth_headers: dict,
        ce_practice,
        ce_patient,
        ce_appointment,
    ):
        cdt = await _seed_cdt_code(db_session, "D0220", "diagnostic", "Periapical x-ray")
        await _seed_procedure(
            db_session,
            ce_practice.id,
            ce_appointment.id,
            ce_patient.id,
            cdt,
            fee_cents=5000,
        )
        await _seed_contracted_fee(db_session, ce_practice.id, cdt.id, 4500)
        await _seed_eligibility(
            db_session,
            ce_practice.id,
            ce_patient.id,
            coinsurance_by_code={"D0220": 0.20},
            deductible_individual=0,
            deductible_individual_met=0,
            annual_max_individual_remaining=150000,
        )
        await db_session.commit()

        await client.post(_post_url(ce_appointment.id), headers=mut(ce_auth_headers))

        # Set an override first.
        await client.patch(
            _post_url(ce_appointment.id),
            json={"overridePatientCents": 250, "overrideNote": "Note"},
            headers=mut(ce_auth_headers),
        )

        # Clear it by passing null.
        patch_resp = await client.patch(
            _post_url(ce_appointment.id),
            json={"overridePatientCents": None, "overrideNote": None},
            headers=mut(ce_auth_headers),
        )
        assert patch_resp.status_code == 200, patch_resp.text
        assert patch_resp.json()["overridePatientCents"] is None
        assert patch_resp.json()["overrideNote"] is None


class TestFeatureGate:
    async def test_no_copay_feature_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Practice without copay_estimation gets 403 on POST and GET."""
        from app.models.practice import Practice
        from app.models.user import PracticeUser, User

        p = Practice(
            id=uuid.uuid4(),
            name="No Feature Practice",
            timezone="America/Chicago",
            features={"copay_estimation": False, "eligibility_verification": True},
        )
        db_session.add(p)
        await db_session.commit()

        cognito_sub = f"nf-sub-{uuid.uuid4().hex}"
        user = User(
            id=uuid.uuid4(),
            cognito_sub=cognito_sub,
            email=f"nf-{uuid.uuid4().hex[:6]}@test.local",
            full_name="No Feature Staff",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()
        db_session.add(
            PracticeUser(practice_id=p.id, user_id=user.id, role="admin", is_active=True)
        )
        await db_session.commit()

        appt_id = uuid.uuid4()

        with _auth_patches(cognito_sub, user.email, ["admin"]):
            headers = {"Authorization": "Bearer t", "X-Practice-ID": str(p.id)}
            post_resp = await client.post(
                _post_url(appt_id),
                headers=mut(headers),
            )
            get_resp = await client.get(
                _post_url(appt_id),
                headers=headers,
            )
            patch_resp = await client.patch(
                _post_url(appt_id),
                json={"overridePatientCents": 1000},
                headers=mut(headers),
            )

        assert post_resp.status_code == 403, post_resp.text
        assert get_resp.status_code == 403, get_resp.text
        assert patch_resp.status_code == 403, patch_resp.text
