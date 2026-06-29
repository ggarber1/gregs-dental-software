from __future__ import annotations

_UNDERPAY_THRESHOLD = 0.95  # flag when insurance pays < 95% of the Module 6 estimate


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
