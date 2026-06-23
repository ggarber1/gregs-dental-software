from datetime import UTC, datetime

import httpx
import pytest

from app.services.era.base import ERAFetchError
from app.services.era.stedi import StediRemittanceClient


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_poll_filters_to_835_and_returns_ids():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "items": [
                {"transactionId": "t-835-a", "transactionSetIdentifier": "835"},
                {"transactionId": "t-277", "transactionSetIdentifier": "277"},
                {"transactionId": "t-835-b", "transactionSetIdentifier": "835"},
            ],
            "nextPageToken": None,
        })

    client = StediRemittanceClient(api_key="k", client=_client(handler))
    txns = await client.poll_transactions(datetime(2026, 6, 1, tzinfo=UTC))
    assert [t.transaction_id for t in txns] == ["t-835-a", "t-835-b"]


@pytest.mark.asyncio
async def test_poll_paginates_via_next_page_token():
    pages = {
        None: {
            "items": [{"transactionId": "a", "transactionSetIdentifier": "835"}],
            "nextPageToken": "p2",
        },
        "p2": {
            "items": [{"transactionId": "b", "transactionSetIdentifier": "835"}],
            "nextPageToken": None,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.params.get("pageToken")
        return httpx.Response(200, json=pages[token])

    client = StediRemittanceClient(api_key="k", client=_client(handler))
    txns = await client.poll_transactions(datetime(2026, 6, 1, tzinfo=UTC))
    assert [t.transaction_id for t in txns] == ["a", "b"]


@pytest.mark.asyncio
async def test_fetch_era_returns_json_and_sends_key_auth():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        captured["path"] = request.url.path
        return httpx.Response(200, json={"transactions": [{"payer": {"name": "X"}}]})

    client = StediRemittanceClient(api_key="secret", client=_client(handler))
    body = await client.fetch_era("txn-1")
    assert body["transactions"][0]["payer"]["name"] == "X"
    assert captured["auth"] == "Key secret"
    assert "txn-1" in captured["path"]


@pytest.mark.asyncio
async def test_fetch_era_server_error_raises_retryable():
    client = StediRemittanceClient(
        api_key="k", client=_client(lambda r: httpx.Response(503, json={}))
    )
    with pytest.raises(ERAFetchError) as exc:
        await client.fetch_era("txn-1")
    assert exc.value.retryable is True


@pytest.mark.asyncio
async def test_poll_4xx_raises_non_retryable():
    client = StediRemittanceClient(
        api_key="k", client=_client(lambda r: httpx.Response(400, json={}))
    )
    with pytest.raises(ERAFetchError) as exc:
        await client.poll_transactions(datetime(2026, 6, 1, tzinfo=UTC))
    assert exc.value.retryable is False
