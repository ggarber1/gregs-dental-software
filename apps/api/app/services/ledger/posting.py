from __future__ import annotations

import uuid
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment_procedure import AppointmentProcedure
from app.models.ledger_entry import LedgerEntry


class _LedgerAppointment(Protocol):
    id: uuid.UUID
    practice_id: uuid.UUID
    patient_id: uuid.UUID


class _LedgerClaim(Protocol):
    id: uuid.UUID
    practice_id: uuid.UUID
    patient_id: uuid.UUID
    insurance_paid_cents: int | None
    adjustments: list[dict[str, Any]] | None


async def record_patient_payment(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    *,
    amount_cents: int,
    payment_method: str,
    memo: str | None,
    posted_by: str,
) -> LedgerEntry:
    """Post a patient payment (stored as a negative entry). Amount must be > 0."""
    if amount_cents <= 0:
        raise ValueError("payment amount_cents must be positive")
    entry = LedgerEntry(
        id=uuid.uuid4(),
        practice_id=practice_id,
        patient_id=patient_id,
        entry_type="patient_payment",
        amount_cents=-amount_cents,
        payment_method=payment_method,
        memo=memo,
        posted_by=posted_by,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def add_manual_adjustment(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    *,
    amount_cents: int,
    memo: str,
    posted_by: str,
) -> LedgerEntry:
    """Post a manual adjustment. Sign is the caller's: negative = credit/write-off,
    positive = additional charge. `memo` (reason) is required."""
    if not memo or not memo.strip():
        raise ValueError("adjustment memo is required")
    if amount_cents == 0:
        raise ValueError("adjustment amount_cents must be non-zero")
    entry = LedgerEntry(
        id=uuid.uuid4(),
        practice_id=practice_id,
        patient_id=patient_id,
        entry_type="adjustment",
        amount_cents=amount_cents,
        memo=memo,
        posted_by=posted_by,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def _is_reversed(session: AsyncSession, entry_id: uuid.UUID) -> bool:
    found = await session.scalar(
        select(LedgerEntry.id).where(
            LedgerEntry.reverses_entry_id == entry_id,
            LedgerEntry.deleted_at.is_(None),
        )
    )
    return found is not None


async def reverse_entry(
    session: AsyncSession,
    practice_id: uuid.UUID,
    entry_id: uuid.UUID,
    *,
    posted_by: str,
    memo: str | None = None,
) -> LedgerEntry | None:
    """Post a mirror entry that cancels `entry_id`. Returns None if the entry is not
    found in this practice, is itself a reversal, or has already been reversed."""
    original = await session.scalar(
        select(LedgerEntry).where(
            LedgerEntry.id == entry_id,
            LedgerEntry.practice_id == practice_id,
            LedgerEntry.deleted_at.is_(None),
        )
    )
    if original is None or original.reverses_entry_id is not None:
        return None
    # Best-effort double-reverse guard (check-then-insert). Low-concurrency single-practice
    # app makes a race negligible for 8a; a partial unique index on reverses_entry_id is the
    # eventual DB-level backstop.
    if await _is_reversed(session, entry_id):
        return None
    reversal = LedgerEntry(
        id=uuid.uuid4(),
        practice_id=original.practice_id,
        patient_id=original.patient_id,
        guarantor_account_id=original.guarantor_account_id,
        entry_type=original.entry_type,
        amount_cents=-original.amount_cents,
        payment_method=original.payment_method,
        appointment_id=original.appointment_id,
        appointment_procedure_id=original.appointment_procedure_id,
        claim_id=original.claim_id,
        remittance_id=original.remittance_id,
        reverses_entry_id=original.id,
        memo=memo or f"reversal of {original.id}",
        posted_by=posted_by,
    )
    session.add(reversal)
    await session.commit()
    await session.refresh(reversal)
    return reversal


def _post_reversal_obj(original: LedgerEntry, posted_by: str) -> LedgerEntry:
    """Build (but do not add) a mirror entry for `original`."""
    return LedgerEntry(
        id=uuid.uuid4(),
        practice_id=original.practice_id,
        patient_id=original.patient_id,
        guarantor_account_id=original.guarantor_account_id,
        entry_type=original.entry_type,
        amount_cents=-original.amount_cents,
        appointment_id=original.appointment_id,
        appointment_procedure_id=original.appointment_procedure_id,
        claim_id=original.claim_id,
        remittance_id=original.remittance_id,
        reverses_entry_id=original.id,
        payment_method=original.payment_method,
        memo=f"auto reversal of {original.id}",
        posted_by=posted_by,
    )


async def _live_charges_by_proc(
    session: AsyncSession, appointment_id: uuid.UUID
) -> dict[uuid.UUID, LedgerEntry]:
    """Map appointment_procedure_id -> its live (un-reversed) charge entry."""
    reversed_ids = select(LedgerEntry.reverses_entry_id).where(
        LedgerEntry.reverses_entry_id.isnot(None),
        LedgerEntry.deleted_at.is_(None),
    )
    rows = (
        await session.scalars(
            select(LedgerEntry).where(
                LedgerEntry.appointment_id == appointment_id,
                LedgerEntry.entry_type == "charge",
                LedgerEntry.reverses_entry_id.is_(None),
                LedgerEntry.id.notin_(reversed_ids),
                LedgerEntry.deleted_at.is_(None),
            )
        )
    ).all()
    by_proc: dict[uuid.UUID, LedgerEntry] = {}
    for r in rows:
        if r.appointment_procedure_id is None:
            continue
        if r.appointment_procedure_id in by_proc:
            raise RuntimeError(
                f"invariant violation: two live charges for procedure {r.appointment_procedure_id}"
            )
        by_proc[r.appointment_procedure_id] = r
    return by_proc


async def reconcile_charges_for_appointment(
    session: AsyncSession, appointment: _LedgerAppointment, *, user_sub: str | None = None
) -> None:
    """Ensure exactly one live charge == fee_cents per live procedure of `appointment`.

    Idempotent. Posts reversing entries for stale/removed charges and new charges for
    new/changed procedures. `appointment` needs `.id`, `.practice_id`, `.patient_id`.
    """
    # Check-then-write is best-effort like reverse_entry (single-practice 8a); a future
    # partial unique index on appointment_procedure_id for live charges is the backstop.
    posted_by = user_sub or "system"
    procs = (
        await session.scalars(
            select(AppointmentProcedure).where(
                AppointmentProcedure.appointment_id == appointment.id,
                AppointmentProcedure.deleted_at.is_(None),
            )
        )
    ).all()
    proc_by_id = {p.id: p for p in procs}
    live = await _live_charges_by_proc(session, appointment.id)

    changed = False
    # Reverse charges whose procedure was deleted or whose fee changed.
    for proc_id, entry in live.items():
        proc = proc_by_id.get(proc_id)
        if proc is None or proc.fee_cents != entry.amount_cents:
            session.add(_post_reversal_obj(entry, posted_by))
            changed = True
    # Post charges for procedures lacking a matching live charge.
    for proc in procs:
        existing = live.get(proc.id)
        if existing is None or existing.amount_cents != proc.fee_cents:
            session.add(
                LedgerEntry(
                    id=uuid.uuid4(),
                    practice_id=appointment.practice_id,
                    patient_id=appointment.patient_id,
                    entry_type="charge",
                    amount_cents=proc.fee_cents,
                    appointment_id=appointment.id,
                    appointment_procedure_id=proc.id,
                    posted_by=posted_by,
                )
            )
            changed = True
    if changed:
        await session.commit()


async def _insurance_entry_exists(
    session: AsyncSession,
    claim_id: uuid.UUID,
    remittance_id: uuid.UUID,
    entry_type: str,
) -> bool:
    found = await session.scalar(
        select(LedgerEntry.id).where(
            LedgerEntry.claim_id == claim_id,
            LedgerEntry.remittance_id == remittance_id,
            LedgerEntry.entry_type == entry_type,
            LedgerEntry.reverses_entry_id.is_(None),
            LedgerEntry.deleted_at.is_(None),
        )
    )
    return found is not None


def _contractual_writeoff_cents(adjustments: list[dict[str, Any]] | None) -> int:
    """Sum of non-PR adjustment cents (contractual write-offs the provider absorbs).

    PR (patient responsibility) adjustments are what the patient owes and are NOT
    written off, so they are excluded.
    """
    if not adjustments:
        return 0
    return sum(int(a.get("cents", 0)) for a in adjustments if a.get("group") != "PR")


async def post_insurance_remittance(
    session: AsyncSession,
    claim: _LedgerClaim,
    remittance_id: uuid.UUID,
    *,
    user_sub: str | None = None,
) -> None:
    """Post insurance payment + contractual write-off entries for a matched claim.

    Reads the payment columns 7b set on the claim. Idempotent on
    (claim_id, remittance_id, entry_type). Only NON-PR adjustments are written off.
    """
    posted_by = user_sub or "system"
    paid = claim.insurance_paid_cents or 0
    if paid and not await _insurance_entry_exists(
        session, claim.id, remittance_id, "insurance_payment"
    ):
        session.add(
            LedgerEntry(
                id=uuid.uuid4(),
                practice_id=claim.practice_id,
                patient_id=claim.patient_id,
                entry_type="insurance_payment",
                amount_cents=-paid,
                claim_id=claim.id,
                remittance_id=remittance_id,
                posted_by=posted_by,
            )
        )

    writeoff = _contractual_writeoff_cents(claim.adjustments)
    if writeoff and not await _insurance_entry_exists(
        session, claim.id, remittance_id, "adjustment"
    ):
        session.add(
            LedgerEntry(
                id=uuid.uuid4(),
                practice_id=claim.practice_id,
                patient_id=claim.patient_id,
                entry_type="adjustment",
                amount_cents=-writeoff,
                claim_id=claim.id,
                remittance_id=remittance_id,
                memo="contractual adjustment",
                posted_by=posted_by,
            )
        )
    await session.commit()
