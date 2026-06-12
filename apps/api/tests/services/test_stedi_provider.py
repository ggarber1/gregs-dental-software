from __future__ import annotations

import dataclasses
from datetime import date

import httpx
import pytest

from app.services.eligibility.base import (
    EligibilityProviderError,
    EligibilityRequest,
    EligibilityStatus,
)
from app.services.eligibility.stedi import StediProvider

_REQ = EligibilityRequest(
    payer_id="CDELT",
    subscriber_id="XYZ123",
    group_number="GRP001",
    subscriber_dob=date(1980, 1, 1),
    subscriber_first_name="John",
    subscriber_last_name="Smith",
    provider_npi="1234567890",
    submitter_id="SUB1",
    date_of_service=date(2026, 4, 10),
    control_number="000000001",
)


def _client_returning(status_code: int, json_body: dict) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_build_request_payload_shape():
    provider = StediProvider(api_key="k")
    payload = provider.build_payload(_REQ)
    assert payload["tradingPartnerServiceId"] == "CDELT"
    assert payload["subscriber"]["memberId"] == "XYZ123"
    assert payload["subscriber"]["dateOfBirth"] == "19800101"
    assert payload["encounter"]["dateOfService"] == "20260410"
    # Stedi supports only STC 35 for dental eligibility.
    assert payload["encounter"]["serviceTypeCodes"] == ["35"]
    assert payload["provider"]["npi"] == "1234567890"


async def test_check_eligibility_sends_key_auth_header():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(200, json={"benefitsInformation": [{"code": "1"}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await StediProvider(api_key="secret123", client=client).check_eligibility(_REQ)
    assert captured["auth"] == "Key secret123"


async def test_check_eligibility_success_parses_result():
    body = {
        "benefitsInformation": [{"code": "1", "name": "Active Coverage"}],
        "payer": {"name": "Delta Dental"},
    }
    provider = StediProvider(api_key="k", client=_client_returning(200, body))
    result = await provider.check_eligibility(_REQ)
    assert result.status == EligibilityStatus.ACTIVE
    assert result.payer_name == "Delta Dental"


async def test_payer_not_found_raises_not_supported():
    body = {"errors": [{"code": "AAA", "description": "Payer not found"}]}
    provider = StediProvider(api_key="k", client=_client_returning(200, body))
    with pytest.raises(EligibilityProviderError) as exc:
        await provider.check_eligibility(_REQ)
    assert exc.value.not_supported is True


async def test_server_error_raises_retryable():
    provider = StediProvider(api_key="k", client=_client_returning(503, {"message": "down"}))
    with pytest.raises(EligibilityProviderError) as exc:
        await provider.check_eligibility(_REQ)
    assert exc.value.retryable is True


def test_build_payload_omits_optional_fields_when_none():
    req = dataclasses.replace(_REQ, group_number=None, submitter_id=None)
    payload = StediProvider(api_key="k").build_payload(req)
    assert "groupNumber" not in payload["subscriber"]
    assert "serviceProviderNumber" not in payload["provider"]


async def test_timeout_raises_retryable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = StediProvider(api_key="k", client=client)
    with pytest.raises(EligibilityProviderError) as exc:
        await provider.check_eligibility(_REQ)
    assert exc.value.retryable is True


async def test_http_400_raises_not_supported():
    provider = StediProvider(api_key="k", client=_client_returning(400, {"message": "bad"}))
    with pytest.raises(EligibilityProviderError) as exc:
        await provider.check_eligibility(_REQ)
    assert exc.value.not_supported is True
