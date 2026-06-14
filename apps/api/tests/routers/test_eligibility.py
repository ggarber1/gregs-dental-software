from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from app.services.eligibility.base import (
    EligibilityProviderError,
    EligibilityResult,
    EligibilityStatus,
)

_PRACTICE_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_PATIENT_ID = uuid.uuid4()
_INSURANCE_ID = uuid.uuid4()
_PLAN_ID = uuid.uuid4()
_JWT_CLAIMS = {"sub": "sub-test", "email": "staff@clinic.com", "cognito:groups": []}


def _get_app():
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    os.environ.setdefault("APP_ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ=")
    from app.main import create_app

    return create_app()


def _result(status: EligibilityStatus = EligibilityStatus.ACTIVE) -> EligibilityResult:
    return EligibilityResult(
        raw_response={"ok": True}, payer_name="Delta Dental", plan_name="PPO",
        status=status, coverage_start_date=date(2026, 1, 1), coverage_end_date=date(2026, 12, 31),
        deductible_individual=5000, deductible_individual_met=None, deductible_family=None,
        deductible_family_met=None, oop_max_individual=None, oop_max_individual_met=None,
        annual_max_individual=150000, annual_max_individual_used=None,
        annual_max_individual_remaining=120000, coinsurance_preventive=0.0,
        coinsurance_basic=0.2, coinsurance_major=0.5, coinsurance_ortho=None,
        waiting_period_basic_months=None, waiting_period_major_months=None,
        waiting_period_ortho_months=None, frequency_limits=None,
    )


def _practice(features: dict[str, Any]) -> MagicMock:
    return MagicMock(
        id=_PRACTICE_ID, features=features, billing_npi="1234567890",
        clearinghouse_submitter_id="SUB1", clearinghouse_api_key_ssm_path="/dental/stedi",
        clearinghouse_provider="stedi",
    )


def _insurance() -> MagicMock:
    return MagicMock(
        id=_INSURANCE_ID, patient_id=_PATIENT_ID, practice_id=_PRACTICE_ID,
        insurance_plan_id=_PLAN_ID, relationship_to_insured="self", member_id="XYZ123",
        group_number="GRP001", insured_first_name=None, insured_last_name=None,
        insured_date_of_birth=None, deleted_at=None,
    )


def _patient() -> MagicMock:
    return MagicMock(
        id=_PATIENT_ID, first_name="John", last_name="Smith", date_of_birth=date(1980, 1, 1),
    )


def _plan() -> MagicMock:
    return MagicMock(id=_PLAN_ID, payer_id="CDELT", carrier_name="Delta Dental")


@contextmanager
def _auth_patches(role: str = "front_desk"):
    headers = {"Authorization": "Bearer fake.jwt.token", "X-Practice-ID": str(_PRACTICE_ID)}
    with (
        patch("jose.jwt.get_unverified_header", return_value={"kid": "fake-kid"}),
        patch("app.middleware.auth._get_public_key", new=AsyncMock(return_value=object())),
        patch("jose.jwt.decode", return_value=_JWT_CLAIMS),
        patch(
            "app.middleware.auth._resolve_practice_membership",
            new=AsyncMock(return_value=(_USER_ID, role)),
        ),
        patch(
            "app.middleware.idempotency.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), setex=AsyncMock()),
        ),
    ):
        yield headers


def _session_for_check(*, feature_on: bool) -> Any:
    """A session whose scalar() returns practice, insurance, plan, patient in router call order."""
    session = MagicMock()
    practice = _practice({"eligibility_verification": feature_on})
    session.scalar = AsyncMock(side_effect=[practice, _insurance(), _plan(), _patient()])
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


async def test_check_feature_disabled_returns_403():
    app = _get_app()
    session = MagicMock()
    session.scalar = AsyncMock(return_value=_practice({}))
    with _auth_patches() as headers, patch("app.routers.eligibility.get_session_factory") as sf:
        sf.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
        sf.return_value.return_value.__aexit__ = AsyncMock(return_value=None)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/eligibility/check",
                json={"patientInsuranceId": str(_INSURANCE_ID)},
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert resp.status_code == 403


async def test_check_happy_path_returns_verified():
    app = _get_app()
    fake_provider = MagicMock()
    fake_provider.check_eligibility = AsyncMock(return_value=_result())
    session = _session_for_check(feature_on=True)
    with (
        _auth_patches() as headers, patch("app.routers.eligibility.get_session_factory") as sf,
        patch("app.routers.eligibility.get_ssm_parameter", return_value="api-key"),
        patch("app.routers.eligibility.StediProvider", return_value=fake_provider),
    ):
        sf.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
        sf.return_value.return_value.__aexit__ = AsyncMock(return_value=None)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/eligibility/check",
                json={"patientInsuranceId": str(_INSURANCE_ID)},
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "verified"
    assert body["coverageStatus"] == "active"
    assert body["deductibleIndividual"] == 5000


async def test_check_provider_error_marks_failed():
    app = _get_app()
    fake_provider = MagicMock()
    fake_provider.check_eligibility = AsyncMock(
        side_effect=EligibilityProviderError("boom", retryable=True)
    )
    session = _session_for_check(feature_on=True)
    with (
        _auth_patches() as headers, patch("app.routers.eligibility.get_session_factory") as sf,
        patch("app.routers.eligibility.get_ssm_parameter", return_value="api-key"),
        patch("app.routers.eligibility.StediProvider", return_value=fake_provider),
    ):
        sf.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
        sf.return_value.return_value.__aexit__ = AsyncMock(return_value=None)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/eligibility/check",
                json={"patientInsuranceId": str(_INSURANCE_ID)},
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "failed"
    assert body["failureReason"]


async def test_check_payer_not_found_marks_not_supported():
    app = _get_app()
    fake_provider = MagicMock()
    fake_provider.check_eligibility = AsyncMock(
        side_effect=EligibilityProviderError("nope", not_supported=True)
    )
    session = _session_for_check(feature_on=True)
    with (
        _auth_patches() as headers, patch("app.routers.eligibility.get_session_factory") as sf,
        patch("app.routers.eligibility.get_ssm_parameter", return_value="api-key"),
        patch("app.routers.eligibility.StediProvider", return_value=fake_provider),
    ):
        sf.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
        sf.return_value.return_value.__aexit__ = AsyncMock(return_value=None)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/eligibility/check",
                json={"patientInsuranceId": str(_INSURANCE_ID)},
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert resp.json()["status"] == "not_supported"
