"""
Unit tests for GET/POST/PATCH/DELETE /api/v1/insurance-plans.

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
_PLAN_ID = uuid.uuid4()
_SUB = "cognito-sub-test"
_JWT_CLAIMS = {"sub": _SUB, "email": "staff@clinic.com", "cognito:groups": []}

_PLAN_ROW_DEFAULTS: dict[str, Any] = {
    "id": _PLAN_ID,
    "practice_id": _PRACTICE_ID,
    "carrier_name": "Delta Dental",
    "payer_id": "DLTADNTL",
    "group_number": None,
    "is_in_network": True,
    "deleted_at": None,
    "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
}


def _make_row(**overrides: Any) -> MagicMock:
    row = MagicMock()
    for k, v in {**_PLAN_ROW_DEFAULTS, **overrides}.items():
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


def _copy_attrs(target: Any, source: MagicMock) -> None:
    for key in _PLAN_ROW_DEFAULTS:
        if hasattr(target, key):
            setattr(target, key, getattr(source, key))


# ── POST /api/v1/insurance-plans ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_plan_returns_201():
    app = _get_app()
    mock_row = _make_row()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.insurance_plans.get_session_factory") as mock_sf,
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
                "/api/v1/insurance-plans",
                json={"carrierName": "Delta Dental", "payerId": "DLTADNTL"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 201
    body = response.json()
    assert body["carrierName"] == "Delta Dental"
    assert body["payerId"] == "DLTADNTL"
    assert body["isInNetwork"] is True


@pytest.mark.asyncio
async def test_create_plan_422_missing_carrier_name():
    app = _get_app()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.insurance_plans.get_session_factory"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/v1/insurance-plans",
                json={"payerId": "DLTADNTL"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_plan_403_without_practice_scope():
    app = _get_app()

    with (
        _auth_patches(practice_id=None) as auth_headers,
        patch("app.routers.insurance_plans.get_session_factory"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/v1/insurance-plans",
                json={"carrierName": "Delta Dental", "payerId": "DLTADNTL"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_plan_403_read_only_role():
    app = _get_app()

    with (
        _auth_patches(role="read_only") as auth_headers,
        patch("app.routers.insurance_plans.get_session_factory"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/v1/insurance-plans",
                json={"carrierName": "Delta Dental", "payerId": "DLTADNTL"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 403


# ── GET /api/v1/insurance-plans ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_plans_returns_list():
    app = _get_app()
    row1 = _make_row(carrier_name="Delta Dental")
    row2 = _make_row(id=uuid.uuid4(), carrier_name="Cigna", payer_id="CIGNA00")

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.insurance_plans.get_session_factory") as mock_sf,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [row1, row2]
        mock_session.scalars = AsyncMock(return_value=mock_scalars)
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/api/v1/insurance-plans", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["carrierName"] == "Delta Dental"
    assert body[1]["carrierName"] == "Cigna"


@pytest.mark.asyncio
async def test_list_plans_403_without_practice_scope():
    app = _get_app()

    with (
        _auth_patches(practice_id=None) as auth_headers,
        patch("app.routers.insurance_plans.get_session_factory"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/api/v1/insurance-plans", headers=auth_headers)

    assert response.status_code == 403


# ── PATCH /api/v1/insurance-plans/{plan_id} ──────────────────────────────────


@pytest.mark.asyncio
async def test_patch_plan_returns_200():
    app = _get_app()
    mock_row = _make_row(carrier_name="Cigna", payer_id="CIGNA00")

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.insurance_plans.get_session_factory") as mock_sf,
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
                f"/api/v1/insurance-plans/{_PLAN_ID}",
                json={"carrierName": "Cigna", "payerId": "CIGNA00"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["carrierName"] == "Cigna"
    assert body["payerId"] == "CIGNA00"


@pytest.mark.asyncio
async def test_patch_plan_404_unknown():
    app = _get_app()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.insurance_plans.get_session_factory") as mock_sf,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.scalar = AsyncMock(return_value=None)
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.patch(
                f"/api/v1/insurance-plans/{uuid.uuid4()}",
                json={"carrierName": "Cigna"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INSURANCE_PLAN_NOT_FOUND"


@pytest.mark.asyncio
async def test_patch_plan_403_read_only():
    app = _get_app()

    with (
        _auth_patches(role="read_only") as auth_headers,
        patch("app.routers.insurance_plans.get_session_factory"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.patch(
                f"/api/v1/insurance-plans/{_PLAN_ID}",
                json={"carrierName": "Cigna"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 403


# ── DELETE /api/v1/insurance-plans/{plan_id} ─────────────────────────────────


@pytest.mark.asyncio
async def test_delete_plan_returns_204():
    app = _get_app()
    mock_row = _make_row()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.insurance_plans.get_session_factory") as mock_sf,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.scalar = AsyncMock(return_value=mock_row)
        mock_session.commit = AsyncMock()
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.delete(
                f"/api/v1/insurance-plans/{_PLAN_ID}",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_plan_404_unknown():
    app = _get_app()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.insurance_plans.get_session_factory") as mock_sf,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.scalar = AsyncMock(return_value=None)
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.delete(
                f"/api/v1/insurance-plans/{uuid.uuid4()}",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INSURANCE_PLAN_NOT_FOUND"


@pytest.mark.asyncio
async def test_delete_plan_403_read_only():
    app = _get_app()

    with (
        _auth_patches(role="read_only") as auth_headers,
        patch("app.routers.insurance_plans.get_session_factory"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.delete(
                f"/api/v1/insurance-plans/{_PLAN_ID}",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 403
