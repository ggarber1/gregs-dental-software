"""Manual smoke test against Stedi's eligibility SANDBOX (test mode).

Exercises the REAL StediProvider + parser against a live mock eligibility check,
then feeds the parsed result through the REAL co-pay engine (Module 6) to print a
sample patient-responsibility estimate — so we can confirm request-building, auth,
271 parsing, AND the eligibility→co-pay chain all work end-to-end on live test data
before Staging Checkpoint 5 (which separately proves the ECS/NAT/SSM/IAM wiring).

The co-pay step reuses the production `_snapshot` / `_resolve_coinsurance` helpers
and `calculate_patient_responsibility`, so it exercises the same code the API runs
(no reimplementation). It drives sample procedures off the live 271's per-CDT-code
coinsurance map when present, falling back to a couple of common codes otherwise.

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
    # optional: STEDI_SAMPLE_FEE_CENTS (default 20000 = $200 per sample procedure)

    set -a; source .stedi-smoke.env; set +a
    .venv/bin/python scripts/stedi_eligibility_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date

from app.services.copay.engine import calculate_patient_responsibility
from app.services.copay.models import ProcedureInput
from app.services.copay.service import _resolve_coinsurance, _snapshot
from app.services.eligibility.base import (
    EligibilityProviderError,
    EligibilityRequest,
    EligibilityResult,
)
from app.services.eligibility.parser import _cdt_category
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
    print(f"plan_type / network:     {result.plan_type} / {result.network_status}")
    print("coinsurance category fallback (patient share fraction):")
    print(f"  preventive {result.coinsurance_preventive}  basic {result.coinsurance_basic}"
          f"  major {result.coinsurance_major}  ortho {result.coinsurance_ortho}")
    print(f"coinsurance by CDT code:  {result.coinsurance_by_code}")

    _print_copay_estimate(result)

    print("\n✓ Live Stedi sandbox call succeeded, parsed, and ran through the co-pay engine.")
    return 0


def _print_copay_estimate(result: EligibilityResult) -> None:
    """Feed the parsed eligibility through the production co-pay engine on sample
    procedures and print the breakdown. Sample codes come from the live 271's per-code
    coinsurance map when present (exercising the per-CDT-code path), else two common
    codes that resolve via the category fallback."""
    # Pick one representative code per distinct patient-share so the demo spans the
    # 0% / coinsurance / major splits (the first-N keys often cluster in one category).
    by_share: dict[float, str] = {}
    for code, sh in (result.coinsurance_by_code or {}).items():
        by_share.setdefault(sh, code)
    codes = list(by_share.values())[:6] or ["D1110", "D2740"]
    sample_fee = int(os.environ.get("STEDI_SAMPLE_FEE_CENTS", "20000"))

    procedures = [
        ProcedureInput(
            procedure_id=code,
            cdt_code=code,
            category=_cdt_category(code),
            provider_fee_cents=sample_fee,
            allowed_amount_cents=None,  # no contracted fee in the smoke script
            coinsurance_patient_share=_resolve_coinsurance(result, code, _cdt_category(code)),
        )
        for code in codes
    ]

    snapshot = _snapshot(result)
    breakdown = calculate_patient_responsibility(snapshot, procedures, date.today())
    share = {p.cdt_code: p.coinsurance_patient_share for p in procedures}

    print("\n── Co-pay estimate (parsed eligibility → engine) ──")
    print(f"deductible remaining:    {snapshot.deductible_remaining_cents}c   "
          f"annual max remaining: {snapshot.annual_max_remaining_cents}c   "
          f"(sample fee {sample_fee}c/proc)")
    header = f"  {'code':7}{'cat':11}{'coins':>6}{'write':>9}{'ins':>9}{'patient':>9}  flags"
    print(header)
    for li in breakdown.line_items:
        flags = ",".join(
            name for name, on in (
                ("manual", li.needs_manual_entry),
                ("not_covered", li.not_covered),
                ("freq", li.is_frequency_exceeded),
                ("wait", li.is_in_waiting_period),
                ("max_cap", li.annual_max_cap_applied),
            ) if on
        )
        coins = share.get(li.cdt_code)
        coins_str = "manual" if coins is None else f"{coins:.2f}"
        print(f"  {li.cdt_code:7}{li.category:11}{coins_str:>6}"
              f"{li.write_off_cents:>9}{li.insurance_owes_cents:>9}{li.patient_owes_cents:>9}"
              f"  {flags}")
        assert (
            li.write_off_cents + li.patient_owes_cents + li.insurance_owes_cents
            == li.provider_fee_cents
        ), f"identity violated on {li.cdt_code}"

    print(f"  TOTAL  write {breakdown.total_write_off_cents}c  "
          f"insurance {breakdown.total_insurance_owes_cents}c  "
          f"patient {breakdown.total_patient_owes_cents}c  "
          f"(fee {breakdown.total_provider_fee_cents}c)")
    assert (
        breakdown.total_write_off_cents
        + breakdown.total_patient_owes_cents
        + breakdown.total_insurance_owes_cents
        == breakdown.total_provider_fee_cents
    )
    print("  ✓ accounting identity holds (fee == write_off + patient + insurance)")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
