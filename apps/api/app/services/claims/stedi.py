from __future__ import annotations

import logging
from typing import Any

import httpx

from app.services.claims.base import (
    ClaimResult,
    ClaimSubmissionError,
    ClearinghouseClient,
    DentalClaimInput,
)

logger = logging.getLogger(__name__)

# NOTE: confirm the exact path/version against the Stedi Dental Claims (837D) JSON
# reference and the sandbox smoke test before going live. Unit tests do not
# depend on this value (httpx is mocked).
_STEDI_DENTAL_CLAIMS_URL = (
    "https://healthcare.us.stedi.com/2024-04-01/change/medicalnetwork/dentalclaims/v3"
)
_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=15.0, pool=5.0)

# Stedi "paymentResponsibilityLevelCode": P = primary.
_PRIMARY = "P"


def _cents_to_dollars(cents: int) -> str:
    return f"{cents / 100:.2f}"


class StediClaimsClient(ClearinghouseClient):
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._client = client  # injected in tests; created per-call in prod

    def to_stedi_payload(self, claim: DentalClaimInput) -> dict[str, Any]:
        service_date = claim.date_of_service.strftime("%Y%m%d")
        service_lines: list[dict[str, Any]] = []
        for line in claim.lines:
            entry: dict[str, Any] = {
                "procedureCodeQualifier": "AD",
                "procedureCode": line.cdt_code,
                "lineItemChargeAmount": _cents_to_dollars(line.fee_cents),
                "unitOrBasisForMeasurementCode": "UN",
                "serviceUnitCount": "1",
                "serviceDate": service_date,
                "lineItemControlNumber": line.procedure_id,
            }
            if line.tooth_number:
                entry["toothNumber"] = line.tooth_number
            service_lines.append(entry)

        subscriber = {
            "memberId": claim.member_id,
            "paymentResponsibilityLevelCode": _PRIMARY,
            "firstName": claim.subscriber_first_name,
            "lastName": claim.subscriber_last_name,
            "dateOfBirth": claim.subscriber_dob.strftime("%Y%m%d"),
        }
        if claim.group_number:
            subscriber["groupNumber"] = claim.group_number

        # NOTE: claim.submitter_id is validated as a required practice config (see validator)
        # but is NOT sent per-claim — Stedi derives the submitter/trading-partner identity from
        # the account behind the API key. It will be needed by the DentalXChange raw-X12 path (deferred).
        payload: dict[str, Any] = {
            "usageIndicator": claim.usage_indicator,
            "controlNumber": claim.patient_control_number,
            "tradingPartnerServiceId": claim.payer_id,
            "submitter": {
                "organizationName": claim.billing_org_name,
                "contactInformation": {"name": claim.billing_org_name},
            },
            "receiver": {"organizationName": claim.payer_id},
            "billing": {
                "providerType": "BillingProvider",
                "npi": claim.billing_npi,
                "employerId": claim.billing_tax_id,
                "taxonomyCode": claim.billing_taxonomy_code,
                "organizationName": claim.billing_org_name,
            },
            "rendering": {
                "providerType": "RenderingProvider",
                "npi": claim.rendering_npi,
                "firstName": claim.rendering_first_name,
                "lastName": claim.rendering_last_name,
            },
            "subscriber": subscriber,
            "claimInformation": {
                "patientControlNumber": claim.patient_control_number,
                "claimChargeAmount": _cents_to_dollars(claim.total_charge_cents),
                "placeOfServiceCode": "11",  # office
                "claimFrequencyCode": "1",   # original
                "benefitsAssignmentCertificationIndicator": "Y",
                "serviceLines": service_lines,
            },
        }

        if claim.relationship_to_insured != "self":
            payload["dependent"] = {
                "firstName": claim.patient_first_name,
                "lastName": claim.patient_last_name,
                "dateOfBirth": claim.patient_dob.strftime("%Y%m%d"),
                "relationshipToSubscriberCode": _relationship_code(claim.relationship_to_insured),
            }

        return payload

    async def submit_dental_claim(
        self, claim: DentalClaimInput, idempotency_key: str
    ) -> ClaimResult:
        payload = self.to_stedi_payload(claim)
        headers = {"Authorization": f"Key {self._api_key}", "Idempotency-Key": idempotency_key}

        client = self._client or httpx.AsyncClient(timeout=_TIMEOUT)
        owns_client = self._client is None
        try:
            resp = await client.post(_STEDI_DENTAL_CLAIMS_URL, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ClaimSubmissionError(f"Stedi timeout: {exc}", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ClaimSubmissionError(f"Stedi transport error: {exc}", retryable=True) from exc
        finally:
            if owns_client:
                await client.aclose()

        if resp.status_code >= 500:
            raise ClaimSubmissionError(
                f"Stedi server error {resp.status_code}", retryable=True
            )

        if resp.status_code in (401, 403):
            raise ClaimSubmissionError(
                f"Stedi auth error {resp.status_code}: {resp.text[:200]}", retryable=False
            )

        try:
            body = resp.json()
        except ValueError as exc:
            raise ClaimSubmissionError(
                f"Stedi returned a non-JSON {resp.status_code} body: {resp.text[:200]}",
                retryable=True,
            ) from exc

        errors = _extract_errors(body)
        # A 4xx or an explicit error/rejection is a clearinghouse edit failure (not retryable).
        status = str(body.get("submissionStatus", "")).upper()
        accepted = resp.status_code < 400 and not errors and status not in ("REJECTED", "ERROR")

        return ClaimResult(
            accepted=accepted,
            clearinghouse_claim_id=body.get("transactionId"),
            clearinghouse_status=body.get("submissionStatus"),
            errors=errors,
            raw_request=payload,
            raw_response=body,
        )


def _relationship_code(relationship: str) -> str:
    # X12 individual relationship codes: 01 spouse, 19 child, G8 other.
    code = {"spouse": "01", "child": "19", "other": "G8"}.get(relationship)
    if code is None:
        logger.warning("Unknown relationship_to_insured %r; defaulting to 'other' (G8)", relationship)
        return "G8"
    return code


def _extract_errors(body: dict[str, Any]) -> list[str]:
    raw = body.get("errors") or []
    out: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(str(item.get("description") or item.get("message") or item))
        else:
            out.append(str(item))
    return out
