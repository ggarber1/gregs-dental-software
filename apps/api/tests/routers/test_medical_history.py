"""
Unit tests for /api/v1/patients/{patient_id}/medical-history endpoints.

Auth and DB are fully mocked — no real Postgres, Cognito, or Redis needed.
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
_VERSION_ID = uuid.uuid4()
_SUB = "cognito-sub-test"
_JWT_CLAIMS = {"sub": _SUB, "email": "staff@clinic.com", "cognito:groups": []}

_NOW = datetime(2026, 5, 2, 12, 0, 0, tzinfo=UTC)

_VERSION_ROW_DEFAULTS: dict[str, Any] = {
    "id": _VERSION_ID,
    "practice_id": _PRACTICE_ID,
    "patient_id": _PATIENT_ID,
    "version_number": 1,
    "recorded_by": _USER_ID,
    "recorded_at": _NOW,
    "allergies": [{"name": "penicillin", "severity": "severe"}],
    "medications": [{"name": "metformin", "dose": "500mg"}],
    "conditions": [{"name": "diabetes"}],
    "flag_blood_thinners": False,
    "flag_bisphosphonates": False,
    "flag_heart_condition": False,
    "flag_diabetes": True,
    "flag_pacemaker": False,
    "flag_latex_allergy": False,
    "additional_notes": None,
    "created_at": _NOW,
    "updated_at": _NOW,
    "last_accessed_by": None,
    "last_accessed_at": None,
    "deleted_at": None,
}

_PATIENT_ROW_DEFAULTS: dict[str, Any] = {
    "id": _PATIENT_ID,
    "practice_id": _PRACTICE_ID,
    "first_name": "Jane",
    "last_name": "Doe",
    "allergies": [],
    "medical_alerts": [],
    "medications": [],
    "deleted_at": None,
    "updated_at": _NOW,
}


def _make_version_row(**overrides: Any) -> MagicMock:
    row = MagicMock()
    for k, v in {**_VERSION_ROW_DEFAULTS, **overrides}.items():
        setattr(row, k, v)
    return row


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
async def test_get_latest_unauthenticated_returns_401():
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get(f"/api/v1/patients/{_PATIENT_ID}/medical-history")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_post_unauthenticated_returns_401():
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.post(
            f"/api/v1/patients/{_PATIENT_ID}/medical-history",
            json={"allergies": [], "medications": [], "conditions": []},
            # Idempotency-Key is required on mutations; without auth the middleware
            # returns 401. Include the key so the idempotency check passes first.
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_post_read_only_role_returns_403():
    app = _get_app()
    session = _make_session()
    with (
        _auth_patches(role="read_only") as auth_headers,
        patch("app.routers.medical_history.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                f"/api/v1/patients/{_PATIENT_ID}/medical-history",
                json={"allergies": [], "medications": [], "conditions": []},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 403


# ── GET latest ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_latest_no_versions_returns_404():
    app = _get_app()
    session = _make_session(scalar_returns=[None])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.medical_history.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/patients/{_PATIENT_ID}/medical-history",
                headers=auth_headers,
            )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MEDICAL_HISTORY_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_latest_returns_highest_version():
    app = _get_app()
    version_row = _make_version_row(version_number=3)
    session = _make_session(scalar_returns=[version_row])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.medical_history.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/patients/{_PATIENT_ID}/medical-history",
                headers=auth_headers,
            )
    assert response.status_code == 200
    body = response.json()
    assert body["versionNumber"] == 3
    assert body["patientId"] == str(_PATIENT_ID)
    assert body["flags"]["flagDiabetes"] is True


# ── GET history ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_history_returns_versions_descending():
    app = _get_app()
    v2 = _make_version_row(version_number=2, id=uuid.uuid4())
    v1 = _make_version_row(version_number=1)
    session = _make_session(scalar_returns=[2], scalars_returns=[v2, v1])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.medical_history.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/patients/{_PATIENT_ID}/medical-history/history",
                headers=auth_headers,
            )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["items"][0]["versionNumber"] == 2
    assert body["items"][1]["versionNumber"] == 1


@pytest.mark.asyncio
async def test_get_history_respects_pagination():
    app = _get_app()
    session = _make_session(scalar_returns=[10], scalars_returns=[])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.medical_history.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/patients/{_PATIENT_ID}/medical-history/history?page=2&page_size=5",
                headers=auth_headers,
            )
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 2
    assert body["pageSize"] == 5
    assert body["total"] == 10


# ── GET specific version ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_specific_version_wrong_patient_returns_404():
    app = _get_app()
    session = _make_session(scalar_returns=[None])
    wrong_patient_id = uuid.uuid4()
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.medical_history.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/patients/{wrong_patient_id}/medical-history/{_VERSION_ID}",
                headers=auth_headers,
            )
    assert response.status_code == 404


# ── POST ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_post_creates_first_version():
    app = _get_app()
    patient_row = _make_patient_row()

    def _side_effect_add(row: Any) -> None:
        for k, v in _VERSION_ROW_DEFAULTS.items():
            if hasattr(row, k):
                setattr(row, k, v)

    session = _make_session(scalar_returns=[patient_row, None])
    session.add = MagicMock(side_effect=_side_effect_add)
    session.refresh = AsyncMock(side_effect=lambda row: None)

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.medical_history.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                f"/api/v1/patients/{_PATIENT_ID}/medical-history",
                json={
                    "allergies": [{"name": "penicillin", "severity": "severe"}],
                    "medications": [{"name": "metformin", "dose": "500mg"}],
                    "conditions": [{"name": "diabetes"}],
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 201
    body = response.json()
    assert body["versionNumber"] == 1


@pytest.mark.asyncio
async def test_post_increments_version_number():
    app = _get_app()
    patient_row = _make_patient_row()

    def _side_effect_add(row: Any) -> None:
        v2_defaults = {**_VERSION_ROW_DEFAULTS, "version_number": 2}
        for k, v in v2_defaults.items():
            if hasattr(row, k):
                setattr(row, k, v)

    session = _make_session(scalar_returns=[patient_row, 1])
    session.add = MagicMock(side_effect=_side_effect_add)
    session.refresh = AsyncMock()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.medical_history.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                f"/api/v1/patients/{_PATIENT_ID}/medical-history",
                json={"allergies": [], "medications": [], "conditions": []},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 201
    assert response.json()["versionNumber"] == 2


@pytest.mark.asyncio
async def test_post_updates_patient_flat_arrays():
    app = _get_app()
    patient_row = _make_patient_row()

    session = _make_session(scalar_returns=[patient_row, None])

    def _track_patient(row: Any) -> None:
        for k, v in _VERSION_ROW_DEFAULTS.items():
            if hasattr(row, k):
                setattr(row, k, v)

    session.add = MagicMock(side_effect=_track_patient)
    session.refresh = AsyncMock()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.medical_history.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                f"/api/v1/patients/{_PATIENT_ID}/medical-history",
                json={
                    "allergies": [{"name": "penicillin"}],
                    "medications": [{"name": "metformin"}],
                    "conditions": [{"name": "diabetes"}],
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 201
    # Patient flat array writes are set on the patient_row mock
    assert patient_row.allergies == ["penicillin"]
    assert patient_row.medications == ["metformin"]
    assert patient_row.medical_alerts == ["diabetes"]


@pytest.mark.asyncio
async def test_post_patient_not_found_returns_404():
    app = _get_app()
    session = _make_session(scalar_returns=[None])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.medical_history.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                f"/api/v1/patients/{_PATIENT_ID}/medical-history",
                json={"allergies": [], "medications": [], "conditions": []},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PATIENT_NOT_FOUND"


# ── Flag inference ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_warfarin_condition_sets_blood_thinner_flag():
    app = _get_app()
    patient_row = _make_patient_row()
    captured_flags: dict = {}

    def _capture_add(row: Any) -> None:
        if hasattr(row, "flag_blood_thinners"):
            captured_flags["flag_blood_thinners"] = row.flag_blood_thinners
        for k, v in _VERSION_ROW_DEFAULTS.items():
            if hasattr(row, k):
                setattr(row, k, v)

    session = _make_session(scalar_returns=[patient_row, None])
    session.add = MagicMock(side_effect=_capture_add)
    session.refresh = AsyncMock()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.medical_history.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post(
                f"/api/v1/patients/{_PATIENT_ID}/medical-history",
                json={
                    "conditions": [{"name": "Taking warfarin daily"}],
                    "allergies": [],
                    "medications": [],
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert captured_flags.get("flag_blood_thinners") is True


@pytest.mark.asyncio
async def test_latex_in_allergies_sets_latex_flag():
    app = _get_app()
    patient_row = _make_patient_row()
    captured_flags: dict = {}

    def _capture_add(row: Any) -> None:
        if hasattr(row, "flag_latex_allergy"):
            captured_flags["flag_latex_allergy"] = row.flag_latex_allergy
        for k, v in _VERSION_ROW_DEFAULTS.items():
            if hasattr(row, k):
                setattr(row, k, v)

    session = _make_session(scalar_returns=[patient_row, None])
    session.add = MagicMock(side_effect=_capture_add)
    session.refresh = AsyncMock()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.medical_history.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post(
                f"/api/v1/patients/{_PATIENT_ID}/medical-history",
                json={"allergies": [{"name": "latex gloves"}], "conditions": [], "medications": []},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert captured_flags.get("flag_latex_allergy") is True


@pytest.mark.asyncio
async def test_client_flag_override_sets_pacemaker_flag():
    app = _get_app()
    patient_row = _make_patient_row()
    captured_flags: dict = {}

    def _capture_add(row: Any) -> None:
        if hasattr(row, "flag_pacemaker"):
            captured_flags["flag_pacemaker"] = row.flag_pacemaker
        for k, v in _VERSION_ROW_DEFAULTS.items():
            if hasattr(row, k):
                setattr(row, k, v)

    session = _make_session(scalar_returns=[patient_row, None])
    session.add = MagicMock(side_effect=_capture_add)
    session.refresh = AsyncMock()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.medical_history.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            await c.post(
                f"/api/v1/patients/{_PATIENT_ID}/medical-history",
                json={
                    "allergies": [],
                    "medications": [],
                    "conditions": [],
                    "flags": {"flagPacemaker": True},
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert captured_flags.get("flag_pacemaker") is True
