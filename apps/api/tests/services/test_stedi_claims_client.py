from datetime import date

import httpx
import pytest

from app.services.claims.base import ClaimLine, ClaimSubmissionError, DentalClaimInput
from app.services.claims.stedi import StediClaimsClient

_CLAIM = DentalClaimInput(
    patient_control_number="ABC123",
    payer_id="CDLA1",
    usage_indicator="T",
    billing_npi="1234567890",
    billing_tax_id="123456789",
    billing_taxonomy_code="1223G0001X",
    billing_org_name="Downtown Dental",
    submitter_id="SUB1",
    rendering_npi="1234567890",
    rendering_first_name="Jane",
    rendering_last_name="Dentist",
    subscriber_first_name="John",
    subscriber_last_name="Smith",
    subscriber_dob=date(1980, 1, 1),
    member_id="U123",
    group_number="GRP1",
    relationship_to_insured="self",
    patient_first_name="John",
    patient_last_name="Smith",
    patient_dob=date(1980, 1, 1),
    date_of_service=date(2026, 6, 18),
    lines=(
        ClaimLine(
            procedure_id="proc-1", cdt_code="D2392", fee_cents=20000,
            tooth_number="14", surface="O", procedure_name="Resin composite",
        ),
        ClaimLine(
            procedure_id="proc-2", cdt_code="D0120", fee_cents=5000,
            tooth_number=None, surface=None, procedure_name="Periodic exam",
        ),
    ),
)


def test_payload_maps_money_to_dollar_strings_and_lines():
    client = StediClaimsClient(api_key="k")
    payload = client.to_stedi_payload(_CLAIM)
    assert payload["usageIndicator"] == "T"
    assert payload["tradingPartnerServiceId"] == "CDLA1"
    info = payload["claimInformation"]
    assert info["patientControlNumber"] == "ABC123"
    assert info["claimChargeAmount"] == "250.00"  # 20000 + 5000 cents
    lines = info["serviceLines"]
    assert len(lines) == 2
    assert lines[0]["procedureCodeQualifier"] == "AD"
    assert lines[0]["procedureCode"] == "D2392"
    assert lines[0]["lineItemChargeAmount"] == "200.00"
    assert lines[0]["toothNumber"] == "14"
    assert lines[0]["lineItemControlNumber"] == "proc-1"
    assert lines[0]["serviceDate"] == "20260618"
    # subscriber omitted dependent when relationship is self
    assert "dependent" not in payload


def _client_returning(status_code: int, json_body: dict) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_body)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_accepted_response_returns_accepted_result():
    body = {
        "transactionId": "txn-1",
        "businessIdentifier": "biz-1",
        "submissionStatus": "ACCEPTED",
    }
    client = StediClaimsClient(api_key="k", client=_client_returning(200, body))
    result = await client.submit_dental_claim(_CLAIM, "idem-1")
    assert result.accepted is True
    assert result.clearinghouse_claim_id == "txn-1"
    assert result.errors == []


@pytest.mark.asyncio
async def test_edit_rejection_returns_not_accepted_with_errors():
    body = {
        "transactionId": "txn-2",
        "submissionStatus": "REJECTED",
        "errors": [{"description": "Invalid member ID"}],
    }
    client = StediClaimsClient(api_key="k", client=_client_returning(200, body))
    result = await client.submit_dental_claim(_CLAIM, "idem-2")
    assert result.accepted is False
    assert any("member" in e.lower() for e in result.errors)


@pytest.mark.asyncio
async def test_server_error_raises_retryable():
    client = StediClaimsClient(api_key="k", client=_client_returning(503, {}))
    with pytest.raises(ClaimSubmissionError) as exc:
        await client.submit_dental_claim(_CLAIM, "idem-3")
    assert exc.value.retryable is True


@pytest.mark.asyncio
async def test_sends_key_auth_and_idempotency_header():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        captured["idem"] = request.headers.get("Idempotency-Key")
        return httpx.Response(200, json={"transactionId": "t", "submissionStatus": "ACCEPTED"})

    client = StediClaimsClient(
        api_key="secret", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    await client.submit_dental_claim(_CLAIM, "idem-9")
    assert captured["auth"] == "Key secret"
    assert captured["idem"] == "idem-9"
