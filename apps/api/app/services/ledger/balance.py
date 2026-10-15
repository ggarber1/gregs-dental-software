from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry


def annotate_running_balance(
    entries: Sequence[LedgerEntry],
) -> list[tuple[LedgerEntry, int]]:
    """Pair each entry with the running balance after it. Entries must already be
    ordered oldest-first. Pure — no DB access."""
    running = 0
    out: list[tuple[LedgerEntry, int]] = []
    for entry in entries:
        running += entry.amount_cents
        out.append((entry, running))
    return out


async def _live_entries(
    session: AsyncSession, practice_id: uuid.UUID, patient_id: uuid.UUID
) -> list[LedgerEntry]:
    rows = (
        await session.scalars(
            select(LedgerEntry)
            .where(
                LedgerEntry.practice_id == practice_id,
                LedgerEntry.patient_id == patient_id,
                LedgerEntry.deleted_at.is_(None),
            )
            .order_by(LedgerEntry.posted_at, LedgerEntry.id)
        )
    ).all()
    return list(rows)


async def get_patient_balance(
    session: AsyncSession, practice_id: uuid.UUID, patient_id: uuid.UUID
) -> int:
    """SUM(amount_cents). Positive = patient owes; negative = credit balance."""
    total = await session.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(
            LedgerEntry.practice_id == practice_id,
            LedgerEntry.patient_id == patient_id,
            LedgerEntry.deleted_at.is_(None),
        )
    )
    return int(total or 0)


async def get_ledger(
    session: AsyncSession, practice_id: uuid.UUID, patient_id: uuid.UUID
) -> tuple[list[tuple[LedgerEntry, int]], int]:
    """Return (entries-with-running-balance oldest-first, current balance)."""
    entries = await _live_entries(session, practice_id, patient_id)
    annotated = annotate_running_balance(entries)
    balance = annotated[-1][1] if annotated else 0
    return annotated, balance


def unreversed_entry_where() -> list[ColumnElement[bool]]:
    """WHERE clauses selecting live entries that are neither a reversal nor reversed.

    A reversal pair (original + mirror) nets to zero, so excluding both sides leaves
    balances unchanged while keeping stale charges out of age buckets and statements.
    """
    reversed_ids = select(LedgerEntry.reverses_entry_id).where(
        LedgerEntry.reverses_entry_id.isnot(None),
        LedgerEntry.deleted_at.is_(None),
    )
    return [
        LedgerEntry.deleted_at.is_(None),
        LedgerEntry.reverses_entry_id.is_(None),
        LedgerEntry.id.notin_(reversed_ids),
    ]


async def get_unreversed_entries(
    session: AsyncSession, practice_id: uuid.UUID, patient_ids: Iterable[uuid.UUID]
) -> list[LedgerEntry]:
    """Live, un-reversed entries for the given patients, oldest-first."""
    ids = list(patient_ids)
    if not ids:
        return []
    rows = (
        await session.scalars(
            select(LedgerEntry)
            .where(
                LedgerEntry.practice_id == practice_id,
                LedgerEntry.patient_id.in_(ids),
                *unreversed_entry_where(),
            )
            .order_by(LedgerEntry.posted_at, LedgerEntry.id)
        )
    ).all()
    return list(rows)
