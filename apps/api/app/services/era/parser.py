from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from typing import Any

from app.services.era.base import ClaimAdjustment, ClaimPayment, ERAPayment


def _to_cents(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return 0


def _to_cents_opt(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if not value or not isinstance(value, str):
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _iter_claim_payment_objs(transaction: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield each claim-payment JSON object inside one 835 transaction.

    ISOLATED traversal — the single place to adjust if the real recorded Stedi
    response nests claim payments differently (verify at Staging Checkpoint 5).
    Documented shape: transaction.detailInfo[].paymentInfo[].
    """
    for detail in transaction.get("detailInfo") or []:
        for cp in detail.get("paymentInfo") or []:
            yield cp


def _parse_adjustments(cp_obj: dict[str, Any]) -> tuple[ClaimAdjustment, ...]:
    out: list[ClaimAdjustment] = []
    for group_obj in cp_obj.get("claimAdjustments") or []:
        group = str(group_obj.get("claimAdjustmentGroupCode") or "")
        for detail in group_obj.get("adjustmentDetails") or []:
            out.append(
                ClaimAdjustment(
                    group=group,
                    code=str(detail.get("adjustmentReasonCode") or ""),
                    cents=_to_cents(detail.get("adjustmentAmount")),
                )
            )
    return tuple(out)


def _parse_claim_payment(cp_obj: dict[str, Any]) -> ClaimPayment:
    info = cp_obj.get("claimPaymentInfo") or {}
    return ClaimPayment(
        patient_control_number=str(info.get("patientControlNumber") or ""),
        claim_status_code=str(info.get("claimStatusCode") or ""),
        total_charge_cents=_to_cents(info.get("totalClaimChargeAmount")),
        paid_cents=_to_cents(info.get("claimPaymentAmount")),
        patient_responsibility_cents=_to_cents(info.get("patientResponsibilityAmount")),
        payer_claim_control_number=info.get("payerClaimControlNumber") or None,
        adjustments=_parse_adjustments(cp_obj),
        raw=cp_obj,
    )


def parse_stedi_era(raw: dict[str, Any]) -> ERAPayment:
    """Parse a Stedi 835 ERA JSON document into a domain ERAPayment.

    Fail-soft on missing fields (a malformed claim yields zeros/empties rather than
    crashing the whole poll), but never silently drops a claim payment — every
    paymentInfo object becomes a ClaimPayment.
    """
    transactions = raw.get("transactions") or []
    txn = transactions[0] if transactions else {}

    fin = txn.get("financialInformation") or {}
    trn = txn.get("reassociationTraceNumber") or {}

    claim_payments = tuple(
        _parse_claim_payment(cp_obj)
        for t in transactions
        for cp_obj in _iter_claim_payment_objs(t)
    )

    return ERAPayment(
        payer_name=(txn.get("payer") or {}).get("name"),
        trace_number=trn.get("checkOrEftTraceNumber") or None,
        payment_cents=_to_cents_opt(fin.get("totalActualProviderPaymentAmount")),
        payment_date=_parse_date(txn.get("productionDate")),
        claim_payments=claim_payments,
        raw=raw,
    )
