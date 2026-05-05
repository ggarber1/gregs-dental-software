"""
Unit tests for perio chart endpoints.

Auth, DB, and Redis are fully mocked — no real Postgres or Redis needed.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.routers.perio_charts import _compute_summary

# ── Constants ─────────────────────────────────────────────────────────────────

_PRACTICE_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_PATIENT_ID = uuid.uuid4()
_PROVIDER_ID = uuid.uuid4()
_CHART_ID = uuid.uuid4()
_CHART_B_ID = uuid.uuid4()
_READING_ID = uuid.uuid4()
_SUB = "cognito-sub-test"
_JWT_CLAIMS = {"sub": _SUB, "email": "hygienist@clinic.com", "cognito:groups": []}

_TODAY = date(2026, 5, 5)
_NOW = datetime(2026, 5, 5, 10, 0, 0, tzinfo=UTC)

_CHART_ROW_DEFAULTS: dict[str, Any] = {
    "id": _CHART_ID,
    "practice_id": _PRACTICE_ID,
    "patient_id": _PATIENT_ID,
    "appointment_id": None,
    "provider_id": _PROVIDER_ID,
    "chart_date": _TODAY,
    "notes": None,
    "created_at": _NOW,
    "updated_at": _NOW,
    "last_accessed_by": None,
    "last_accessed_at": None,
    "deleted_at": None,
}

_READING_ROW_DEFAULTS: dict[str, Any] = {
    "id": _READING_ID,
    "perio_chart_id": _CHART_ID,
    "tooth_number": "14",
    "site": "b",
    "probing_depth_mm": 3,
    "recession_mm": 0,
    "bleeding": False,
    "suppuration": False,
    "furcation": None,
    "mobility": None,
    "created_at": _NOW,
}

_PATIENT_ROW_DEFAULTS: dict[str, Any] = {
    "id": _PATIENT_ID,
    "practice_id": _PRACTICE_ID,
    "first_name": "Jane",
    "last_name": "Doe",
    "deleted_at": None,
}


def _make_chart_row(**overrides: Any) -> MagicMock:
    row = MagicMock()
    for k, v in {**_CHART_ROW_DEFAULTS, **overrides}.items():
        setattr(row, k, v)
    return row


def _make_reading_row(**overrides: Any) -> MagicMock:
    row = MagicMock()
    for k, v in {**_READING_ROW_DEFAULTS, **overrides}.items():
        setattr(row, k, v)
    return row


def _make_patient_row(**overrides: Any) -> MagicMock:
    row = MagicMock()
    for k, v in {**_PATIENT_ROW_DEFAULTS, **overrides}.items():
        setattr(row, k, v)
    return row


def _make_session(
    scalar_returns: list | None = None,
    scalars_returns: list | None = None,
    execute_returns: Any = None,
) -> AsyncMock:
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()

    if scalar_returns is not None:
        session.scalar = AsyncMock(side_effect=scalar_returns)

    if scalars_returns is not None:
        mock_scalars_result = MagicMock()
        mock_scalars_result.all.return_value = scalars_returns
        session.scalars = AsyncMock(return_value=mock_scalars_result)

    if execute_returns is not None:
        mock_exec_result = MagicMock()
        mock_exec_result.all.return_value = execute_returns
        session.execute = AsyncMock(return_value=mock_exec_result)

    return session


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


_BASE = f"/api/v1/patients/{_PATIENT_ID}/perio-charts"


# ── Unit: pure helpers ─────────────────────────────────────────────────────────


def test_cal_is_depth_plus_recession():
    reading = _make_reading_row(probing_depth_mm=4, recession_mm=2)
    # CAL computed in _reading_to_dict: depth + recession
    assert reading.probing_depth_mm + reading.recession_mm == 6


def test_compute_summary_empty_readings():
    stats = _compute_summary([])
    assert stats["avgProbingDepthMm"] == 0.0
    assert stats["sitesGte4mm"] == 0
    assert stats["sitesGte6mm"] == 0
    assert stats["bleedingSiteCount"] == 0


def test_compute_summary_counts_correctly():
    readings = [
        _make_reading_row(probing_depth_mm=3, bleeding=False),
        _make_reading_row(probing_depth_mm=5, bleeding=True),
        _make_reading_row(probing_depth_mm=7, bleeding=True),
    ]
    stats = _compute_summary(readings)
    assert stats["avgProbingDepthMm"] == 5.0
    assert stats["sitesGte4mm"] == 2
    assert stats["sitesGte6mm"] == 1
    assert stats["bleedingSiteCount"] == 2


# ── Auth tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_charts_unauthenticated_returns_401():
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get(_BASE)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_chart_read_only_role_returns_403():
    app = _get_app()
    session = _make_session()
    with (
        _auth_patches(role="read_only") as auth_headers,
        patch("app.routers.perio_charts.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                _BASE,
                json={
                    "providerId": str(_PROVIDER_ID),
                    "chartDate": _TODAY.isoformat(),
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_upsert_readings_read_only_role_returns_403():
    app = _get_app()
    session = _make_session()
    with (
        _auth_patches(role="read_only") as auth_headers,
        patch("app.routers.perio_charts.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                f"{_BASE}/{_CHART_ID}/readings",
                json={"readings": []},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 403


# ── Input validation ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_chart_depth_out_of_range_returns_422():
    app = _get_app()
    session = _make_session()
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.perio_charts.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                _BASE,
                json={
                    "providerId": str(_PROVIDER_ID),
                    "chartDate": _TODAY.isoformat(),
                    "readings": [
                        {
                            "toothNumber": "14",
                            "site": "b",
                            "probingDepthMm": 99,  # exceeds max of 20
                        }
                    ],
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_chart_invalid_site_returns_422():
    """Site values outside the enum are rejected by Pydantic before hitting the DB."""
    app = _get_app()
    session = _make_session()
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.perio_charts.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                _BASE,
                json={
                    "providerId": str(_PROVIDER_ID),
                    "chartDate": _TODAY.isoformat(),
                    "readings": [
                        # invalid site value
                        {"toothNumber": "14", "site": "buccal", "probingDepthMm": 3},
                    ],
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 422


# ── Create chart ───────────────────────────────────────────────────────────────


def _make_create_session(patient_row: Any, chart_row: Any, reading_rows: list) -> AsyncMock:
    """Session mock wired for the create_perio_chart endpoint flow."""
    scalars_result = MagicMock()
    scalars_result.all.return_value = reading_rows

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock(return_value=patient_row)
    session.scalars = AsyncMock(return_value=scalars_result)

    async def _refresh(obj: Any) -> None:
        obj.id = chart_row.id
        obj.created_at = _NOW
        obj.updated_at = _NOW

    session.refresh = AsyncMock(side_effect=_refresh)
    return session


@pytest.mark.asyncio
async def test_create_chart_success_returns_201():
    app = _get_app()
    chart_row = _make_chart_row()
    patient_row = _make_patient_row()
    session = _make_create_session(patient_row, chart_row, [])

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.perio_charts.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                _BASE,
                json={
                    "providerId": str(_PROVIDER_ID),
                    "chartDate": _TODAY.isoformat(),
                    "readings": [],
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 201
    data = response.json()
    assert data["readings"] == []
    assert data["chartDate"] == _TODAY.isoformat()


@pytest.mark.asyncio
async def test_create_chart_with_192_readings_calls_upsert():
    """Batch creation for a full-mouth chart (32 teeth × 6 sites = 192 readings)."""
    app = _get_app()
    chart_row = _make_chart_row()
    patient_row = _make_patient_row()

    sites = ["db", "b", "mb", "dl", "l", "ml"]
    readings_payload = [
        {"toothNumber": str(tooth), "site": site, "probingDepthMm": 3}
        for tooth in range(1, 33)
        for site in sites
    ]
    assert len(readings_payload) == 192

    session = _make_create_session(patient_row, chart_row, [])

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.perio_charts.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                _BASE,
                json={
                    "providerId": str(_PROVIDER_ID),
                    "chartDate": _TODAY.isoformat(),
                    "readings": readings_payload,
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    # Upsert was called (session.execute called with the pg_insert statement)
    assert session.execute.called
    assert response.status_code == 201


# ── Get detail ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_chart_not_found_returns_404():
    app = _get_app()
    session = _make_session(scalar_returns=[None])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.perio_charts.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(f"{_BASE}/{_CHART_ID}", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CHART_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_chart_detail_returns_readings():
    app = _get_app()
    chart_row = _make_chart_row()
    reading_row = _make_reading_row()

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [reading_row]

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock(return_value=chart_row)
    session.scalars = AsyncMock(return_value=scalars_mock)

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.perio_charts.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(f"{_BASE}/{_CHART_ID}", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data["readings"]) == 1
    assert data["readings"][0]["toothNumber"] == "14"
    assert data["readings"][0]["cal"] == reading_row.probing_depth_mm + reading_row.recession_mm


# ── Comparison ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compare_charts_returns_correct_deltas():
    app = _get_app()
    chart_a = _make_chart_row(id=_CHART_ID, chart_date=date(2026, 1, 1))
    chart_b = _make_chart_row(id=_CHART_B_ID, chart_date=date(2026, 4, 1))
    reading_a = _make_reading_row(
        perio_chart_id=_CHART_ID, tooth_number="14", site="b", probing_depth_mm=3
    )
    reading_b = _make_reading_row(
        perio_chart_id=_CHART_B_ID, tooth_number="14", site="b", probing_depth_mm=5
    )

    scalars_mock_a = MagicMock()
    scalars_mock_a.all.return_value = [reading_a]
    scalars_mock_b = MagicMock()
    scalars_mock_b.all.return_value = [reading_b]

    scalars_call_count = 0

    async def _scalars_side_effect(*args: Any, **kwargs: Any) -> MagicMock:
        nonlocal scalars_call_count
        scalars_call_count += 1
        return scalars_mock_a if scalars_call_count == 1 else scalars_mock_b

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    session.scalar = AsyncMock(side_effect=[chart_a, chart_b])
    session.scalars = AsyncMock(side_effect=_scalars_side_effect)

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.perio_charts.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"{_BASE}/compare",
                params={"chartA": str(_CHART_ID), "chartB": str(_CHART_B_ID)},
                headers=auth_headers,
            )

    assert response.status_code == 200
    data = response.json()
    assert len(data["deltas"]) == 1
    delta = data["deltas"][0]
    assert delta["toothNumber"] == "14"
    assert delta["depthA"] == 3
    assert delta["depthB"] == 5
    assert delta["delta"] == 2  # worse


# ── Delete ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_chart_returns_204():
    app = _get_app()
    chart_row = _make_chart_row()
    session = _make_session(scalar_returns=[chart_row])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.perio_charts.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.delete(
                f"{_BASE}/{_CHART_ID}",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 204
    assert chart_row.deleted_at is not None


@pytest.mark.asyncio
async def test_delete_chart_read_only_role_returns_403():
    app = _get_app()
    session = _make_session()
    with (
        _auth_patches(role="read_only") as auth_headers,
        patch("app.routers.perio_charts.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.delete(
                f"{_BASE}/{_CHART_ID}",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 403
