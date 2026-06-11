from __future__ import annotations

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
    assert set(payload["encounter"]["serviceTypeCodes"]) == {"35", "27", "F3", "AJ"}
    assert payload["provider"]["npi"] == "1234567890"


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
