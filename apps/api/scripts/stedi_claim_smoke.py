"""Manual Stedi dental-claim sandbox smoke test. NOT run in CI.

Usage:
    source apps/api/.stedi-smoke.env   # exports STEDI_TEST_API_KEY
    python apps/api/scripts/stedi_claim_smoke.py

Verifies the real Stedi Dental Claims (837D) JSON endpoint path, payload shape, and the
synchronous 277CA response against a sandbox test claim (usageIndicator='T' — Stedi
processes but does not forward to a payer).
"""

import asyncio
import os
from datetime import date

from app.services.claims.base import ClaimLine, DentalClaimInput
from app.services.claims.stedi import StediClaimsClient


async def main() -> None:
    api_key = os.environ["STEDI_TEST_API_KEY"]
    claim = DentalClaimInput(
        patient_control_number="SMOKE0001",
        payer_id="CIGNA",            # adjust to the Stedi dental sandbox payer id
        usage_indicator="T",
        billing_npi="1999999984",    # Stedi sandbox billing NPI — confirm in Stedi docs
        billing_tax_id="123456789",
        billing_taxonomy_code="1223G0001X",
        billing_org_name="Downtown Dental",
        submitter_id="SUBMITTER",
        rendering_npi="1999999984",
        rendering_first_name="Jane",
        rendering_last_name="Dentist",
        subscriber_first_name="Jaguar",
        subscriber_last_name="Dent",
        subscriber_dob=date(1996, 5, 5),
        member_id="U3141592653",
        group_number=None,
        relationship_to_insured="self",
        patient_first_name="Jaguar",
        patient_last_name="Dent",
        patient_dob=date(1996, 5, 5),
        date_of_service=date.today(),
        lines=(
            ClaimLine(
                procedure_id="line-1", cdt_code="D0120", fee_cents=5000,
                tooth_number=None, surface=None, procedure_name="Periodic exam",
            ),
        ),
    )
    client = StediClaimsClient(api_key=api_key)
    result = await client.submit_dental_claim(claim, "smoke-claim-0001")
    print("accepted:", result.accepted)
    print("clearinghouse_claim_id:", result.clearinghouse_claim_id)
    print("status:", result.clearinghouse_status)
    print("errors:", result.errors)
    print("raw_response:", result.raw_response)


if __name__ == "__main__":
    asyncio.run(main())
