"""Manual Stedi dental-claim sandbox smoke test. NOT run in CI.

Usage:
    source apps/api/.stedi-smoke.env   # exports STEDI_TEST_API_KEY + the test identity
    python apps/api/scripts/stedi_claim_smoke.py

Reuses the SAME env-driven test identity as scripts/stedi_eligibility_smoke.py so the
proven Stedi dental sandbox subscriber/payer is used:
    STEDI_TEST_API_KEY   a Stedi *Test* mode key
    STEDI_PAYER_ID       mock tradingPartnerServiceId (e.g. 62308)
    STEDI_MEMBER_ID
    STEDI_FIRST / STEDI_LAST / STEDI_DOB (YYYY-MM-DD)
    # optional: STEDI_GROUP, STEDI_NPI (default 1999999984), STEDI_SUBMITTER
    # optional: STEDI_TAX_ID (default 123456789), STEDI_TAXONOMY (default 1223G0001X)
    # optional: STEDI_SAMPLE_CDT (default D0120), STEDI_SAMPLE_FEE_CENTS (default 5000)

Submits a single sandbox dental claim with usageIndicator='T' — Stedi processes the claim
and returns a synchronous 277CA acknowledgment but does NOT forward it to a real payer.
This is the first real exercise of the Stedi dental-claims endpoint path + payload shape;
expect to iterate on field names against the live contract.
"""

import asyncio
import os
from datetime import date

from app.services.claims.base import ClaimLine, DentalClaimInput
from app.services.claims.stedi import StediClaimsClient

_REQUIRED = ("STEDI_TEST_API_KEY", "STEDI_PAYER_ID", "STEDI_MEMBER_ID", "STEDI_FIRST",
            "STEDI_LAST", "STEDI_DOB")


async def main() -> None:
    missing = [k for k in _REQUIRED if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"Missing env vars: {', '.join(missing)} (source .stedi-smoke.env)")

    api_key = os.environ["STEDI_TEST_API_KEY"]
    npi = os.environ.get("STEDI_NPI") or "1999999984"
    dob = date.fromisoformat(os.environ["STEDI_DOB"])
    cdt = os.environ.get("STEDI_SAMPLE_CDT") or "D0120"
    fee_cents = int(os.environ.get("STEDI_SAMPLE_FEE_CENTS") or "5000")

    claim = DentalClaimInput(
        patient_control_number="SMOKE0001",
        payer_id=os.environ["STEDI_PAYER_ID"],
        usage_indicator="T",
        billing_npi=npi,
        billing_tax_id=os.environ.get("STEDI_TAX_ID") or "123456789",
        billing_taxonomy_code=os.environ.get("STEDI_TAXONOMY") or "1223G0001X",
        billing_org_name="Downtown Dental",
        submitter_id=os.environ.get("STEDI_SUBMITTER") or "",
        rendering_npi=npi,
        rendering_first_name="Jane",
        rendering_last_name="Dentist",
        subscriber_first_name=os.environ["STEDI_FIRST"],
        subscriber_last_name=os.environ["STEDI_LAST"],
        subscriber_dob=dob,
        member_id=os.environ["STEDI_MEMBER_ID"],
        group_number=os.environ.get("STEDI_GROUP") or None,
        relationship_to_insured="self",
        patient_first_name=os.environ["STEDI_FIRST"],
        patient_last_name=os.environ["STEDI_LAST"],
        patient_dob=dob,
        date_of_service=date.today(),
        lines=(
            ClaimLine(
                procedure_id="line-1", cdt_code=cdt, fee_cents=fee_cents,
                tooth_number=None, surface=None, procedure_name="Sample procedure",
            ),
        ),
    )

    print(f"Submitting test dental claim to Stedi (payer={claim.payer_id}, "
          f"member={claim.member_id}, {cdt} ${fee_cents / 100:.2f}, usageIndicator=T)…")
    client = StediClaimsClient(api_key=api_key)
    result = await client.submit_dental_claim(claim, "smoke-claim-0001")
    print("accepted:", result.accepted)
    print("clearinghouse_claim_id:", result.clearinghouse_claim_id)
    print("status:", result.clearinghouse_status)
    print("errors:", result.errors)
    print("raw_response:", result.raw_response)


if __name__ == "__main__":
    asyncio.run(main())
