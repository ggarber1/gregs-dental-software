"""Patient A/R aging (Module 8b).

Positive-amount entries (charges and positive adjustments) are bucketed by the age
of their posted_at date; payments and negative adjustments are not attributed to a
bucket and are reported as one signed credits total. This is the standard
small-practice statement layout and avoids FIFO attribution.

`bucket_ledger_entries` is pure and shared by the worklist endpoint and the PDF.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry
from app.models.patient import Patient
from app.models.patient_statement import PatientStatement
from app.services.ledger.balance import get_unreversed_entries, unreversed_entry_where
from app.services.reports.insurance_ar import Buckets, age_bucket, days_between

DEFAULT_MIN_BALANCE_CENTS = 500

SortBy = Literal["balance", "oldest_charge", "last_statement"]


class _EntryLike(Protocol):
    """The three LedgerEntry attributes aging reads. Lets tests pass plain objects."""

    entry_type: str
    amount_cents: int
    posted_at: datetime


@dataclass
class AgingBreakdown:
    buckets: Buckets = field(default_factory=Buckets)
    credits_cents: int = 0
    balance_cents: int = 0
    oldest_charge_at: datetime | None = None

    @classmethod
    def empty(cls) -> AgingBreakdown:
        return cls()

    def snapshot(self) -> dict[str, int]:
        """Bucket totals keyed like ARBuckets — stored on patient_statements."""
        b = self.buckets
        return {"b0_30": b.b0_30, "b31_60": b.b31_60, "b61_90": b.b61_90, "b90_plus": b.b90_plus}


def bucket_ledger_entries(entries: Sequence[_EntryLike], *, now: datetime) -> AgingBreakdown:
    """Pure. Positive-amount entries (charges and positive adjustments) are bucketed
    by age; payments and negative adjustments are credits. Entries should already
    exclude reversal pairs (see `ledger.balance.unreversed_entry_where`)."""
    buckets = Buckets()
    credits = 0
    oldest: datetime | None = None
    for e in entries:
        if e.amount_cents <= 0:
            credits += e.amount_cents
            continue
        bucket = age_bucket(days_between(e.posted_at, now))
        if bucket == "0-30":
            buckets.b0_30 += e.amount_cents
        elif bucket == "31-60":
            buckets.b31_60 += e.amount_cents
        elif bucket == "61-90":
            buckets.b61_90 += e.amount_cents
        else:
            buckets.b90_plus += e.amount_cents
        if oldest is None or e.posted_at < oldest:
            oldest = e.posted_at
    charges = buckets.b0_30 + buckets.b31_60 + buckets.b61_90 + buckets.b90_plus
    return AgingBreakdown(
        buckets=buckets,
        credits_cents=credits,
        balance_cents=charges + credits,
        oldest_charge_at=oldest,
    )


@dataclass(frozen=True, kw_only=True)
class PatientAgingRow:
    patient_id: uuid.UUID
    patient_name: str
    email: str | None
    aging: AgingBreakdown
    last_statement_at: datetime | None
    last_statement_method: str | None


async def _patient_contact_map(
    session: AsyncSession, practice_id: uuid.UUID, patient_ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, str | None]]:
    """patient_id -> (display name, email) for live patients in this practice.

    Projects only the columns needed — avoids loading full PHI rows.
    """
    rows = (
        await session.execute(
            select(Patient.id, Patient.first_name, Patient.last_name, Patient.email).where(
                Patient.id.in_(patient_ids),
                Patient.practice_id == practice_id,
                Patient.deleted_at.is_(None),
            )
        )
    ).all()
    return {pid: (f"{first} {last}", email) for pid, first, last, email in rows}


async def _last_statement_map(
    session: AsyncSession, practice_id: uuid.UUID, patient_ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[datetime, str]]:
    """patient_id -> (generated_at, delivery_method) of the most recent statement."""
    rows = (
        await session.execute(
            select(
                PatientStatement.patient_id,
                PatientStatement.generated_at,
                PatientStatement.delivery_method,
            )
            .where(
                PatientStatement.practice_id == practice_id,
                PatientStatement.patient_id.in_(patient_ids),
                PatientStatement.deleted_at.is_(None),
            )
            # Both DESC: DISTINCT ON only needs patient_id grouped, and a single
            # backward scan of (practice_id, patient_id, generated_at) satisfies it.
            .order_by(PatientStatement.patient_id.desc(), PatientStatement.generated_at.desc())
            .distinct(PatientStatement.patient_id)
        )
    ).all()
    return {pid: (generated_at, method) for pid, generated_at, method in rows}


_SortKey = Callable[["PatientAgingRow"], tuple[int, float, str, str]]


def _sort_key(sort_by: SortBy) -> _SortKey:
    """Deterministic ordering: every mode breaks ties on (patient_name, patient_id)."""
    if sort_by == "oldest_charge":
        # Oldest debt first; rows with no charge (all-credit) last.
        return lambda r: (
            (0, r.aging.oldest_charge_at.timestamp(), r.patient_name, str(r.patient_id))
            if r.aging.oldest_charge_at
            else (1, 0.0, r.patient_name, str(r.patient_id))
        )
    if sort_by == "last_statement":
        # Never-billed first, then the longest since last statement.
        return lambda r: (
            (1, r.last_statement_at.timestamp(), r.patient_name, str(r.patient_id))
            if r.last_statement_at
            else (0, 0.0, r.patient_name, str(r.patient_id))
        )
    return lambda r: (0, -float(r.aging.balance_cents), r.patient_name, str(r.patient_id))


async def get_patient_aging_worklist(
    session: AsyncSession,
    practice_id: uuid.UUID,
    *,
    min_balance_cents: int = DEFAULT_MIN_BALANCE_CENTS,
    sort_by: SortBy = "balance",
    now: datetime | None = None,
) -> list[PatientAgingRow]:
    """Every live patient owing at least `min_balance_cents`, with aging breakdown
    and last-statement metadata. Patients with a zero or credit balance never appear."""
    now = now or datetime.now(UTC)
    threshold = max(min_balance_cents, 1)

    balance_rows = (
        await session.execute(
            select(LedgerEntry.patient_id, func.sum(LedgerEntry.amount_cents))
            .where(LedgerEntry.practice_id == practice_id, *unreversed_entry_where())
            .group_by(LedgerEntry.patient_id)
            .having(func.sum(LedgerEntry.amount_cents) >= threshold)
        )
    ).all()
    patient_ids = {pid for pid, _ in balance_rows}
    if not patient_ids:
        return []

    contacts = await _patient_contact_map(session, practice_id, patient_ids)
    patient_ids = {pid for pid in patient_ids if pid in contacts}
    if not patient_ids:
        return []

    by_patient: dict[uuid.UUID, list[LedgerEntry]] = defaultdict(list)
    for entry in await get_unreversed_entries(session, practice_id, patient_ids):
        by_patient[entry.patient_id].append(entry)
    last = await _last_statement_map(session, practice_id, patient_ids)

    rows: list[PatientAgingRow] = []
    for pid in patient_ids:
        name, email = contacts[pid]
        stmt = last.get(pid)
        rows.append(
            PatientAgingRow(
                patient_id=pid,
                patient_name=name,
                email=email,
                aging=bucket_ledger_entries(by_patient[pid], now=now),
                last_statement_at=stmt[0] if stmt else None,
                last_statement_method=stmt[1] if stmt else None,
            )
        )
    rows.sort(key=_sort_key(sort_by))
    return rows
