from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry


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
    if await _is_reversed(session, entry_id):
        return None
    reversal = LedgerEntry(
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
        memo=memo or f"reversal of {original.id}",
        posted_by=posted_by,
    )
    session.add(reversal)
    await session.commit()
    await session.refresh(reversal)
    return reversal
