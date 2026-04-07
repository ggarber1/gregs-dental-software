import uuid
from unittest.mock import AsyncMock, patch

import pytest

_FAKE_SUB = "cognito-sub-abc123"
_FAKE_EMAIL = "dentist@example.com"
_FAKE_PRACTICE_ID = uuid.uuid4()
_FAKE_USER_ID = uuid.uuid4()
_FAKE_JWT_CLAIMS = {"sub": _FAKE_SUB, "email": _FAKE_EMAIL, "cognito:groups": []}


def _make_app_with_open_route():
    """Creates a minimal test app with a protected /test route."""
    import os

    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")

    from fastapi import FastAPI
    from starlette.requests import Request

    from app.middleware.auth import CognitoAuthMiddleware
    from app.middleware.security import SecurityHeadersMiddleware

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CognitoAuthMiddleware)

    @app.get("/test")
    async def protected(request: Request):
        user = request.state.user
        return {
            "ok": True,
            "practice_id": str(user.practice_id) if user.practice_id else None,
            "role": user.role,
            "user_id": str(user.user_id) if user.user_id else None,
        }

    @app.get("/health")
    async def public():
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_missing_auth_header_returns_401():
    from httpx import ASGITransport, AsyncClient

    app = _make_app_with_open_route()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/test")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MISSING_TOKEN"


@pytest.mark.asyncio
async def test_public_path_skips_auth():
    from httpx import ASGITransport, AsyncClient

    app = _make_app_with_open_route()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/health")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_invalid_token_returns_401():
    from httpx import ASGITransport, AsyncClient

    app = _make_app_with_open_route()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/test", headers={"Authorization": "Bearer not.a.valid.token"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_malformed_auth_scheme_returns_401():
    from httpx import ASGITransport, AsyncClient

    app = _make_app_with_open_route()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/test", headers={"Authorization": "Basic dXNlcjpwYXNz"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "MISSING_TOKEN"


# ── X-Practice-ID tests ───────────────────────────────────────────────────────
# JWT verification is patched out for all tests below; we test only the
# practice-scoping logic that runs after a valid token is accepted.


@pytest.mark.asyncio
async def test_valid_jwt_without_practice_id_header_succeeds():
    """A request with no X-Practice-ID header is accepted; practice context is None."""
    from httpx import ASGITransport, AsyncClient

    app = _make_app_with_open_route()
    with (
        patch("jose.jwt.get_unverified_header", return_value={"kid": "fake-kid"}),
        patch("app.middleware.auth._get_public_key", new=AsyncMock(return_value=object())),
        patch("jose.jwt.decode", return_value=_FAKE_JWT_CLAIMS),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/test", headers={"Authorization": "Bearer fake.jwt.token"})

    assert response.status_code == 200
    body = response.json()
    assert body["practice_id"] is None
    assert body["role"] is None
    assert body["user_id"] is None


@pytest.mark.asyncio
async def test_malformed_practice_id_returns_400():
    """X-Practice-ID that is not a valid UUID returns 400."""
    from httpx import ASGITransport, AsyncClient

    app = _make_app_with_open_route()
    with (
        patch("jose.jwt.get_unverified_header", return_value={"kid": "fake-kid"}),
        patch("app.middleware.auth._get_public_key", new=AsyncMock(return_value=object())),
        patch("jose.jwt.decode", return_value=_FAKE_JWT_CLAIMS),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                "/test",
                headers={
                    "Authorization": "Bearer fake.jwt.token",
                    "X-Practice-ID": "not-a-uuid",
                },
            )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_PRACTICE_ID"


@pytest.mark.asyncio
async def test_active_practice_membership_sets_user_context():
    """Valid UUID + active membership → 200 with practice_id and role populated."""
    from httpx import ASGITransport, AsyncClient

    app = _make_app_with_open_route()
    with (
        patch("jose.jwt.get_unverified_header", return_value={"kid": "fake-kid"}),
        patch("app.middleware.auth._get_public_key", new=AsyncMock(return_value=object())),
        patch("jose.jwt.decode", return_value=_FAKE_JWT_CLAIMS),
        patch(
            "app.middleware.auth._resolve_practice_membership",
            new=AsyncMock(return_value=(_FAKE_USER_ID, "admin")),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                "/test",
                headers={
                    "Authorization": "Bearer fake.jwt.token",
                    "X-Practice-ID": str(_FAKE_PRACTICE_ID),
                },
            )

    assert response.status_code == 200
    body = response.json()
    assert body["practice_id"] == str(_FAKE_PRACTICE_ID)
    assert body["role"] == "admin"
    assert body["user_id"] == str(_FAKE_USER_ID)


@pytest.mark.asyncio
async def test_no_practice_membership_returns_403():
    """Valid UUID but user has no active practice_users row → 403."""
    from httpx import ASGITransport, AsyncClient

    app = _make_app_with_open_route()
    with (
        patch("jose.jwt.get_unverified_header", return_value={"kid": "fake-kid"}),
        patch("app.middleware.auth._get_public_key", new=AsyncMock(return_value=object())),
        patch("jose.jwt.decode", return_value=_FAKE_JWT_CLAIMS),
        patch(
            "app.middleware.auth._resolve_practice_membership",
            new=AsyncMock(return_value=None),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get(
                "/test",
                headers={
                    "Authorization": "Bearer fake.jwt.token",
                    "X-Practice-ID": str(_FAKE_PRACTICE_ID),
                },
            )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PRACTICE_ACCESS_DENIED"
