from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment_procedure import AppointmentProcedure
from app.models.claim import Claim
from app.models.copay_calculation import CopayCalculation
from app.models.insurance_plan import InsurancePlan
from app.models.ledger_entry import LedgerEntry
from app.models.patient import Patient
from app.models.practice import Practice
from app.services.reports.insurance_ar import (
    get_worklist as _get_ar_worklist,
)

_UNDERPAY_PCT = 95  # must match insurance_ar._UNDERPAY_PCT
_PROBLEM_STATUSES = frozenset({"denied", "clearinghouse_rejected", "submission_failed"})

ReconciliationLabel = Literal["overpaid", "within_tolerance", "matched", "no_estimate"]


def classify_for_reconciliation(
    insurance_paid_cents: int,
    estimated_insurance_cents: int | None,
) -> ReconciliationLabel | None:
    """Return reconciliation label, or None if claim is underpaid (goes to insurance-ar).

    None means the claim is underpaid (paid < 95% of estimate) — it belongs
    in the Underpaid tab, not here.
    """
    if estimated_insurance_cents is None or estimated_insurance_cents <= 0:
        return "no_estimate"
    if insurance_paid_cents > estimated_insurance_cents:
        return "overpaid"
    if insurance_paid_cents == estimated_insurance_cents:
        return "matched"
    # paid < estimate — is it within tolerance or underpaid?
    if 100 * insurance_paid_cents >= _UNDERPAY_PCT * estimated_insurance_cents:
        return "within_tolerance"
    return None  # underpaid


@dataclass(frozen=True, kw_only=True)
class ReconciliationRow:
    claim_id: uuid.UUID
    appointment_id: uuid.UUID
    patient_id: uuid.UUID
    claim_number: str
    patient_name: str
    payer_id: str
    carrier_name: str
    recon_label: ReconciliationLabel
    billed_cents: int
    estimated_insurance_cents: int | None
    insurance_paid_cents: int
    variance_cents: int | None  # positive=overpaid, negative=shortfall, None=no estimate
    has_estimate: bool
    patient_balance_cents: int
    days_since_era: int
    reconciliation_confirmed_at: datetime | None


@dataclass
class ARSummaryData:
    insurance_ar_total_cents: int
    patient_ar_total_cents: int
    claims_needing_attention: int
    reconciliation_pending_count: int
    era_reconciliation_mode: Literal["auto", "confirm"]


