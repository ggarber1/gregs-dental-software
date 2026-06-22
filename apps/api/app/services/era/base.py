from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, kw_only=True)
class ClaimAdjustment:
    group: str          # CO | PR | OA | PI  (CAS group code)
    code: str           # CARC reason code (e.g. "45", "2")
    cents: int          # adjustment amount in cents


@dataclass(frozen=True, kw_only=True)
class ClaimPayment:
    patient_control_number: str          # CLP01 — matches claims.patient_control_number
    claim_status_code: str               # CLP02 — 1/2/3/19/20/21 processed, 4 denied, 22 reversal
    total_charge_cents: int              # CLP03
    paid_cents: int                      # CLP04
    patient_responsibility_cents: int    # CLP05
    payer_claim_control_number: str | None  # CLP07
    adjustments: tuple[ClaimAdjustment, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)  # the raw claim-payment JSON object


@dataclass(frozen=True, kw_only=True)
class ERAPayment:
    payer_name: str | None
    trace_number: str | None
    payment_cents: int | None
    payment_date: date | None
    claim_payments: tuple[ClaimPayment, ...]
    raw: dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class Transaction:
    transaction_id: str
    processed_at: datetime | None = None


class ERAFetchError(Exception):
    """Raised by a RemittanceClient on a transport/server failure.

    `retryable` -> timeout/5xx/transport: the poll can be safely re-run later
    (ingest is idempotent on the Stedi transaction id).
    """

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class RemittanceClient(ABC):
    @abstractmethod
    async def poll_transactions(self, since: datetime) -> list[Transaction]:
        """Return processed 835 transactions since `since` (filtered to ERAs)."""

    @abstractmethod
    async def fetch_era(self, transaction_id: str) -> dict[str, Any]:
        """Return the raw Stedi 835 ERA JSON for one transaction."""
