import pytest


def _make_app_with_open_route():
    """Creates a minimal test app with a protected /test route."""
    import os

    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")

    from app.middleware.auth import CognitoAuthMiddleware
    from app.middleware.security import SecurityHeadersMiddleware
    from fastapi import FastAPI

    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CognitoAuthMiddleware)

    @app.get("/test")
    async def protected():
        return {"ok": True}

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
