from __future__ import annotations

import logging
from typing import Any

import httpx

from app.services.claims.base import (
    Address,
    ClaimResult,
    ClaimSubmissionError,
    ClearinghouseClient,
    DentalClaimInput,
)

logger = logging.getLogger(__name__)

# Endpoint path + `Authorization: Key <key>` confirmed via the live sandbox smoke run
# (scripts/stedi_claim_smoke.py). NOTE: this endpoint is NOT available with a Stedi
# Test-Mode API key (returns 403 access_denied) — it needs a full-access/production key.
# The nested JSON field names in to_stedi_payload() remain unverified against a real
# accepted claim (the smoke run is blocked by the test-mode key tier). Unit tests mock
# httpx and do not depend on this URL.
# Payload aligned to Stedi's documented Dental Claims (837D) JSON schema 2026-06-19;
# key changes vs X12: renderingProvider (not rendering), tooth data under dentalService,
# serviceUnitCount numeric, releaseInformationCode required. Known gaps until tested with
# a full-access key: receiver uses payer_id as org name; non-self subscriber
# gender/address fall back to patient/unknown.
_STEDI_DENTAL_CLAIMS_URL = "https://healthcare.us.stedi.com/2024-04-01/dental-claims/submission"
_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=15.0, pool=5.0)

# Stedi "paymentResponsibilityLevelCode": P = primary.
_PRIMARY = "P"


def _cents_to_dollars(cents: int) -> str:
    return f"{cents / 100:.2f}"


def _address(addr: Address) -> dict[str, str]:
    return {
        "address1": addr.line1,
        "city": addr.city,
        "state": addr.state,
        "postalCode": addr.postal_code,
    }


class StediClaimsClient(ClearinghouseClient):
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._client = client  # injected in tests; created per-call in prod

    def to_stedi_payload(self, claim: DentalClaimInput) -> dict[str, Any]:
        service_date = claim.date_of_service.strftime("%Y%m%d")
        service_lines: list[dict[str, Any]] = []
        for line in claim.lines:
            entry: dict[str, Any] = {
                "procedureCode": line.cdt_code,
                "lineItemChargeAmount": _cents_to_dollars(line.fee_cents),
                "serviceUnitCount": 1,
                "unitOrBasisForMeasurementCode": "UN",
                "serviceDate": service_date,
                "lineItemControlNumber": line.procedure_id,
            }
            dental: dict[str, Any] = {}
            if line.tooth_number:
                dental["toothNumber"] = line.tooth_number
            if line.surface:
                dental["toothInformation"] = {"toothSurfaceCode": line.surface}
            if dental:
                entry["dentalService"] = dental
            service_lines.append(entry)

        subscriber: dict[str, Any] = {
            "memberId": claim.member_id,
            "paymentResponsibilityLevelCode": _PRIMARY,
            "firstName": claim.subscriber_first_name,
            "lastName": claim.subscriber_last_name,
            "dateOfBirth": claim.subscriber_dob.strftime("%Y%m%d"),
            "gender": claim.subscriber_gender,
            "address": _address(claim.subscriber_address),
        }
        if claim.group_number:
            subscriber["groupNumber"] = claim.group_number

        # NOTE: claim.submitter_id is validated as a required practice config (see
        # validator) but is NOT sent per-claim — Stedi derives the submitter/trading-
        # partner identity from the account behind the API key. It will be needed by the
        # DentalXChange raw-X12 path (deferred).
        payload: dict[str, Any] = {
            "usageIndicator": claim.usage_indicator,
            "tradingPartnerServiceId": claim.payer_id,
            "submitter": {
                "organizationName": claim.billing_org_name,
                "contactInformation": {"name": claim.billing_org_name},
            },
            # receiver.organizationName should be the payer NAME; we only carry the payer
            # id, so this is a known best-effort gap until a payer-name source is threaded.
            "receiver": {"organizationName": claim.payer_id},
            "billing": {
                "npi": claim.billing_npi,
                "employerId": claim.billing_tax_id,
                "taxonomyCode": claim.billing_taxonomy_code,
                "organizationName": claim.billing_org_name,
                "address": _address(claim.billing_address),
            },
            "renderingProvider": {
                "npi": claim.rendering_npi,
                "firstName": claim.rendering_first_name,
                "lastName": claim.rendering_last_name,
                "taxonomyCode": claim.billing_taxonomy_code,
            },
            "subscriber": subscriber,
            "claimInformation": {
                "patientControlNumber": claim.patient_control_number,
                "claimChargeAmount": _cents_to_dollars(claim.total_charge_cents),
                "placeOfServiceCode": "11",
                "claimFrequencyCode": claim.claim_frequency_code,
                "benefitsAssignmentCertificationIndicator": "Y",
                "releaseInformationCode": "Y",
                "serviceLines": service_lines,
            },
        }

        claim_info = payload["claimInformation"]
        if claim.claim_frequency_code == "7" and claim.original_claim_reference:
            claim_info["originalClaimNumber"] = claim.original_claim_reference

        if claim.relationship_to_insured != "self":
            payload["dependent"] = {
                "firstName": claim.patient_first_name,
                "lastName": claim.patient_last_name,
                "dateOfBirth": claim.patient_dob.strftime("%Y%m%d"),
                "gender": claim.patient_gender,
                "relationshipToSubscriber": _relationship_code(claim.relationship_to_insured),
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
        logger.warning(
            "Unknown relationship_to_insured %r; defaulting to 'other' (G8)", relationship
        )
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
