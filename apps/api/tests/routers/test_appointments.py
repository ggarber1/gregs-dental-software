"""
Unit tests for GET/POST/PATCH/DELETE /api/v1/appointments.

Auth and DB are fully mocked — no real Postgres, Cognito, or Redis needed.
JWT verification is patched out; practice membership is stubbed per-test.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ── Constants ─────────────────────────────────────────────────────────────────

_PRACTICE_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_PATIENT_ID = uuid.uuid4()
_PROVIDER_ID = uuid.uuid4()
_OPERATORY_ID = uuid.uuid4()
_APPOINTMENT_TYPE_ID = uuid.uuid4()
_APPOINTMENT_ID = uuid.uuid4()
_SUB = "cognito-sub-test"
_JWT_CLAIMS = {"sub": _SUB, "email": "staff@clinic.com", "cognito:groups": []}


# ── Helpers ──────────────────────────────────────────────────────────────────


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


def _make_patient_row(**overrides: Any) -> MagicMock:
    defaults = {
        "id": _PATIENT_ID,
        "practice_id": _PRACTICE_ID,
        "first_name": "Jane",
        "last_name": "Doe",
        "sms_opt_out": False,
        "deleted_at": None,
    }
    row = MagicMock()
    for k, v in {**defaults, **overrides}.items():
        setattr(row, k, v)
    return row


def _make_practice_row(**overrides: Any) -> MagicMock:
    defaults = {
        "id": _PRACTICE_ID,
        "reminder_hours": [48, 24],
    }
    row = MagicMock()
    for k, v in {**defaults, **overrides}.items():
        setattr(row, k, v)
    return row


def _make_provider_row(**overrides: Any) -> MagicMock:
    defaults = {
        "id": _PROVIDER_ID,
        "practice_id": _PRACTICE_ID,
        "full_name": "Dr. Smith",
        "npi": "1234567890",
        "provider_type": "dentist",
        "deleted_at": None,
    }
    row = MagicMock()
    for k, v in {**defaults, **overrides}.items():
        setattr(row, k, v)
    return row


def _make_operatory_row(**overrides: Any) -> MagicMock:
    defaults = {
        "id": _OPERATORY_ID,
        "practice_id": _PRACTICE_ID,
        "name": "Operatory 1",
        "deleted_at": None,
    }
    row = MagicMock()
    for k, v in {**defaults, **overrides}.items():
        setattr(row, k, v)
    return row


def _make_appointment_type_row(**overrides: Any) -> MagicMock:
    defaults = {
        "id": _APPOINTMENT_TYPE_ID,
        "practice_id": _PRACTICE_ID,
        "name": "Cleaning",
        "color": "#5B8DEF",
        "duration_minutes": 30,
        "deleted_at": None,
    }
    row = MagicMock()
    for k, v in {**defaults, **overrides}.items():
        setattr(row, k, v)
    return row


def _make_appointment_row(**overrides: Any) -> MagicMock:
    patient_mock = _make_patient_row()
    provider_mock = _make_provider_row()
    operatory_mock = _make_operatory_row()
    appt_type_mock = _make_appointment_type_row()

    defaults: dict[str, Any] = {
        "id": _APPOINTMENT_ID,
        "practice_id": _PRACTICE_ID,
        "patient_id": _PATIENT_ID,
        "provider_id": _PROVIDER_ID,
        "operatory_id": _OPERATORY_ID,
        "appointment_type_id": _APPOINTMENT_TYPE_ID,
        "start_time": datetime(2026, 6, 15, 9, 0, tzinfo=UTC),
        "end_time": datetime(2026, 6, 15, 9, 30, tzinfo=UTC),
        "status": "scheduled",
        "notes": None,
        "cancellation_reason": None,
        "deleted_at": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
        "patient": patient_mock,
        "provider": provider_mock,
        "operatory": operatory_mock,
        "appointment_type": appt_type_mock,
    }
    row = MagicMock()
    for k, v in {**defaults, **overrides}.items():
        setattr(row, k, v)
    return row


def _mock_session() -> AsyncMock:
    """Create a mock async session with context-manager support."""
    # Default execute result: empty reminder summary (no reminder rows).
    _empty_execute = MagicMock()
    _empty_execute.all.return_value = []

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock(return_value=_empty_execute)
    return session


def _empty_scalars_result() -> MagicMock:
    """A mock result for session.scalars() that returns an empty list on .all()."""
    result = MagicMock()
    result.all.return_value = []
    return result


def _create_payload(
    *,
    patient_id: uuid.UUID = _PATIENT_ID,
    provider_id: uuid.UUID = _PROVIDER_ID,
    operatory_id: uuid.UUID = _OPERATORY_ID,
    appointment_type_id: uuid.UUID | None = _APPOINTMENT_TYPE_ID,
    start_time: str = "2026-06-15T09:00:00Z",
    end_time: str = "2026-06-15T09:30:00Z",
    notes: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "patientId": str(patient_id),
        "providerId": str(provider_id),
        "operatoryId": str(operatory_id),
        "startTime": start_time,
        "endTime": end_time,
    }
    if appointment_type_id is not None:
        payload["appointmentTypeId"] = str(appointment_type_id)
    if notes is not None:
        payload["notes"] = notes
    return payload


# ── POST /api/v1/appointments ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_appointment_returns_201():
    app = _get_app()
    patient_row = _make_patient_row()
    provider_row = _make_provider_row()
    operatory_row = _make_operatory_row()
    appt_type_row = _make_appointment_type_row()
    practice_row = _make_practice_row()
    appointment_row = _make_appointment_row()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.appointments.get_session_factory") as mock_sf,
    ):
        mock_session = _mock_session()

        # session.scalar is called for:
        #   1. Patient lookup
        #   2. Provider lookup
        #   3. Operatory lookup
        #   4. AppointmentType lookup
        #   5. Practice lookup (for reminder_hours)
        #   6. Re-fetch after commit (with selectinload)
        mock_session.scalar = AsyncMock(
            side_effect=[
                patient_row,
                provider_row,
                operatory_row,
                appt_type_row,
                practice_row,
                appointment_row,
            ]
        )

        # session.scalars is called for conflict checks:
        #   1. Provider conflict -> no conflicts
        #   2. Operatory conflict -> no conflicts
        mock_session.scalars = AsyncMock(
            side_effect=[_empty_scalars_result(), _empty_scalars_result()]
        )

        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/v1/appointments",
                json=_create_payload(),
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 201
    body = response.json()
    assert body["patientId"] == str(_PATIENT_ID)
    assert body["providerId"] == str(_PROVIDER_ID)
    assert body["operatoryId"] == str(_OPERATORY_ID)
    assert body["status"] == "scheduled"
    assert body["patientName"] == "Jane Doe"
    assert body["providerName"] == "Dr. Smith"
    assert body["operatoryName"] == "Operatory 1"
    assert body["appointmentTypeName"] == "Cleaning"


@pytest.mark.asyncio
async def test_create_appointment_provider_conflict_returns_409():
    app = _get_app()
    patient_row = _make_patient_row()
    provider_row = _make_provider_row()
    operatory_row = _make_operatory_row()
    appt_type_row = _make_appointment_type_row()

    # An existing appointment that conflicts on the provider
    conflicting_row = _make_appointment_row(id=uuid.uuid4())

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.appointments.get_session_factory") as mock_sf,
    ):
        mock_session = _mock_session()

        # FK lookups all succeed
        mock_session.scalar = AsyncMock(
            side_effect=[patient_row, provider_row, operatory_row, appt_type_row]
        )

        # Provider conflict returns a hit; operatory check should not be reached
        # because the router collects all conflicts and returns them together,
        # so both checks run.
        provider_conflict_result = MagicMock()
        provider_conflict_result.all.return_value = [conflicting_row]
        operatory_no_conflict = _empty_scalars_result()
        mock_session.scalars = AsyncMock(
            side_effect=[provider_conflict_result, operatory_no_conflict]
        )

        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/v1/appointments",
                json=_create_payload(),
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "SCHEDULING_CONFLICT"
    conflicts = body["error"]["details"]["conflicts"]
    assert any(c["type"] == "provider" for c in conflicts)


@pytest.mark.asyncio
async def test_create_appointment_operatory_conflict_returns_409():
    app = _get_app()
    patient_row = _make_patient_row()
    provider_row = _make_provider_row()
    operatory_row = _make_operatory_row()
    appt_type_row = _make_appointment_type_row()

    conflicting_row = _make_appointment_row(id=uuid.uuid4())

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.appointments.get_session_factory") as mock_sf,
    ):
        mock_session = _mock_session()

        mock_session.scalar = AsyncMock(
            side_effect=[patient_row, provider_row, operatory_row, appt_type_row]
        )

        # Provider has no conflict; operatory has a conflict
        provider_no_conflict = _empty_scalars_result()
        operatory_conflict_result = MagicMock()
        operatory_conflict_result.all.return_value = [conflicting_row]
        mock_session.scalars = AsyncMock(
            side_effect=[provider_no_conflict, operatory_conflict_result]
        )

        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/v1/appointments",
                json=_create_payload(),
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "SCHEDULING_CONFLICT"
    conflicts = body["error"]["details"]["conflicts"]
    assert any(c["type"] == "operatory" for c in conflicts)


@pytest.mark.asyncio
async def test_create_appointment_no_practice_scope_returns_403():
    app = _get_app()

    with _auth_patches(practice_id=None) as auth_headers:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/v1/appointments",
                json=_create_payload(),
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PRACTICE_SCOPE_REQUIRED"


@pytest.mark.asyncio
async def test_create_appointment_read_only_role_returns_403():
    app = _get_app()

    with _auth_patches(role="read_only") as auth_headers:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/v1/appointments",
                json=_create_payload(),
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_ROLE"


# ── GET /api/v1/appointments ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_appointments_returns_all():
    app = _get_app()
    row1 = _make_appointment_row()
    row2 = _make_appointment_row(
        id=uuid.uuid4(),
        start_time=datetime(2026, 6, 15, 10, 0, tzinfo=UTC),
        end_time=datetime(2026, 6, 15, 10, 30, tzinfo=UTC),
    )

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.appointments.get_session_factory") as mock_sf,
    ):
        mock_session = _mock_session()

        mock_scalars_result = MagicMock()
        mock_scalars_result.all.return_value = [row1, row2]
        mock_session.scalars = AsyncMock(return_value=mock_scalars_result)
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/api/v1/appointments", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["patientName"] == "Jane Doe"
    assert body[0]["providerName"] == "Dr. Smith"
    assert body[0]["operatoryName"] == "Operatory 1"
    assert body[0]["appointmentTypeName"] == "Cleaning"


# ── GET /api/v1/appointments/{id} ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_appointment_returns_200():
    app = _get_app()
    appointment_row = _make_appointment_row()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.appointments.get_session_factory") as mock_sf,
    ):
        mock_session = _mock_session()
        mock_session.scalar = AsyncMock(return_value=appointment_row)
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/appointments/{_APPOINTMENT_ID}", headers=auth_headers
            )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(_APPOINTMENT_ID)
    assert body["status"] == "scheduled"
    assert body["patientName"] == "Jane Doe"
    assert body["providerName"] == "Dr. Smith"
    assert body["operatoryName"] == "Operatory 1"
    assert body["appointmentTypeName"] == "Cleaning"
    assert body["appointmentTypeColor"] == "#5B8DEF"


# ── PATCH /api/v1/appointments/{id} ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_appointment_status_transition_valid():
    """scheduled -> confirmed is a valid transition."""
    app = _get_app()
    existing_row = _make_appointment_row(status="scheduled")
    # After commit + re-fetch, the row comes back with updated status
    refetched_row = _make_appointment_row(status="confirmed")

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.appointments.get_session_factory") as mock_sf,
    ):
        mock_session = _mock_session()

        # scalar calls:
        #   1. Fetch existing appointment
        #   2. Re-fetch after commit (with selectinload)
        mock_session.scalar = AsyncMock(side_effect=[existing_row, refetched_row])
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.patch(
                f"/api/v1/appointments/{_APPOINTMENT_ID}",
                json={"status": "confirmed"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_update_appointment_invalid_transition_returns_422():
    """completed -> scheduled is not a valid transition."""
    app = _get_app()
    existing_row = _make_appointment_row(status="completed")

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.appointments.get_session_factory") as mock_sf,
    ):
        mock_session = _mock_session()
        mock_session.scalar = AsyncMock(return_value=existing_row)
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.patch(
                f"/api/v1/appointments/{_APPOINTMENT_ID}",
                json={"status": "scheduled"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "INVALID_STATUS_TRANSITION"


# ── DELETE /api/v1/appointments/{id} ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_appointment_returns_204():
    app = _get_app()
    existing_row = _make_appointment_row(status="scheduled")

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.appointments.get_session_factory") as mock_sf,
    ):
        mock_session = _mock_session()
        mock_session.scalar = AsyncMock(return_value=existing_row)
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.request(
                "DELETE",
                f"/api/v1/appointments/{_APPOINTMENT_ID}",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
                json={"cancellationReason": "Patient requested"},
            )

    assert response.status_code == 204
    assert existing_row.status == "cancelled"
    assert existing_row.cancellation_reason == "Patient requested"


@pytest.mark.asyncio
async def test_cancel_completed_appointment_returns_422():
    app = _get_app()
    existing_row = _make_appointment_row(status="completed")

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.appointments.get_session_factory") as mock_sf,
    ):
        mock_session = _mock_session()
        mock_session.scalar = AsyncMock(return_value=existing_row)
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.delete(
                f"/api/v1/appointments/{_APPOINTMENT_ID}",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "INVALID_STATUS_TRANSITION"
