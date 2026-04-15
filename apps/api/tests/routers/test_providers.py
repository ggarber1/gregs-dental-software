"""
Unit tests for GET/POST/PATCH/DELETE /api/v1/providers.

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

# -- Constants ----------------------------------------------------------------

_PRACTICE_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_PROVIDER_ID = uuid.uuid4()
_SUB = "cognito-sub-test"
_JWT_CLAIMS = {"sub": _SUB, "email": "staff@clinic.com", "cognito:groups": []}

_PROVIDER_ROW_DEFAULTS: dict[str, Any] = {
    "id": _PROVIDER_ID,
    "practice_id": _PRACTICE_ID,
    "full_name": "Dr. Smith",
    "npi": "1234567890",
    "provider_type": "dentist",
    "license_number": "DDS-12345",
    "specialty": "General",
    "color": "#4F86C6",
    "is_active": True,
    "display_order": 0,
    "deleted_at": None,
    "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
}


def _make_row(**overrides: Any) -> MagicMock:
    row = MagicMock()
    for k, v in {**_PROVIDER_ROW_DEFAULTS, **overrides}.items():
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

    Yields (auth_headers) -- the headers to include in each request.
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
    """Copy mock row attributes onto a real model instance after session.add()."""
    for key in _PROVIDER_ROW_DEFAULTS:
        if hasattr(target, key):
            setattr(target, key, getattr(source, key))


# -- POST /api/v1/providers ---------------------------------------------------


@pytest.mark.asyncio
async def test_create_provider_returns_201():
    app = _get_app()
    mock_row = _make_row()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.providers.get_session_factory") as mock_sf,
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
                "/api/v1/providers",
                json={
                    "fullName": "Dr. Smith",
                    "npi": "1234567890",
                    "providerType": "dentist",
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 201
    body = response.json()
    assert body["fullName"] == "Dr. Smith"
    assert body["npi"] == "1234567890"
    assert body["providerType"] == "dentist"


# -- GET /api/v1/providers ----------------------------------------------------


@pytest.mark.asyncio
async def test_list_providers_returns_list():
    app = _get_app()
    row1 = _make_row(full_name="Dr. Smith")
    row2 = _make_row(id=uuid.uuid4(), full_name="Dr. Jones")

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.providers.get_session_factory") as mock_sf,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [row1, row2]
        mock_session.scalars = AsyncMock(return_value=mock_scalars)
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/api/v1/providers", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert body[0]["fullName"] == "Dr. Smith"
    assert body[1]["fullName"] == "Dr. Jones"


# -- GET /api/v1/providers/{id} -----------------------------------------------


@pytest.mark.asyncio
async def test_get_provider_returns_200():
    app = _get_app()
    mock_row = _make_row()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.providers.get_session_factory") as mock_sf,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.scalar = AsyncMock(return_value=mock_row)
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                f"/api/v1/providers/{_PROVIDER_ID}",
                headers=auth_headers,
            )

    assert response.status_code == 200
    body = response.json()
    assert body["fullName"] == "Dr. Smith"
    assert body["npi"] == "1234567890"


# -- PATCH /api/v1/providers/{id} ---------------------------------------------


@pytest.mark.asyncio
async def test_update_provider_returns_200():
    app = _get_app()
    mock_row = _make_row(full_name="Dr. Johnson", specialty="Orthodontics")

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.providers.get_session_factory") as mock_sf,
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
                f"/api/v1/providers/{_PROVIDER_ID}",
                json={"fullName": "Dr. Johnson", "specialty": "Orthodontics"},
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["fullName"] == "Dr. Johnson"
    assert body["specialty"] == "Orthodontics"


# -- DELETE /api/v1/providers/{id} --------------------------------------------


@pytest.mark.asyncio
async def test_delete_provider_returns_204():
    app = _get_app()
    mock_row = _make_row()

    with (
        _auth_patches() as auth_headers,
        patch("app.routers.providers.get_session_factory") as mock_sf,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.scalar = AsyncMock(return_value=mock_row)
        mock_session.commit = AsyncMock()
        mock_sf.return_value.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.delete(
                f"/api/v1/providers/{_PROVIDER_ID}",
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 204


# -- Auth guard tests ---------------------------------------------------------


@pytest.mark.asyncio
async def test_create_provider_no_practice_scope_returns_403():
    app = _get_app()

    with _auth_patches(practice_id=None) as auth_headers:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/api/v1/providers",
                json={
                    "fullName": "Dr. Smith",
                    "npi": "1234567890",
                    "providerType": "dentist",
                },
                headers={**auth_headers, "Idempotency-Key": str(uuid.uuid4())},
            )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PRACTICE_SCOPE_REQUIRED"
