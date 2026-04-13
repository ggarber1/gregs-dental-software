"""
Unit tests for GET/POST/PATCH /api/v1/patients.

Auth and DB are fully mocked — no real Postgres, Cognito, or Redis needed.
JWT verification is patched out; practice membership is stubbed per-test.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ── Constants ─────────────────────────────────────────────────────────────────

_PRACTICE_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_PATIENT_ID = uuid.uuid4()
_SUB = "cognito-sub-test"
_JWT_CLAIMS = {"sub": _SUB, "email": "staff@clinic.com", "cognito:groups": []}

_PATIENT_ROW_DEFAULTS: dict[str, Any] = {
    "id": _PATIENT_ID,
    "practice_id": _PRACTICE_ID,
    "first_name": "Jane",
    "last_name": "Doe",
    "date_of_birth": date(1985, 6, 15),
    "sex": "female",
    "phone": "555-1234",
    "email": "jane@example.com",
    "address_line1": "1 Main St",
    "address_line2": None,
    "city": "Boston",
    "state": "MA",
    "zip": "02101",
    "ssn_encrypted": None,
    "allergies": ["penicillin"],
    "medical_alerts": [],
    "medications": [],
    "marital_status": None,
    "doctor_notes": None,
    "sms_opt_out": False,
    "deleted_at": None,
    "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
    "last_accessed_by": None,
    "last_accessed_at": None,
    "emergency_contact_name": None,
    "emergency_contact_phone": None,
    "occupation": None,
    "employer": None,
    "referral_source": None,
    "last_xray_date": None,
}


def _make_patient_row(**overrides: Any) -> MagicMock:
    row = MagicMock()
    for k, v in {**_PATIENT_ROW_DEFAULTS, **overrides}.items():
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
    """
    Patch Cognito JWT validation and practice membership resolution.

    Yields (auth_headers) — the headers to include in each request.
    If practice_id is None, X-Practice-ID is omitted (no practice scope).
    """
    membership_result = (_USER_ID, role) if practice_id is not None else None

    headers: dict[str, str] = {"Authorization": "Bearer fake.jwt.token"}
    if practice_id is not None:
        headers["X-Practice-ID"] = str(practice_id)

    with (
        patch("jose.jwt.get_unverified_header", return_value={"kid": "fake-kid"}),
        patch(
            "app.middleware.auth._get_public_key",
            new=AsyncMock(return_value=object()),
        ),
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


def _copy_attrs(target: Any, source: MagicMock) -> None:
    """Copy mock row attributes onto a real PatientModel instance after session.add()."""
    for key in _PATIENT_ROW_DEFAULTS:
        if hasattr(target, key):
            setattr(target, key, getattr(source, key))


# ── POST /api/v1/patients ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_patient_returns_201():
    app = _get_app()
    mock_row = _make_patient_row()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.patients.get_session_factory") as mock_sf,
        patch("app.routers.patients.encrypt", return_value=b"encrypted"),
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.add = MagicMock(side_effect=lambda r: _copy_attrs(r, mock_row))
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/v1/patients",
                json={
                    "practiceId": str(_PRACTICE_ID),
                    "firstName": "Jane",
                    "lastName": "Doe",
                    "dateOfBirth": "1985-06-15",
                    "allergies": ["penicillin"],
                    "medicalAlerts": [],
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 201
    body = response.json()
    assert body["firstName"] == "Jane"
    assert body["lastName"] == "Doe"


@pytest.mark.asyncio
async def test_create_patient_practice_id_mismatch_returns_400():
    app = _get_app()

    with _auth_patches(practice_id=_PRACTICE_ID) as auth_headers:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/v1/patients",
                json={
                    "practiceId": str(uuid.uuid4()),  # intentionally different
                    "firstName": "Jane",
                    "lastName": "Doe",
                    "dateOfBirth": "1985-06-15",
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PRACTICE_ID_MISMATCH"


@pytest.mark.asyncio
async def test_create_patient_no_practice_scope_returns_403():
    app = _get_app()

    with _auth_patches(practice_id=None) as auth_headers:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/v1/patients",
                json={
                    "practiceId": str(_PRACTICE_ID),
                    "firstName": "Jane",
                    "lastName": "Doe",
                    "dateOfBirth": "1985-06-15",
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PRACTICE_SCOPE_REQUIRED"


@pytest.mark.asyncio
async def test_create_patient_read_only_role_returns_403():
    app = _get_app()

    with _auth_patches(role="read_only") as auth_headers:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/v1/patients",
                json={
                    "practiceId": str(_PRACTICE_ID),
                    "firstName": "Jane",
                    "lastName": "Doe",
                    "dateOfBirth": "1985-06-15",
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"


@pytest.mark.asyncio
async def test_create_patient_billing_role_returns_403():
    app = _get_app()

    with _auth_patches(role="billing") as auth_headers:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/v1/patients",
                json={
                    "practiceId": str(_PRACTICE_ID),
                    "firstName": "Jane",
                    "lastName": "Doe",
                    "dateOfBirth": "1985-06-15",
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"


# ── GET /api/v1/patients ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_patients_returns_200_with_meta():
    app = _get_app()
    mock_row = _make_patient_row()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.patients.get_session_factory") as mock_sf,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.scalar = AsyncMock(return_value=1)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_row]
        mock_session.scalars = AsyncMock(return_value=mock_scalars)
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/api/v1/patients", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "meta" in body
    assert body["meta"]["total"] == 1
    assert body["meta"]["page"] == 1
    assert len(body["data"]) == 1
    # SSN must not appear in list responses
    assert body["data"][0].get("ssnLastFour") is None


@pytest.mark.asyncio
async def test_list_patients_no_scope_returns_403():
    app = _get_app()

    with _auth_patches(practice_id=None) as auth_headers:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/api/v1/patients", headers=auth_headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PRACTICE_SCOPE_REQUIRED"


# ── GET /api/v1/patients/{id} ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_patient_returns_200_with_ssn():
    app = _get_app()
    mock_row = _make_patient_row(ssn_encrypted=b"blob")

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.patients.get_session_factory") as mock_sf,
        patch("app.routers.patients.decrypt", return_value="4321"),
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.scalar = AsyncMock(return_value=mock_row)
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(f"/api/v1/patients/{_PATIENT_ID}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["ssn"] == "4321"
    assert body["firstName"] == "Jane"


@pytest.mark.asyncio
async def test_get_patient_not_found_returns_404():
    app = _get_app()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.patients.get_session_factory") as mock_sf,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.scalar = AsyncMock(return_value=None)
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(f"/api/v1/patients/{uuid.uuid4()}", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PATIENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_patient_tenant_isolation():
    """DB returns None because practice_id WHERE clause doesn't match → 404."""
    app = _get_app()

    with (
        _auth_patches(practice_id=uuid.uuid4()) as auth_headers,
        patch("app.routers.patients.get_session_factory") as mock_sf,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.scalar = AsyncMock(return_value=None)
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(f"/api/v1/patients/{_PATIENT_ID}", headers=auth_headers)

    assert response.status_code == 404


# ── PATCH /api/v1/patients/{id} ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_patient_returns_200():
    app = _get_app()
    mock_row = _make_patient_row(phone="555-9999")

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.patients.get_session_factory") as mock_sf,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.scalar = AsyncMock(return_value=mock_row)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.patch(
                f"/api/v1/patients/{_PATIENT_ID}",
                json={"phone": "555-9999"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 200
    assert response.json()["phone"] == "555-9999"


@pytest.mark.asyncio
async def test_patch_patient_not_found_returns_404():
    app = _get_app()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.patients.get_session_factory") as mock_sf,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.scalar = AsyncMock(return_value=None)
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.patch(
                f"/api/v1/patients/{uuid.uuid4()}",
                json={"phone": "555-0000"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PATIENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_patch_patient_read_only_role_returns_403():
    app = _get_app()

    with _auth_patches(role="read_only") as auth_headers:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.patch(
                f"/api/v1/patients/{_PATIENT_ID}",
                json={"phone": "555-0000"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"
