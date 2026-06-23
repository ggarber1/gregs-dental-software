from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from app.services.era.base import ERAFetchError, RemittanceClient, Transaction

logger = logging.getLogger(__name__)

# Confirm host/version against Stedi docs + the Staging Checkpoint 5 smoke run.
# Unit tests mock httpx and do not depend on these.
_POLL_URL = "https://core.us.stedi.com/2023-08-01/pollingTransactions"
_ERA_REPORT_URL = (
    "https://healthcare.us.stedi.com/2024-04-01/change/medicalnetwork/reports/v2/{txn}/835"
)
_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=15.0, pool=5.0)


def _is_835(item: dict[str, Any]) -> bool:
    for key in ("transactionSetIdentifier", "x12TransactionSetCode", "transactionType"):
        if str(item.get(key) or "") == "835":
            return True
    return False


def _transaction_id(item: dict[str, Any]) -> str | None:
    return item.get("transactionId") or item.get("id")


class StediRemittanceClient(RemittanceClient):
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._client = client  # injected in tests; created per-call in prod

    async def poll_transactions(self, since: datetime) -> list[Transaction]:
        headers = {"Authorization": f"Key {self._api_key}"}
        client = self._client or httpx.AsyncClient(timeout=_TIMEOUT)
        owns_client = self._client is None
        out: list[Transaction] = []
        page_token: str | None = None
        try:
            while True:
                params: dict[str, Any] = {"startDateTime": since.isoformat()}
                if page_token:
                    params["pageToken"] = page_token
                try:
                    resp = await client.get(_POLL_URL, params=params, headers=headers)
                except httpx.HTTPError as exc:
                    raise ERAFetchError(f"Stedi poll transport error: {exc}", retryable=True) from exc
                if resp.status_code >= 500:
                    raise ERAFetchError(f"Stedi poll server error {resp.status_code}", retryable=True)
                if resp.status_code >= 400:
                    raise ERAFetchError(
                        f"Stedi poll rejected {resp.status_code}: {resp.text[:200]}", retryable=False
                    )
                body = resp.json()
                for item in body.get("items") or []:
                    txn_id = _transaction_id(item)
                    if txn_id and _is_835(item):
                        out.append(Transaction(transaction_id=str(txn_id)))
                page_token = body.get("nextPageToken")
                if not page_token:
                    break
        finally:
            if owns_client:
                await client.aclose()
        return out

    async def fetch_era(self, transaction_id: str) -> dict[str, Any]:
        headers = {"Authorization": f"Key {self._api_key}"}
        url = _ERA_REPORT_URL.format(txn=transaction_id)
        client = self._client or httpx.AsyncClient(timeout=_TIMEOUT)
        owns_client = self._client is None
        try:
            try:
                resp = await client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                raise ERAFetchError(f"Stedi ERA transport error: {exc}", retryable=True) from exc
        finally:
            if owns_client:
                await client.aclose()
        if resp.status_code >= 500:
            raise ERAFetchError(f"Stedi ERA server error {resp.status_code}", retryable=True)
        if resp.status_code >= 400:
            raise ERAFetchError(
                f"Stedi ERA rejected {resp.status_code}: {resp.text[:200]}", retryable=False
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise ERAFetchError(f"Stedi returned non-JSON ERA body: {resp.text[:200]}", retryable=True) from exc
