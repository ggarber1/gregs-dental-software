"""Patient A/R aging (Module 8b).

Charges are bucketed by the age of their posted_at date; payments and adjustments
are not attributed to a bucket and are reported as one signed credits total. This
is the standard small-practice statement layout and avoids FIFO attribution.

`bucket_ledger_entries` is pure and shared by the worklist endpoint and the PDF.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from app.services.reports.insurance_ar import Buckets, age_bucket

DEFAULT_MIN_BALANCE_CENTS = 500

SortBy = Literal["balance", "oldest_charge", "last_statement"]


class _EntryLike(Protocol):
    """The three LedgerEntry attributes aging reads. Lets tests pass plain objects."""

    entry_type: str
    amount_cents: int
    posted_at: datetime


@dataclass(frozen=True)
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


def _days_between(anchor: datetime, now: datetime) -> int:
    return (now.date() - anchor.date()).days


def bucket_ledger_entries(entries: Sequence[_EntryLike], *, now: datetime) -> AgingBreakdown:
    """Pure. Entries should already exclude reversal pairs (see
    `ledger.balance.unreversed_entry_where`)."""
    buckets = Buckets()
    credits = 0
    oldest: datetime | None = None
    for e in entries:
        if e.entry_type != "charge":
            credits += e.amount_cents
            continue
        bucket = age_bucket(_days_between(e.posted_at, now))
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
