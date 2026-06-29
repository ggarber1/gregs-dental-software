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
from app.models.patient import Patient

_PROBLEM_STATUSES = frozenset({"denied", "clearinghouse_rejected", "submission_failed"})
_UNDERPAY_PCT = 95  # flag underpayment when insurance pays < 95% of the Module 6 estimate


def age_bucket(days_out: int) -> Literal["0-30", "31-60", "61-90", "90+"]:
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
    # Integer-cents comparison (no float): paid < 95% of estimate.
    return 100 * insurance_paid_cents < _UNDERPAY_PCT * estimated_insurance_cents


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


_BUCKET_FIELD = {"0-30": "b0_30", "31-60": "b31_60", "61-90": "b61_90", "90+": "b90_plus"}


@dataclass(frozen=True, kw_only=True)
class WorklistRow:
    claim_id: uuid.UUID
    claim_number: str
    patient_name: str
    payer_id: str
    carrier_name: str
    category: str
    billed_cents: int
    estimated_insurance_cents: int | None
    insurance_paid_cents: int | None
    shortfall_cents: int | None
    has_estimate: bool
    days_out: int
    bucket: Literal["0-30", "31-60", "61-90", "90+"]
    status: str
    reason: str | None


@dataclass
class Buckets:
    b0_30: int = 0
    b31_60: int = 0
    b61_90: int = 0
    b90_plus: int = 0


@dataclass
class CarrierSummary:
    payer_id: str
    carrier_name: str
    claim_count: int
    buckets: Buckets
    total_billed_cents: int
    expected_cents: int
    unestimated_count: int
    underpaid_count: int
    problem_count: int


@dataclass
class ARTotals:
    claim_count: int
    buckets: Buckets
    total_billed_cents: int
    expected_cents: int
    unestimated_count: int
    underpaid_count: int
    problem_count: int


@dataclass
class Summary:
    carriers: list[CarrierSummary]
    totals: ARTotals


def summarize(rows: list[WorklistRow]) -> Summary:
    """Aggregate worklist rows into the carrier birds-eye + TOTAL row. Pure.

    Only AWAITING rows contribute to billed buckets / total_billed / expected;
    underpaid and problem rows are counted separately per carrier.
    Appealing rows contribute only to claim_count (there is no appealing_count
    on the summary by design), so they appear in totals without their own column.
    """
    by_payer: dict[str, CarrierSummary] = {}
    order: list[str] = []
    for r in rows:
        cs = by_payer.get(r.payer_id)
        if cs is None:
            cs = CarrierSummary(
                payer_id=r.payer_id,
                carrier_name=r.carrier_name,
                claim_count=0,
                buckets=Buckets(),
                total_billed_cents=0,
                expected_cents=0,
                unestimated_count=0,
                underpaid_count=0,
                problem_count=0,
            )
            by_payer[r.payer_id] = cs
            order.append(r.payer_id)
        cs.claim_count += 1
        if r.category == "underpaid":
            cs.underpaid_count += 1
        elif r.category == "problem":
            cs.problem_count += 1
        elif r.category == "awaiting":
            setattr(
                cs.buckets,
                _BUCKET_FIELD[r.bucket],
                getattr(cs.buckets, _BUCKET_FIELD[r.bucket]) + r.billed_cents,
            )
            cs.total_billed_cents += r.billed_cents
            if r.has_estimate and r.estimated_insurance_cents is not None:
                cs.expected_cents += r.estimated_insurance_cents
            else:
                cs.unestimated_count += 1

    carriers = [by_payer[p] for p in order]
    totals = ARTotals(
        claim_count=sum(c.claim_count for c in carriers),
        buckets=Buckets(
            b0_30=sum(c.buckets.b0_30 for c in carriers),
            b31_60=sum(c.buckets.b31_60 for c in carriers),
            b61_90=sum(c.buckets.b61_90 for c in carriers),
            b90_plus=sum(c.buckets.b90_plus for c in carriers),
        ),
        total_billed_cents=sum(c.total_billed_cents for c in carriers),
        expected_cents=sum(c.expected_cents for c in carriers),
        unestimated_count=sum(c.unestimated_count for c in carriers),
        underpaid_count=sum(c.underpaid_count for c in carriers),
        problem_count=sum(c.problem_count for c in carriers),
    )
    return Summary(carriers=carriers, totals=totals)


# ---------------------------------------------------------------------------
# DB layer
# ---------------------------------------------------------------------------


def _days_between(anchor: datetime, now: datetime) -> int:
    return (now.date() - anchor.date()).days


