"""Unit tests for GET/PUT /api/v1/settings/reminders."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

_PRACTICE_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_SUB = "cognito-sub-test"
_JWT_CLAIMS = {"sub": _SUB, "email": "admin@clinic.com", "cognito:groups": []}


def _get_app():
    import os

    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    os.environ.setdefault("APP_ENCRYPTION_KEY", "dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleXQ=")
    from app.main import create_app

    return create_app()


@contextmanager
def _auth_patches(practice_id: uuid.UUID | None = _PRACTICE_ID, role: str = "admin"):
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


def _make_practice_row(**overrides: Any) -> MagicMock:
    defaults = {
        "id": _PRACTICE_ID,
        "reminder_hours": [48, 24],
    }
    row = MagicMock()
    for k, v in {**defaults, **overrides}.items():
        setattr(row, k, v)
    return row


def _mock_session() -> AsyncMock:
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.commit = AsyncMock()
    return session


# ── GET /api/v1/settings/reminders ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_reminder_settings_returns_hours():
    app = _get_app()
    practice_row = _make_practice_row(reminder_hours=[48, 24])
    session = _mock_session()
    session.scalar = AsyncMock(return_value=practice_row)

    with _auth_patches() as headers:
        with patch("app.routers.settings.get_session_factory", return_value=lambda: session):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/api/v1/settings/reminders", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["reminderHours"] == [48, 24]


@pytest.mark.asyncio
async def test_get_reminder_settings_requires_practice_scope():
    app = _get_app()
    with _auth_patches(practice_id=None) as headers:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/settings/reminders", headers=headers)

    assert resp.status_code == 403


# ── PUT /api/v1/settings/reminders ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_reminder_settings_saves_sorted_hours():
    app = _get_app()
    practice_row = _make_practice_row()
    session = _mock_session()
    session.scalar = AsyncMock(return_value=practice_row)

    with _auth_patches(role="admin") as headers:
        with patch("app.routers.settings.get_session_factory", return_value=lambda: session):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.put(
                    "/api/v1/settings/reminders",
                    json={"reminderHours": [24, 72, 48]},
                    headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                )

    assert resp.status_code == 200
    # Response must be sorted descending and deduplicated
    assert resp.json()["reminderHours"] == [72, 48, 24]
    # The practice row was mutated
    assert practice_row.reminder_hours == [72, 48, 24]


@pytest.mark.asyncio
async def test_update_reminder_settings_deduplicates():
    app = _get_app()
    practice_row = _make_practice_row()
    session = _mock_session()
    session.scalar = AsyncMock(return_value=practice_row)

    with _auth_patches(role="admin") as headers:
        with patch("app.routers.settings.get_session_factory", return_value=lambda: session):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.put(
                    "/api/v1/settings/reminders",
                    json={"reminderHours": [24, 24, 48]},
                    headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
                )

    assert resp.status_code == 200
    assert resp.json()["reminderHours"] == [48, 24]


@pytest.mark.asyncio
async def test_update_reminder_settings_non_admin_rejected():
    app = _get_app()
    with _auth_patches(role="front_desk") as headers:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.put(
                "/api/v1/settings/reminders",
                json={"reminderHours": [24]},
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_reminder_settings_rejects_empty():
    app = _get_app()
    with _auth_patches(role="admin") as headers:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.put(
                "/api/v1/settings/reminders",
                json={"reminderHours": []},
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_reminder_settings_rejects_out_of_range():
    app = _get_app()
    with _auth_patches(role="admin") as headers:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.put(
                "/api/v1/settings/reminders",
                json={"reminderHours": [0]},
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_reminder_settings_rejects_too_many_windows():
    app = _get_app()
    with _auth_patches(role="admin") as headers:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.put(
                "/api/v1/settings/reminders",
                json={"reminderHours": [12, 24, 36, 48, 72, 96]},
                headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert resp.status_code == 422
