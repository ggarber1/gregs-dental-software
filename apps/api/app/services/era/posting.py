from __future__ import annotations

from typing import Any

from app.services.era.base import ClaimPayment

# X12 835 CLP02 (claim status). 1/2/3 processed; 19/20/21 processed-and-forwarded;
# 4 denied; 22 reversal. (research/15 incorrectly listed 19 as denied — it is not.)
_PROCESSED_CODES = {"1", "2", "3", "19", "20", "21"}
_DENIED_CODES = {"4", "22"}


def status_for_claim_payment(cp: ClaimPayment) -> str:
    """Map CLP02 + patient responsibility to a claim status.

    Never infers status from the paid amount: a $0 payment can be a valid accepted
    claim (Stedi guidance). 'partially_paid' means the patient still owes something.
    """
    if cp.claim_status_code in _DENIED_CODES:
        return "denied"
    if cp.claim_status_code in _PROCESSED_CODES:
        return "partially_paid" if cp.patient_responsibility_cents > 0 else "paid"
    # Unknown code: treat as denied-for-review rather than silently 'paid'.
    return "denied"


def claim_payment_fields(cp: ClaimPayment) -> dict[str, Any]:
    """The column values to post onto the claims row for this claim payment."""
    status = status_for_claim_payment(cp)
    adjustments = [{"group": a.group, "code": a.code, "cents": a.cents} for a in cp.adjustments]
    denial_codes = [a.code for a in cp.adjustments] if status == "denied" else None
    return {
        "insurance_paid_cents": cp.paid_cents,
        "patient_responsibility_cents": cp.patient_responsibility_cents,
        "payer_claim_control_number": cp.payer_claim_control_number,
        "adjustments": adjustments or None,
        "denial_codes": denial_codes,
        "status": status,
    }
