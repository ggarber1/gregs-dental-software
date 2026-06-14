"""Manual smoke test against Stedi's eligibility SANDBOX (test mode).

Exercises the REAL StediProvider + parser against a live mock eligibility check,
so we can confirm request-building, auth, and 271 parsing work end-to-end before
Staging Checkpoint 5 (which separately proves the ECS/NAT/SSM/IAM wiring).

Test mode is free and uses synthetic data only — no PHI, no charges. Stedi
requires the subscriber values to match a mock request EXACTLY; provider NPI can
be any value that passes check-digit validation.

Run from apps/api, supplying values via env (so the key never lands in source).
Easiest: put them in a gitignored file and source it:

    # apps/api/.stedi-smoke.env  (gitignored)
    export STEDI_TEST_API_KEY=...        # a Stedi *Test* mode key
    export STEDI_PAYER_ID=...            # mock tradingPartnerServiceId
    export STEDI_MEMBER_ID=...
    export STEDI_FIRST=...
    export STEDI_LAST=...
    export STEDI_DOB=YYYY-MM-DD
    # optional: STEDI_GROUP, STEDI_NPI (default 1999999984), STEDI_SUBMITTER

    set -a; source .stedi-smoke.env; set +a
    .venv/bin/python scripts/stedi_eligibility_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date

from app.services.eligibility.base import EligibilityProviderError, EligibilityRequest
from app.services.eligibility.stedi import StediProvider

_REQUIRED = (
    "STEDI_TEST_API_KEY",
    "STEDI_PAYER_ID",
    "STEDI_MEMBER_ID",
    "STEDI_FIRST",
    "STEDI_LAST",
    "STEDI_DOB",
)


def _build_request() -> EligibilityRequest:
    return EligibilityRequest(
        payer_id=os.environ["STEDI_PAYER_ID"],
        subscriber_id=os.environ["STEDI_MEMBER_ID"],
        group_number=os.environ.get("STEDI_GROUP") or None,
        subscriber_dob=date.fromisoformat(os.environ["STEDI_DOB"]),
        subscriber_first_name=os.environ["STEDI_FIRST"],
        subscriber_last_name=os.environ["STEDI_LAST"],
        provider_npi=os.environ.get("STEDI_NPI", "1999999984"),
        organization_name=os.environ.get("STEDI_ORG", "Provider Name"),
        submitter_id=os.environ.get("STEDI_SUBMITTER") or None,
        date_of_service=date.today(),
        control_number="112233445",
    )


async def main() -> int:
    missing = [k for k in _REQUIRED if not os.environ.get(k)]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        print(__doc__, file=sys.stderr)
        return 2

    provider = StediProvider(api_key=os.environ["STEDI_TEST_API_KEY"])
    request = _build_request()

    print("── Request payload (key NOT shown) ──")
    print(json.dumps(provider.build_payload(request), indent=2))

    try:
        result = await provider.check_eligibility(request)
    except EligibilityProviderError as exc:
        print(f"\n✗ EligibilityProviderError (retryable={exc.retryable}, "
              f"not_supported={exc.not_supported}):\n  {exc}", file=sys.stderr)
        return 1

    print("\n── Parsed EligibilityResult ──")
    print(f"status:                  {result.status}")
    print(f"payer / plan:            {result.payer_name} / {result.plan_name}")
    print(f"coverage start / end:    {result.coverage_start_date} / {result.coverage_end_date}")
    print(f"deductible ind (cents):  {result.deductible_individual}")
    print(f"annual max (cents):      {result.annual_max_individual}")
    print(f"annual max remaining:    {result.annual_max_individual_remaining}")
    print(f"oop max ind (cents):     {result.oop_max_individual}")
    print("coinsurance (patient share fraction):")
    print(f"  preventive {result.coinsurance_preventive}  basic {result.coinsurance_basic}"
          f"  major {result.coinsurance_major}  ortho {result.coinsurance_ortho}")
    print("\n✓ Live Stedi sandbox call succeeded and parsed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