async def _estimate_map(
    session: AsyncSession, appt_ids: set[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """appointment_id -> estimated insurance cents.

    Uses the latest copay_calculations row per appointment, falling back to
    the sum of appointment_procedures.insurance_est_cents.
    """
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
        if c.appointment_id not in out:  # first per appt = latest (desc order)
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
    # Project only id + name columns — avoids loading full PHI rows (SSN, address,
    # clinical flags). first_name/last_name are plaintext String columns
    # (only ssn_encrypted is column-encrypted), so projection returns real names.
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


async def get_worklist(
    session: AsyncSession,
    practice_id: uuid.UUID,
    *,
    category: str | None = None,
    payer_id: str | None = None,
    bucket: str | None = None,
    status: str | None = None,
    sort: Literal["oldest", "newest"] = "oldest",
    now: datetime | None = None,
) -> list[WorklistRow]:
    now = now or datetime.now(UTC)
    stmt = select(Claim).where(
        Claim.practice_id == practice_id,
        Claim.deleted_at.is_(None),
        Claim.status != "draft",
    )
    if payer_id:
        stmt = stmt.where(Claim.payer_id == payer_id)
    if status:
        stmt = stmt.where(Claim.status == status)
    claims = list((await session.scalars(stmt)).all())
    if not claims:
        return []

    estimates = await _estimate_map(session, {c.appointment_id for c in claims})
    patient_names = await _patient_name_map(session, {c.patient_id for c in claims})
    carrier_names = await _carrier_name_map(session, {c.payer_id for c in claims})

    rows: list[WorklistRow] = []
    for c in claims:
        est = estimates.get(c.appointment_id)
        cat = classify(
            status=c.status,
            insurance_paid_cents=c.insurance_paid_cents,
            estimated_insurance_cents=est,
            insurance_reviewed_at=c.insurance_reviewed_at,
        )
        if cat is None:
            continue
        anchor = c.submitted_at or c.created_at
        days = _days_between(anchor, now)
        shortfall = (
            int(est) - int(c.insurance_paid_cents)
            if cat == "underpaid" and est is not None and c.insurance_paid_cents is not None
            else None
        )
        rows.append(
            WorklistRow(
                claim_id=c.id,
                claim_number=c.patient_control_number,
                patient_name=patient_names.get(c.patient_id, "Unknown"),
                payer_id=c.payer_id,
                carrier_name=carrier_names.get(c.payer_id, c.payer_id),
                category=cat,
                billed_cents=int(c.total_charge_cents),
                estimated_insurance_cents=est,
                insurance_paid_cents=c.insurance_paid_cents,
                shortfall_cents=shortfall,
                has_estimate=est is not None,
                days_out=days,
                bucket=age_bucket(days),
                status=c.status,
                reason=reason_for(c),
            )
        )

    # category/bucket are derived (computed in Python from classify/age_bucket),
    # so they can't be pushed into the SQL WHERE — filter post-hoc. Fine at
    # per-practice claim volumes.
    if category:
        rows = [r for r in rows if r.category == category]
    if bucket:
        rows = [r for r in rows if r.bucket == bucket]
    rows.sort(key=lambda r: r.days_out, reverse=(sort == "oldest"))
    return rows


async def get_summary(
    session: AsyncSession,
    practice_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> Summary:
    rows = await get_worklist(session, practice_id, now=now)
    return summarize(rows)


async def _load_claim(
    session: AsyncSession, practice_id: uuid.UUID, claim_id: uuid.UUID
) -> Claim:
    # Row lock: accept/appeal do load -> check -> mutate -> commit. Without the
    # lock, a concurrent accept + appeal could both pass the underpaid check and
    # set insurance_reviewed_at AND status='appealing'. with_for_update serializes them.
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
    return claim


async def _is_underpaid_claim(session: AsyncSession, claim: Claim) -> bool:
    est = (await _estimate_map(session, {claim.appointment_id})).get(claim.appointment_id)
    return (
        classify(
            status=claim.status,
            insurance_paid_cents=claim.insurance_paid_cents,
            estimated_insurance_cents=est,
            insurance_reviewed_at=claim.insurance_reviewed_at,
        )
        == "underpaid"
    )


async def accept_underpayment(
    session: AsyncSession,
    practice_id: uuid.UUID,
    claim_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> Claim:
    """Mark an underpaid claim reviewed/accepted (drops it from the worklist)."""
    claim = await _load_claim(session, practice_id, claim_id)
    if not await _is_underpaid_claim(session, claim):
        raise ValueError("claim is not currently underpaid")
    claim.insurance_reviewed_at = now or datetime.now(UTC)
    await session.commit()
    await session.refresh(claim)
    return claim


async def flag_for_appeal(
    session: AsyncSession,
    practice_id: uuid.UUID,
    claim_id: uuid.UUID,
) -> Claim:
    """Triage flag only — sets status='appealing'. Does NOT submit to the carrier."""
    claim = await _load_claim(session, practice_id, claim_id)
    if not await _is_underpaid_claim(session, claim):
        raise ValueError("claim is not currently underpaid")
    claim.status = "appealing"
    await session.commit()
    await session.refresh(claim)
    return claim
