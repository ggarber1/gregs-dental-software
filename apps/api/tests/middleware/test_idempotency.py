import json
from unittest.mock import AsyncMock, patch

import pytest


def _make_idempotency_app():
    import os

    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")

    from app.middleware.idempotency import IdempotencyMiddleware
    from fastapi import FastAPI

    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware)

    @app.post("/patients")
    async def create_patient():
        return {"id": "abc-123"}

    @app.get("/patients")
    async def list_patients():
        return []

    return app


@pytest.mark.asyncio
async def test_post_without_idempotency_key_returns_422():
    from httpx import ASGITransport, AsyncClient

    app = _make_idempotency_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.post("/patients", json={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MISSING_IDEMPOTENCY_KEY"


@pytest.mark.asyncio
async def test_get_does_not_require_idempotency_key():
    from httpx import ASGITransport, AsyncClient

    with patch("app.middleware.idempotency.get_redis") as mock_redis:
        mock_redis_client = AsyncMock()
        mock_redis.return_value = mock_redis_client

        app = _make_idempotency_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/patients")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_duplicate_key_returns_cached_response():
    from httpx import ASGITransport, AsyncClient

    cached_payload = json.dumps({"status_code": 200, "body": '{"id": "abc-123"}'})

    with patch("app.middleware.idempotency.get_redis") as mock_redis:
        mock_redis_client = AsyncMock()
        mock_redis_client.get = AsyncMock(return_value=cached_payload)
        mock_redis.return_value = mock_redis_client

        app = _make_idempotency_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/patients",
                json={},
                headers={"Idempotency-Key": "key-already-seen"},
            )

    assert response.status_code == 200
    assert response.headers.get("x-idempotent-replayed") == "true"


@pytest.mark.asyncio
async def test_new_key_stores_response_in_redis():
    from httpx import ASGITransport, AsyncClient

    with patch("app.middleware.idempotency.get_redis") as mock_redis:
        mock_redis_client = AsyncMock()
        mock_redis_client.get = AsyncMock(return_value=None)
        mock_redis_client.setex = AsyncMock()
        mock_redis.return_value = mock_redis_client

        app = _make_idempotency_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post(
                "/patients",
                json={},
                headers={"Idempotency-Key": "brand-new-key"},
            )

    assert response.status_code == 200
    mock_redis_client.setex.assert_called_once()
    call_args = mock_redis_client.setex.call_args
    assert "brand-new-key" in call_args[0][0]
