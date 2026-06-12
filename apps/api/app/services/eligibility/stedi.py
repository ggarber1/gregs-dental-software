from __future__ import annotations

import logging
from typing import Any

import httpx

from app.services.eligibility.base import (
    EligibilityProvider,
    EligibilityProviderError,
    EligibilityRequest,
    EligibilityResult,
)
from app.services.eligibility.parser import parse_stedi_response

logger = logging.getLogger(__name__)

_STEDI_URL = (
    "https://healthcare.us.stedi.com/2024-04-01/change/medicalnetwork/eligibility/v3"
)
# Stedi supports only service type code 35 (dental) for dental eligibility requests.
_DENTAL_SERVICE_TYPE_CODES = ["35"]
_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=15.0, pool=5.0)


class StediProvider(EligibilityProvider):
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._client = client  # injected in tests; created per-call in prod

    def build_payload(self, request: EligibilityRequest) -> dict[str, Any]:
        subscriber: dict[str, Any] = {
            "memberId": request.subscriber_id,
            "firstName": request.subscriber_first_name,
            "lastName": request.subscriber_last_name,
            "dateOfBirth": request.subscriber_dob.strftime("%Y%m%d"),
        }
        if request.group_number:
            subscriber["groupNumber"] = request.group_number
        provider: dict[str, Any] = {"npi": request.provider_npi}
        if request.submitter_id:
            provider["serviceProviderNumber"] = request.submitter_id
        return {
            "controlNumber": request.control_number,
            "tradingPartnerServiceId": request.payer_id,
            "provider": provider,
            "subscriber": subscriber,
            "encounter": {
                "dateOfService": request.date_of_service.strftime("%Y%m%d"),
                "serviceTypeCodes": _DENTAL_SERVICE_TYPE_CODES,
            },
        }

    async def check_eligibility(self, request: EligibilityRequest) -> EligibilityResult:
        payload = self.build_payload(request)
        headers = {"Authorization": f"Key {self._api_key}"}

        client = self._client or httpx.AsyncClient(timeout=_TIMEOUT)
        owns_client = self._client is None
        try:
            resp = await client.post(_STEDI_URL, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise EligibilityProviderError(f"Stedi timeout: {exc}", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise EligibilityProviderError(f"Stedi transport error: {exc}", retryable=True) from exc
        finally:
            if owns_client:
                await client.aclose()

        if resp.status_code >= 500:
            raise EligibilityProviderError(
                f"Stedi server error {resp.status_code}", retryable=True
            )
        if resp.status_code >= 400:
            raise EligibilityProviderError(
                f"Stedi rejected request {resp.status_code}: {resp.text}", not_supported=True
            )

        try:
            body = resp.json()
        except ValueError as exc:
            raise EligibilityProviderError(
                f"Stedi returned a non-JSON 200 body: {resp.text[:200]}", retryable=True
            ) from exc
        if body.get("errors"):
            raise EligibilityProviderError(
                f"Stedi AAA/payer error: {body['errors']}", not_supported=True
            )
        return parse_stedi_response(body)