async def _estimate_map(
    session: AsyncSession, appt_ids: set[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not appt_ids:
        return {}
    out: dict[uuid.UUID, int] = {}
    calcs = (
        await session.scalars(
            select(CopayCalculation)
            .where(CopayCalculation.appointment_id.in_(appt_ids))
            .order_by(CopayCalculation.appointment_id, CopayCalculation.created_at.desc())
        )
    ).all()
    for c in calcs:
        if c.appointment_id not in out:
            out[c.appointment_id] = int(c.total_insurance_owes_cents)
    missing = appt_ids - out.keys()
    if missing:
        rows = (
            await session.execute(
                select(
                    AppointmentProcedure.appointment_id,
                    func.sum(AppointmentProcedure.insurance_est_cents),
                )
                .where(
                    AppointmentProcedure.appointment_id.in_(missing),
                    AppointmentProcedure.insurance_est_cents.is_not(None),
                )
                .group_by(AppointmentProcedure.appointment_id)
            )
        ).all()
        for appt_id, total in rows:
            if total is not None:
                out[appt_id] = int(total)
    return out


async def _patient_name_map(
    session: AsyncSession, patient_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    if not patient_ids:
        return {}
    rows = (
        await session.execute(
            select(Patient.id, Patient.first_name, Patient.last_name).where(
                Patient.id.in_(patient_ids)
            )
        )
    ).all()
    return {pid: f"{first} {last}" for pid, first, last in rows}


async def _carrier_name_map(
    session: AsyncSession, payer_ids: set[str]
) -> dict[str, str]:
    if not payer_ids:
        return {}
    rows = (
        await session.scalars(
            select(InsurancePlan).where(InsurancePlan.payer_id.in_(payer_ids))
        )
    ).all()
    out: dict[str, str] = {}
    for ip in rows:
        out.setdefault(ip.payer_id, ip.carrier_name)
    return out


async def _patient_balance_map(
    session: AsyncSession, practice_id: uuid.UUID, patient_ids: set[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Map patient_id -> running ledger balance (sum of amount_cents). May be negative."""
    if not patient_ids:
        return {}
    rows = (
        await session.execute(
            select(LedgerEntry.patient_id, func.sum(LedgerEntry.amount_cents))
            .where(
                LedgerEntry.practice_id == practice_id,
                LedgerEntry.patient_id.in_(patient_ids),
                LedgerEntry.deleted_at.is_(None),
            )
            .group_by(LedgerEntry.patient_id)
        )
    ).all()
    return {pid: int(total) for pid, total in rows}


async def _reconciliation_mode(session: AsyncSession, practice_id: uuid.UUID) -> str:
    practice = await session.scalar(
        select(Practice).where(Practice.id == practice_id)
    )
    if practice is None:
        return "auto"
    config: dict[str, Any] = practice.automation_config or {}
    return str(config.get("era_reconciliation_mode", "auto"))


async def get_reconciliation_worklist(
    session: AsyncSession,
    practice_id: uuid.UUID,
    *,
    confirmed: bool | None = None,
    now: datetime | None = None,
) -> list[ReconciliationRow]:
    """Return ERA-settled claims eligible for reconciliation review.

    In auto mode only overpaid/within_tolerance/no_estimate claims are returned.
    In confirm mode matched (exact) claims are also returned.
    `confirmed` filters by whether reconciliation_confirmed_at is set.
    """
    now = now or datetime.now(UTC)
    mode = await _reconciliation_mode(session, practice_id)

    stmt = select(Claim).where(
        Claim.practice_id == practice_id,
        Claim.deleted_at.is_(None),
        Claim.insurance_paid_cents.isnot(None),
        Claim.status.notin_(["draft", "appealing", *_PROBLEM_STATUSES]),
    )
    if confirmed is True:
        stmt = stmt.where(Claim.reconciliation_confirmed_at.isnot(None))
    elif confirmed is False:
        stmt = stmt.where(Claim.reconciliation_confirmed_at.is_(None))

    claims = list((await session.scalars(stmt)).all())
    if not claims:
        return []

    estimates = await _estimate_map(session, {c.appointment_id for c in claims})
    patient_names = await _patient_name_map(session, {c.patient_id for c in claims})
    carrier_names = await _carrier_name_map(session, {c.payer_id for c in claims})
    balances = await _patient_balance_map(session, practice_id, {c.patient_id for c in claims})

    rows: list[ReconciliationRow] = []
    for c in claims:
        est = estimates.get(c.appointment_id)
        paid = int(c.insurance_paid_cents)  # type: ignore[arg-type]

        label = classify_for_reconciliation(paid, est)
        if label is None:
            continue
        if mode == "auto" and label == "matched":
            continue

        era_anchor = c.paid_at or c.submitted_at or c.created_at
        days_since = (now.date() - era_anchor.date()).days

        variance = None
        if est is not None:
            variance = paid - est

        rows.append(
            ReconciliationRow(
                claim_id=c.id,
                appointment_id=c.appointment_id,
                patient_id=c.patient_id,
                claim_number=c.patient_control_number,
                patient_name=patient_names.get(c.patient_id, "Unknown"),
                payer_id=c.payer_id,
                carrier_name=carrier_names.get(c.payer_id, c.payer_id),
                recon_label=label,
                billed_cents=int(c.total_charge_cents),
                estimated_insurance_cents=est,
                insurance_paid_cents=paid,
                variance_cents=variance,
                has_estimate=est is not None,
                patient_balance_cents=balances.get(c.patient_id, 0),
                days_since_era=days_since,
                reconciliation_confirmed_at=c.reconciliation_confirmed_at,
            )
        )

    rows.sort(key=lambda r: r.days_since_era, reverse=True)
    return rows


async def confirm_reconciliation(
    session: AsyncSession,
    practice_id: uuid.UUID,
    claim_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> Claim:
    """Set reconciliation_confirmed_at on a claim. Raises LookupError or ValueError."""
    claim = await session.scalar(
        select(Claim)
        .where(
            Claim.id == claim_id,
            Claim.practice_id == practice_id,
            Claim.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if claim is None:
        raise LookupError(f"claim {claim_id} not found for practice")
    if claim.reconciliation_confirmed_at is not None:
        raise ValueError("claim already confirmed")
    est = (await _estimate_map(session, {claim.appointment_id})).get(claim.appointment_id)
    paid = claim.insurance_paid_cents
    if paid is None:
        raise ValueError("claim has no ERA payment — not eligible for reconciliation")
    if classify_for_reconciliation(int(paid), est) is None:
        raise ValueError("claim is underpaid — use the insurance-ar accept action instead")
    if claim.status in _PROBLEM_STATUSES or claim.status == "appealing":
        raise ValueError("claim is in problem/appealing state — not eligible for reconciliation")

    claim.reconciliation_confirmed_at = now or datetime.now(UTC)
    await session.commit()
    await session.refresh(claim)
    return claim


async def get_ar_summary(
    session: AsyncSession,
    practice_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> ARSummaryData:
    """Practice-level A/R summary for the billing dashboard."""
    now = now or datetime.now(UTC)

    ar_rows = await _get_ar_worklist(session, practice_id, now=now)
    insurance_ar_total = sum(
        r.estimated_insurance_cents or 0 for r in ar_rows if r.category == "awaiting"
    ) + sum(
        r.shortfall_cents or 0 for r in ar_rows if r.category == "underpaid"
    )
    claims_needing_attention = sum(
        1 for r in ar_rows if r.category in ("problem", "appealing")
    )

    subq = (
        select(func.sum(LedgerEntry.amount_cents).label("balance"))
        .where(
            LedgerEntry.practice_id == practice_id,
            LedgerEntry.deleted_at.is_(None),
        )
        .group_by(LedgerEntry.patient_id)
        .having(func.sum(LedgerEntry.amount_cents) > 0)
        .subquery()
    )
    patient_ar_total = int(
        await session.scalar(select(func.coalesce(func.sum(subq.c.balance), 0))) or 0
    )

    pending_rows = await get_reconciliation_worklist(
        session, practice_id, confirmed=False, now=now
    )
    reconciliation_pending_count = len(pending_rows)

    mode = await _reconciliation_mode(session, practice_id)

    return ARSummaryData(
        insurance_ar_total_cents=insurance_ar_total,
        patient_ar_total_cents=patient_ar_total,
        claims_needing_attention=claims_needing_attention,
        reconciliation_pending_count=reconciliation_pending_count,
        era_reconciliation_mode=mode,  # type: ignore[arg-type]
    )
