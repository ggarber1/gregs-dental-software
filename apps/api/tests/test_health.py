from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_health_returns_200(client):
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

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["redis"] == "ok"


@pytest.mark.asyncio
async def test_health_db_error_still_returns_200(client):
    with (
        patch("app.main.get_session_factory") as mock_sf,
        patch("app.main.get_redis") as mock_redis,
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(side_effect=Exception("connection refused"))
        mock_sf.return_value.return_value = mock_session

        mock_redis_client = AsyncMock()
        mock_redis_client.ping = AsyncMock()
        mock_redis.return_value = mock_redis_client

        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["db"] == "error"
    assert body["redis"] == "ok"
