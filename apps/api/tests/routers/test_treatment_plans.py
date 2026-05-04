"""
Unit tests for treatment plan endpoints.

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

# ── Constants ─────────────────────────────────────────────────────────────────

_PRACTICE_ID = uuid.uuid4()
_PRACTICE_B_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_PATIENT_ID = uuid.uuid4()
_PLAN_ID = uuid.uuid4()
_ITEM_ID = uuid.uuid4()
_SUB = "cognito-sub-test"
_JWT_CLAIMS = {"sub": _SUB, "email": "staff@clinic.com", "cognito:groups": []}

_TODAY = date(2026, 5, 4)
_NOW = datetime(2026, 5, 4, 12, 0, 0, tzinfo=UTC)

_PLAN_ROW_DEFAULTS: dict[str, Any] = {
    "id": _PLAN_ID,
    "practice_id": _PRACTICE_ID,
    "patient_id": _PATIENT_ID,
    "name": "Treatment Plan",
    "status": "proposed",
    "presented_at": None,
    "accepted_at": None,
    "completed_at": None,
    "notes": None,
    "created_by": _USER_ID,
    "created_at": _NOW,
    "updated_at": _NOW,
    "last_accessed_by": None,
    "last_accessed_at": None,
    "deleted_at": None,
}

_ITEM_ROW_DEFAULTS: dict[str, Any] = {
    "id": _ITEM_ID,
    "practice_id": _PRACTICE_ID,
    "treatment_plan_id": _PLAN_ID,
    "patient_id": _PATIENT_ID,
    "tooth_number": "14",
    "procedure_code": "D2391",
    "procedure_name": "Resin composite, 1 surface",
    "surface": "O",
    "fee_cents": 25000,
    "insurance_est_cents": 15000,
    "patient_est_cents": 10000,
    "status": "proposed",
    "priority": 1,
    "appointment_id": None,
    "completed_appointment_id": None,
    "notes": None,
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
    "deleted_at": None,
}


def _make_plan_row(**overrides: Any) -> MagicMock:
    row = MagicMock()
    for k, v in {**_PLAN_ROW_DEFAULTS, **overrides}.items():
        setattr(row, k, v)
    return row


def _make_item_row(**overrides: Any) -> MagicMock:
    row = MagicMock()
    for k, v in {**_ITEM_ROW_DEFAULTS, **overrides}.items():
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
    else:
        session.execute = AsyncMock()

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


_BASE = f"/api/v1/patients/{_PATIENT_ID}/treatment-plans"


# ── Auth tests ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_plans_unauthenticated_returns_401():
    app = _get_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get(_BASE)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_plan_read_only_role_returns_403():
    app = _get_app()
    session = _make_session()
    with (
        _auth_patches(role="read_only") as auth_headers,
        patch("app.routers.treatment_plans.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                _BASE,
                json={"name": "Phase 1"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_plan_no_practice_returns_403():
    app = _get_app()
    session = _make_session()
    with (
        _auth_patches(practice_id=None) as auth_headers,
        patch("app.routers.treatment_plans.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                _BASE,
                json={"name": "Phase 1"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_practice_b_sees_empty_plan_list_for_practice_a_patient():
    app = _get_app()
    session = _make_session(scalars_returns=[])
    with (
        _auth_patches(practice_id=_PRACTICE_B_ID) as auth_headers,
        patch("app.routers.treatment_plans.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(_BASE, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["items"] == []


# ── Plan status transitions ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_accept_proposed_plan_succeeds():
    app = _get_app()
    plan = _make_plan_row(status="proposed")
    session = _make_session(scalar_returns=[plan])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.treatment_plans.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.patch(
                f"{_BASE}/{_PLAN_ID}",
                json={"status": "accepted"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 200
    assert plan.status == "accepted"


@pytest.mark.asyncio
async def test_transition_proposed_to_in_progress_returns_409():
    app = _get_app()
    plan = _make_plan_row(status="proposed")
    session = _make_session(scalar_returns=[plan])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.treatment_plans.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.patch(
                f"{_BASE}/{_PLAN_ID}",
                json={"status": "in_progress"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


@pytest.mark.asyncio
async def test_transition_completed_plan_returns_409():
    app = _get_app()
    plan = _make_plan_row(status="completed")
    session = _make_session(scalar_returns=[plan])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.treatment_plans.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.patch(
                f"{_BASE}/{_PLAN_ID}",
                json={"status": "accepted"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_refuse_from_any_active_status_succeeds():
    """Refuse is valid from proposed, accepted, and in_progress."""
    for starting_status in ("proposed", "accepted", "in_progress"):
        app = _get_app()
        plan = _make_plan_row(status=starting_status)
        session = _make_session(scalar_returns=[plan])
        with (
            _auth_patches() as auth_headers,
            patch("app.routers.treatment_plans.get_session_factory") as mock_sf,
        ):
            mock_sf.return_value.return_value = session
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                response = await c.patch(
                    f"{_BASE}/{_PLAN_ID}",
                    json={"status": "refused"},
                    headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
                )
        assert response.status_code == 200, f"refused from {starting_status} should be 200"


# ── Item status transitions ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_accept_proposed_item_succeeds():
    app = _get_app()
    item = _make_item_row(status="proposed")
    plan = _make_plan_row(status="accepted")
    session = _make_session(scalar_returns=[item, plan])
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [item]
    session.scalars = AsyncMock(return_value=mock_scalars)
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.treatment_plans.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.patch(
                f"{_BASE}/{_PLAN_ID}/items/{_ITEM_ID}",
                json={"status": "accepted"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_transition_proposed_item_to_completed_returns_409():
    app = _get_app()
    item = _make_item_row(status="proposed")
    plan = _make_plan_row()
    session = _make_session(scalar_returns=[item, plan])
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [item]
    session.scalars = AsyncMock(return_value=mock_scalars)
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.treatment_plans.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.patch(
                f"{_BASE}/{_PLAN_ID}/items/{_ITEM_ID}",
                json={"status": "completed"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


# ── Auto-transition logic ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auto_transition_plan_to_completed_when_all_items_done():
    from app.routers.treatment_plans import _maybe_auto_transition_plan

    plan = _make_plan_row(status="in_progress")
    items = [
        _make_item_row(status="completed"),
        _make_item_row(status="completed"),
        _make_item_row(status="refused"),
    ]

    session = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = items
    session.scalars = AsyncMock(return_value=mock_scalars)

    await _maybe_auto_transition_plan(session, plan)

    assert plan.status == "completed"
    assert plan.completed_at is not None


@pytest.mark.asyncio
async def test_auto_transition_plan_to_in_progress_when_item_scheduled():
    from app.routers.treatment_plans import _maybe_auto_transition_plan

    plan = _make_plan_row(status="accepted")
    items = [
        _make_item_row(status="scheduled"),
        _make_item_row(status="proposed"),
    ]

    session = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = items
    session.scalars = AsyncMock(return_value=mock_scalars)

    await _maybe_auto_transition_plan(session, plan)

    assert plan.status == "in_progress"


@pytest.mark.asyncio
async def test_auto_transition_no_change_when_all_proposed():
    from app.routers.treatment_plans import _maybe_auto_transition_plan

    plan = _make_plan_row(status="accepted")
    items = [_make_item_row(status="proposed"), _make_item_row(status="proposed")]

    session = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = items
    session.scalars = AsyncMock(return_value=mock_scalars)

    await _maybe_auto_transition_plan(session, plan)

    assert plan.status == "accepted"


# ── 404 cases ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_item_to_nonexistent_plan_returns_404():
    app = _get_app()
    session = _make_session(scalar_returns=[None])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.treatment_plans.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                f"{_BASE}/{_PLAN_ID}/items",
                json={
                    "procedureCode": "D2391",
                    "procedureName": "Resin composite",
                    "feeCents": 25000,
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLAN_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_nonexistent_plan_returns_404():
    app = _get_app()
    plan = _make_plan_row()
    session = _make_session(scalar_returns=[None])
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = []
    session.scalars = AsyncMock(return_value=mock_scalars)
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.treatment_plans.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"{_BASE}/{_PLAN_ID}",
                headers=auth_headers,
            )
    assert response.status_code == 404


# ── List plans ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_plans_returns_paginated_response():
    app = _get_app()
    plan = _make_plan_row()
    session = _make_session(scalars_returns=[plan])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.treatment_plans.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(_BASE, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Treatment Plan"
    assert data["hasMore"] is False


@pytest.mark.asyncio
async def test_list_plans_empty_for_new_patient():
    app = _get_app()
    session = _make_session(scalars_returns=[])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.treatment_plans.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(_BASE, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["items"] == []


# ── Delete item ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_item_returns_204():
    app = _get_app()
    item = _make_item_row()
    session = _make_session(scalar_returns=[item])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.treatment_plans.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.delete(
                f"{_BASE}/{_PLAN_ID}/items/{_ITEM_ID}",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 204
    assert item.deleted_at is not None


@pytest.mark.asyncio
async def test_delete_nonexistent_item_returns_404():
    app = _get_app()
    session = _make_session(scalar_returns=[None])
    with (
        _auth_patches() as auth_headers,
        patch("app.routers.treatment_plans.get_session_factory") as mock_sf,
    ):
        mock_sf.return_value.return_value = session
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.delete(
                f"{_BASE}/{_PLAN_ID}/items/{_ITEM_ID}",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )
    assert response.status_code == 404
