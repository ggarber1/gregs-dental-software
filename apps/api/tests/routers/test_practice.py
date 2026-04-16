"""
Unit tests for GET /api/v1/practice.

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


def _make_practice_row(**overrides: Any) -> MagicMock:
    defaults = {
        "id": _PRACTICE_ID,
        "name": "Sunrise Dental",
        "timezone": "America/New_York",
        "phone": "555-123-4567",
        "address_line1": "123 Main St",
        "address_line2": None,
        "city": "Boston",
        "state": "MA",
        "zip": "02101",
        "features": {},
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    row = MagicMock()
    for k, v in {**defaults, **overrides}.items():
        setattr(row, k, v)
    return row


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


# ── GET /api/v1/practice ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_practice_returns_200():
    app = _get_app()
    practice_row = _make_practice_row()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.practice.get_session_factory") as mock_sf,
    ):
        mock_session = _mock_session()
        mock_session.scalar = AsyncMock(return_value=practice_row)
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/api/v1/practice", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(_PRACTICE_ID)
    assert body["name"] == "Sunrise Dental"
    assert body["timezone"] == "America/New_York"
    assert body["phone"] == "555-123-4567"


@pytest.mark.asyncio
async def test_get_practice_no_scope_returns_403():
    app = _get_app()

    with _auth_patches(practice_id=None) as auth_headers:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/api/v1/practice", headers=auth_headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PRACTICE_SCOPE_REQUIRED"


@pytest.mark.asyncio
async def test_get_practice_not_found_returns_404():
    app = _get_app()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.practice.get_session_factory") as mock_sf,
    ):
        mock_session = _mock_session()
        mock_session.scalar = AsyncMock(return_value=None)
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/api/v1/practice", headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PRACTICE_NOT_FOUND"
