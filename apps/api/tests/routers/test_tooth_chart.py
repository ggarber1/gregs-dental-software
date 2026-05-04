"""
Unit tests for /api/v1/patients/{patient_id}/tooth-chart endpoints.

Auth and DB are fully mocked — no real Postgres, Cognito, or Redis needed.
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
_PRACTICE_B_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_PATIENT_ID = uuid.uuid4()
_CONDITION_ID = uuid.uuid4()
_PROVIDER_ID = uuid.uuid4()
_APPOINTMENT_ID = uuid.uuid4()
_SUB = "cognito-sub-test"
_JWT_CLAIMS = {"sub": _SUB, "email": "staff@clinic.com", "cognito:groups": []}

_TODAY = date(2026, 5, 4)
_NOW = datetime(2026, 5, 4, 12, 0, 0, tzinfo=UTC)

_CONDITION_ROW_DEFAULTS: dict[str, Any] = {
    "id": _CONDITION_ID,
    "practice_id": _PRACTICE_ID,
    "patient_id": _PATIENT_ID,
    "tooth_number": "14",
    "notation_system": "universal",
    "condition_type": "crown",
    "surface": None,
    "material": "zirconia",
    "notes": None,
    "status": "existing",
    "recorded_at": _TODAY,
    "recorded_by": _PROVIDER_ID,
    "appointment_id": None,
    "created_at": _NOW,
    "updated_at": _NOW,
    "last_accessed_by": None,
    "last_accessed_at": None,
    "deleted_at": None,
}

_PATIENT_ROW_DEFAULTS: dict[str, Any] = {
    "id": _PATIENT_ID,
    "practice_id": _PRACTICE_ID,
    "deleted_at": None,
}

_APPOINTMENT_ROW_DEFAULTS: dict[str, Any] = {
    "id": _APPOINTMENT_ID,
    "practice_id": _PRACTICE_ID,
    "patient_id": _PATIENT_ID,
}


def _make_condition_row(**overrides: Any) -> MagicMock:
    row = MagicMock()
    for k, v in {**_CONDITION_ROW_DEFAULTS, **overrides}.items():
        setattr(row, k, v)
    return row


def _make_patient_row(**overrides: Any) -> MagicMock:
    row = MagicMock()
    for k, v in {**_PATIENT_ROW_DEFAULTS, **overrides}.items():
        setattr(row, k, v)
    return row


def _make_appointment_row(**overrides: Any) -> MagicMock:
    row = MagicMock()
    for k, v in {**_APPOINTMENT_ROW_DEFAULTS, **overrides}.items():
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


def _make_session(
    scalar_returns: list | None = None,
    scalars_returns: list | None = None,
) -> AsyncMock:
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()

    if scalar_returns is not None:
        session.scalar = AsyncMock(side_effect=scalar_returns)

    if scalars_returns is not None:
        mock_scalars_result = MagicMock()
        mock_scalars_result.all.return_value = scalars_returns
        session.scalars = AsyncMock(return_value=mock_scalars_result)

    return session


# ── Auth tests ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_chart_unauthenticated_returns_401():
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get(f"/api/v1/patients/{_PATIENT_ID}/tooth-chart")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_add_condition_unauthenticated_returns_401():
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.post(
            f"/api/v1/patients/{_PATIENT_ID}/tooth-chart/conditions",
            json={
                "toothNumber": "14",
                "conditionType": "crown",
                "recordedAt": "2026-05-04",
                "recordedBy": str(_PROVIDER_ID),
            },
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_add_condition_read_only_role_returns_403():
    app = _get_app()
    session = _make_session()
    with (
        _auth_patches(role="read_only") as auth_headers,
        patch("app.routers.tooth_chart.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                f"/api/v1/patients/{_PATIENT_ID}/tooth-chart/conditions",
                json={
                    "toothNumber": "14",
                    "conditionType": "crown",
                    "recordedAt": "2026-05-04",
                    "recordedBy": str(_PROVIDER_ID),
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_no_practice_membership_returns_403():
    app = _get_app()
    session = _make_session()
    with (
        _auth_patches(practice_id=None) as auth_headers,
        patch("app.routers.tooth_chart.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/patients/{_PATIENT_ID}/tooth-chart",
                headers=auth_headers,
            )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_practice_b_sees_empty_chart_for_practice_a_patient():
    """Practice B user querying a Practice A patient sees empty conditions list."""
    app = _get_app()
    session = _make_session(scalars_returns=[])
    with (
        _auth_patches(practice_id=_PRACTICE_B_ID) as auth_headers,
        patch("app.routers.tooth_chart.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/patients/{_PATIENT_ID}/tooth-chart",
                headers=auth_headers,
            )
    assert response.status_code == 200
    assert response.json()["conditions"] == []


# ── GET chart ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_chart_returns_conditions():
    app = _get_app()
    condition = _make_condition_row()
    session = _make_session(scalars_returns=[condition])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.tooth_chart.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/patients/{_PATIENT_ID}/tooth-chart",
                headers=auth_headers,
            )
    assert response.status_code == 200
    data = response.json()
    assert len(data["conditions"]) == 1
    assert data["conditions"][0]["toothNumber"] == "14"
    assert data["conditions"][0]["conditionType"] == "crown"


@pytest.mark.asyncio
async def test_get_chart_empty_returns_empty_list():
    app = _get_app()
    session = _make_session(scalars_returns=[])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.tooth_chart.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/patients/{_PATIENT_ID}/tooth-chart",
                headers=auth_headers,
            )
    assert response.status_code == 200
    assert response.json()["conditions"] == []


@pytest.mark.asyncio
async def test_get_chart_as_of_date_passed_as_query_param():
    """as_of_date is forwarded to the query; the mock returns whatever scalars returns."""
    app = _get_app()
    # Simulate: as_of_date filters out the condition (returns empty)
    session = _make_session(scalars_returns=[])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.tooth_chart.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/patients/{_PATIENT_ID}/tooth-chart?as_of_date=2025-01-01",
                headers=auth_headers,
            )
    assert response.status_code == 200
    assert response.json()["conditions"] == []


# ── POST add condition ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_condition_returns_201():
    app = _get_app()
    patient = _make_patient_row()
    session = _make_session(scalar_returns=[patient])
    added_row = _make_condition_row()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.tooth_chart.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        with patch(
            "app.routers.tooth_chart.ToothConditionModel",
            return_value=added_row,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as c:
                response = await c.post(
                    f"/api/v1/patients/{_PATIENT_ID}/tooth-chart/conditions",
                    json={
                        "toothNumber": "14",
                        "conditionType": "crown",
                        "material": "zirconia",
                        "recordedAt": "2026-05-04",
                        "recordedBy": str(_PROVIDER_ID),
                    },
                    headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
                )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_add_condition_patient_not_found_returns_404():
    app = _get_app()
    session = _make_session(scalar_returns=[None])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.tooth_chart.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                f"/api/v1/patients/{_PATIENT_ID}/tooth-chart/conditions",
                json={
                    "toothNumber": "14",
                    "conditionType": "crown",
                    "recordedAt": "2026-05-04",
                    "recordedBy": str(_PROVIDER_ID),
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PATIENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_add_condition_wrong_patient_appointment_returns_400():
    """appointment_id belonging to a different patient is rejected with 400."""
    app = _get_app()
    patient = _make_patient_row()
    # Appointment returns None because it doesn't match the patient
    session = _make_session(scalar_returns=[patient, None])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.tooth_chart.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                f"/api/v1/patients/{_PATIENT_ID}/tooth-chart/conditions",
                json={
                    "toothNumber": "14",
                    "conditionType": "crown",
                    "recordedAt": "2026-05-04",
                    "recordedBy": str(_PROVIDER_ID),
                    "appointmentId": str(uuid.uuid4()),
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_APPOINTMENT"


# ── PATCH update condition ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_condition_returns_200():
    app = _get_app()
    condition = _make_condition_row()
    session = _make_session(scalar_returns=[condition])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.tooth_chart.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.patch(
                f"/api/v1/patients/{_PATIENT_ID}/tooth-chart/conditions/{_CONDITION_ID}",
                json={"status": "treatment_planned"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_condition_not_found_returns_404():
    app = _get_app()
    session = _make_session(scalar_returns=[None])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.tooth_chart.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.patch(
                f"/api/v1/patients/{_PATIENT_ID}/tooth-chart/conditions/{_CONDITION_ID}",
                json={"status": "treatment_planned"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONDITION_NOT_FOUND"


# ── DELETE condition ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_condition_returns_204():
    app = _get_app()
    condition = _make_condition_row()
    session = _make_session(scalar_returns=[condition])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.tooth_chart.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.delete(
                f"/api/v1/patients/{_PATIENT_ID}/tooth-chart/conditions/{_CONDITION_ID}",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_condition_not_found_returns_404():
    app = _get_app()
    session = _make_session(scalar_returns=[None])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.tooth_chart.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.delete(
                f"/api/v1/patients/{_PATIENT_ID}/tooth-chart/conditions/{_CONDITION_ID}",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONDITION_NOT_FOUND"


@pytest.mark.asyncio
async def test_delete_condition_read_only_role_returns_403():
    app = _get_app()
    session = _make_session()
    with (
        _auth_patches(role="read_only") as auth_headers,
        patch("app.routers.tooth_chart.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.delete(
                f"/api/v1/patients/{_PATIENT_ID}/tooth-chart/conditions/{_CONDITION_ID}",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 403
