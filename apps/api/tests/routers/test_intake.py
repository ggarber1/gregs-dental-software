"""
Tests for the intake form router — both public and staff endpoints.

Auth and DB are fully mocked — no real Postgres, Cognito, Redis, or Twilio needed.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ── Constants ─────────────────────────────────────────────────────────────────

_PRACTICE_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_PATIENT_ID = uuid.uuid4()
_INTAKE_ID = uuid.uuid4()
_TOKEN = "a" * 64  # 64-char hex token
_SUB = "cognito-sub-test"
_JWT_CLAIMS = {"sub": _SUB, "email": "staff@clinic.com", "cognito:groups": []}

_NOW = datetime(2026, 4, 9, 12, 0, 0)
_EXPIRES_AT = _NOW + timedelta(hours=72)


def _make_patient(**overrides: Any) -> MagicMock:
    row = MagicMock()
    defaults: dict[str, Any] = {
        "id": _PATIENT_ID,
        "practice_id": _PRACTICE_ID,
        "first_name": "Jane",
        "last_name": "Doe",
        "date_of_birth": datetime(1985, 6, 15).date(),
        "sex": "female",
        "phone": "555-1234",
        "email": "jane@example.com",
        "address_line1": None,
        "address_line2": None,
        "city": None,
        "state": None,
        "zip": None,
        "ssn_encrypted": None,
        "allergies": [],
        "medical_alerts": [],
        "sms_opt_out": False,
        "deleted_at": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "last_accessed_by": None,
        "last_accessed_at": None,
    }
    for k, v in {**defaults, **overrides}.items():
        setattr(row, k, v)
    return row


def _make_practice(**overrides: Any) -> MagicMock:
    row = MagicMock()
    defaults: dict[str, Any] = {
        "id": _PRACTICE_ID,
        "name": "Smile Dental",
    }
    for k, v in {**defaults, **overrides}.items():
        setattr(row, k, v)
    return row


def _make_intake(**overrides: Any) -> MagicMock:
    row = MagicMock()
    defaults: dict[str, Any] = {
        "id": _INTAKE_ID,
        "practice_id": _PRACTICE_ID,
        "patient_id": _PATIENT_ID,
        "token": _TOKEN,
        "status": "pending",
        "expires_at": _EXPIRES_AT,
        "responses_encrypted": None,
        "submission_ip": None,
        "submission_user_agent": None,
        "created_by": _USER_ID,
        "created_at": datetime(2026, 4, 9, tzinfo=UTC),
        "updated_at": datetime(2026, 4, 9, tzinfo=UTC),
    }
    for k, v in {**defaults, **overrides}.items():
        setattr(row, k, v)
    return row


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


# ── Public: GET /intake/form/{token} ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_intake_form_public_returns_200():
    app = _get_app()
    form = _make_intake(expires_at=datetime.now(UTC) + timedelta(hours=48))
    practice = _make_practice()
    patient = _make_patient()

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.scalar = AsyncMock(side_effect=[form, practice, patient])

    with patch("app.routers.intake.get_session_factory") as mock_sf:
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/intake/form/{_TOKEN}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["practiceName"] == "Smile Dental"
    assert body["patientFirstName"] == "Jane"


@pytest.mark.asyncio
async def test_get_intake_form_public_404_unknown_token():
    app = _get_app()

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.scalar = AsyncMock(return_value=None)

    with patch("app.routers.intake.get_session_factory") as mock_sf:
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/intake/form/unknowntoken")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_intake_form_public_410_expired():
    app = _get_app()
    form = _make_intake(
        status="pending",
        expires_at=datetime(2020, 1, 1),  # past
    )

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.scalar = AsyncMock(return_value=form)
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    with patch("app.routers.intake.get_session_factory") as mock_sf:
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/intake/form/{_TOKEN}")

    assert resp.status_code == 410
    assert resp.json()["error"]["code"] == "INTAKE_EXPIRED"


@pytest.mark.asyncio
async def test_get_intake_form_public_410_completed():
    app = _get_app()
    form = _make_intake(
        status="completed",
        expires_at=datetime.now(UTC) + timedelta(hours=48),
    )

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.scalar = AsyncMock(return_value=form)

    with patch("app.routers.intake.get_session_factory") as mock_sf:
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/intake/form/{_TOKEN}")

    assert resp.status_code == 410
    assert resp.json()["error"]["code"] == "INTAKE_COMPLETED"


# ── Public: POST /intake/form/{token}/submit ──────────────────────────────────

_VALID_SUBMIT = {
    "firstName": "Jane",
    "lastName": "Doe",
    "dateOfBirth": "1985-06-15",
    "sex": "female",
    "phone": "555-1234",
    "medicalConditions": [],
    "medications": [],
    "allergies": [],
    "hipaaConsentAccepted": True,
    "hipaaConsentTimestamp": "2026-04-09T12:00:00Z",
    "hipaaConsentSignature": "Jane Doe",
    "smsOptIn": True,
}


@pytest.mark.asyncio
async def test_submit_intake_form_returns_204():
    app = _get_app()
    form = _make_intake(expires_at=datetime.now(UTC) + timedelta(hours=48))

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.scalar = AsyncMock(return_value=form)
    session.execute = AsyncMock()
    session.commit = AsyncMock()

    with (
        patch("app.routers.intake.get_session_factory") as mock_sf,
        patch("app.routers.intake.encrypt", return_value=b"encrypted"),
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(f"/intake/form/{_TOKEN}/submit", json=_VALID_SUBMIT)

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_submit_intake_form_rejects_missing_hipaa_consent():
    app = _get_app()
    payload = {**_VALID_SUBMIT, "hipaaConsentAccepted": False}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post(f"/intake/form/{_TOKEN}/submit", json=payload)

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "HIPAA_CONSENT_REQUIRED"


@pytest.mark.asyncio
async def test_submit_intake_form_rejects_second_submission():
    app = _get_app()
    form = _make_intake(
        status="completed",
        expires_at=datetime.now(UTC) + timedelta(hours=48),
    )

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.scalar = AsyncMock(return_value=form)

    with patch("app.routers.intake.get_session_factory") as mock_sf:
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(f"/intake/form/{_TOKEN}/submit", json=_VALID_SUBMIT)

    assert resp.status_code == 410


# ── Staff: POST /api/v1/intake/send ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_intake_form_returns_201():
    app = _get_app()
    patient = _make_patient()
    practice = _make_practice()
    intake_row = _make_intake(expires_at=datetime.now(UTC) + timedelta(hours=72))

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.scalar = AsyncMock(side_effect=[patient, practice])
    session.add = MagicMock(side_effect=lambda r: setattr(r, "id", intake_row.id))
    session.commit = AsyncMock()
    session.refresh = AsyncMock(
        side_effect=lambda r: setattr(r, "expires_at", intake_row.expires_at)
    )

    with (
        _auth_patches() as headers,
        patch("app.routers.intake.get_session_factory") as mock_sf,
        patch("app.routers.intake.sms.send_sms", new=AsyncMock()),
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/intake/send",
                json={"patientId": str(_PATIENT_ID)},
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert resp.status_code == 201
    assert "intakeFormId" in resp.json()


@pytest.mark.asyncio
async def test_send_intake_form_422_no_phone():
    app = _get_app()
    patient = _make_patient(phone=None)

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.scalar = AsyncMock(return_value=patient)

    with (
        _auth_patches() as headers,
        patch("app.routers.intake.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/intake/send",
                json={"patientId": str(_PATIENT_ID)},
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "PATIENT_NO_PHONE"


@pytest.mark.asyncio
async def test_send_intake_form_422_sms_opt_out():
    app = _get_app()
    patient = _make_patient(sms_opt_out=True)

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.scalar = AsyncMock(return_value=patient)

    with (
        _auth_patches() as headers,
        patch("app.routers.intake.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/v1/intake/send",
                json={"patientId": str(_PATIENT_ID)},
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "PATIENT_SMS_OPT_OUT"


# ── Staff: GET /api/v1/intake ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_intake_forms_returns_list():
    app = _get_app()
    form = _make_intake()

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.scalars = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[form])))

    with (
        _auth_patches() as headers,
        patch("app.routers.intake.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/intake", headers=headers)

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["id"] == str(_INTAKE_ID)


# ── Staff: GET /api/v1/intake/{id} ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_intake_form_detail_returns_responses():
    app = _get_app()
    form = _make_intake(
        status="completed",
        responses_encrypted=b"encrypted",
    )

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.scalar = AsyncMock(return_value=form)

    decrypted = '{"firstName": "Jane", "lastName": "Doe"}'

    with (
        _auth_patches() as headers,
        patch("app.routers.intake.get_session_factory") as mock_sf,
        patch("app.routers.intake.decrypt", return_value=decrypted),
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(f"/api/v1/intake/{_INTAKE_ID}", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["responses"]["firstName"] == "Jane"


# ── Staff: POST /api/v1/intake/{id}/apply ─────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_intake_form_updates_patient():
    app = _get_app()
    form = _make_intake(
        status="completed",
        responses_encrypted=b"encrypted",
    )
    patient = _make_patient()

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.scalar = AsyncMock(side_effect=[form, patient])
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    decrypted = (
        '{"firstName": "Janet", "lastName": "Doe", "dateOfBirth": "1985-06-15", '
        '"sex": "female", "phone": "555-5678", "allergies": ["penicillin"], '
        '"medicalConditions": ["Diabetes"], "medications": ["Metformin"], '
        '"smsOptIn": true, "hipaaConsentAccepted": true, '
        '"hipaaConsentTimestamp": "2026-04-09T12:00:00Z", '
        '"hipaaConsentSignature": "Janet Doe"}'
    )

    with (
        _auth_patches() as headers,
        patch("app.routers.intake.get_session_factory") as mock_sf,
        patch("app.routers.intake.decrypt", return_value=decrypted),
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/intake/{_INTAKE_ID}/apply",
                json={},
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert resp.status_code == 200
    # Patient first_name updated to Janet
    assert patient.first_name == "Janet"
    assert patient.sms_opt_out is False  # smsOptIn=true → sms_opt_out=false


@pytest.mark.asyncio
async def test_apply_intake_form_422_not_completed():
    app = _get_app()
    form = _make_intake(status="pending")

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.scalar = AsyncMock(return_value=form)

    with (
        _auth_patches() as headers,
        patch("app.routers.intake.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/api/v1/intake/{_INTAKE_ID}/apply",
                json={},
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INTAKE_NOT_COMPLETED"
