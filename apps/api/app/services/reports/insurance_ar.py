from __future__ import annotations

from datetime import datetime
from typing import Any

_UNDERPAY_THRESHOLD = 0.95  # flag when insurance pays < 95% of the Module 6 estimate
_PROBLEM_STATUSES = frozenset({"denied", "clearinghouse_rejected", "submission_failed"})


def age_bucket(days_out: int) -> str:
    if days_out <= 30:
        return "0-30"
    if days_out <= 60:
        return "31-60"
    if days_out <= 90:
        return "61-90"
    return "90+"


def is_underpaid(
    insurance_paid_cents: int | None, estimated_insurance_cents: int | None
) -> bool:
    """True when an ERA has posted and the carrier paid more than 5% below estimate."""
    if insurance_paid_cents is None or estimated_insurance_cents is None:
        return False
    if estimated_insurance_cents <= 0:
        return False
    return insurance_paid_cents < _UNDERPAY_THRESHOLD * estimated_insurance_cents


def classify(
    *,
    status: str,
    insurance_paid_cents: int | None,
    estimated_insurance_cents: int | None,
    insurance_reviewed_at: datetime | None,
) -> str | None:
    """Return the worklist category, or None for 'Done' (excluded).

    Evaluated in order so the status label never overrides a real signal:
    appealing -> problem -> awaiting (no payment) -> underpaid (vs estimate) -> Done.
    """
    if status == "draft":
        return None  # never sent
    if status == "appealing":
        return "appealing"
    if status in _PROBLEM_STATUSES:
        return "problem"
    if insurance_paid_cents is None:
        return "awaiting"
    if insurance_reviewed_at is None and is_underpaid(
        insurance_paid_cents, estimated_insurance_cents
    ):
        return "underpaid"
    return None  # paid as expected, or no estimate, or already reviewed


def reason_for(claim: Any) -> str | None:
    """Human-ish reason for a problem claim (raw X12 codes; friendly map is a follow-up)."""
    if claim.status == "denied":
        codes = list(claim.denial_codes or [])
        return f"denied: {', '.join(codes)}" if codes else "denied"
    if claim.status in ("clearinghouse_rejected", "submission_failed"):
        errs = list(claim.submission_errors or [])
        if errs:
            return "; ".join(errs)
        return str(claim.clearinghouse_status or claim.status)
    return None
