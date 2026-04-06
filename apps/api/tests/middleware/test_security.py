from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_security_headers_present(client):
    with (
        patch("app.middleware.auth.CognitoAuthMiddleware.dispatch", new_callable=AsyncMock) as mock_auth,
        patch("app.middleware.audit.AuditLogMiddleware.dispatch", new_callable=AsyncMock) as mock_audit,
        patch("app.middleware.idempotency.IdempotencyMiddleware.dispatch", new_callable=AsyncMock) as mock_idempotency,
    ):
        from starlette.responses import JSONResponse

        async def passthrough(request, call_next):
            return await call_next(request)

        mock_auth.side_effect = passthrough
        mock_audit.side_effect = passthrough
        mock_idempotency.side_effect = passthrough

        with (
            patch("app.main.get_session_factory") as mock_sf,
            patch("app.main.get_redis") as mock_redis,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_session.execute = AsyncMock()
            mock_sf.return_value.return_value = mock_session

            mock_redis_client = AsyncMock()
            mock_redis_client.ping = AsyncMock()
            mock_redis.return_value = mock_redis_client

            response = await client.get("/health")

    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "max-age=" in response.headers["strict-transport-security"]
    assert response.headers["cache-control"] == "no-store"
    assert "default-src" in response.headers["content-security-policy"]
