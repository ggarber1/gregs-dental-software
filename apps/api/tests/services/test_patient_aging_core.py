"""Pure-function tests for patient aging buckets. No DB."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.reports.patient_aging import AgingBreakdown, bucket_ledger_entries

_NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def _entry(entry_type: str, amount: int, days_ago: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        entry_type=entry_type,
        amount_cents=amount,
        posted_at=_NOW - timedelta(days=days_ago),
    )


def test_charges_land_in_the_bucket_for_their_age():
    entries = [
        _entry("charge", 5000, days_ago=0),
        _entry("charge", 4000, days_ago=45),
        _entry("charge", 3000, days_ago=75),
        _entry("charge", 2000, days_ago=120),
    ]
    aging = bucket_ledger_entries(entries, now=_NOW)
    assert aging.buckets.b0_30 == 5000
    assert aging.buckets.b31_60 == 4000
    assert aging.buckets.b61_90 == 3000
    assert aging.buckets.b90_plus == 2000
    assert aging.credits_cents == 0
    assert aging.balance_cents == 14000


def test_bucket_boundaries_are_inclusive_at_30_60_90():
    entries = [
        _entry("charge", 1, days_ago=30),
        _entry("charge", 10, days_ago=31),
        _entry("charge", 100, days_ago=60),
        _entry("charge", 1000, days_ago=61),
        _entry("charge", 10000, days_ago=90),
        _entry("charge", 100000, days_ago=91),
    ]
    aging = bucket_ledger_entries(entries, now=_NOW)
    assert aging.buckets.b0_30 == 1
    assert aging.buckets.b31_60 == 110
    assert aging.buckets.b61_90 == 11000
    assert aging.buckets.b90_plus == 100000


def test_payments_and_adjustments_are_credits_not_bucketed():
    entries = [
        _entry("charge", 10000, days_ago=100),
        _entry("insurance_payment", -6000, days_ago=50),
        _entry("patient_payment", -1000, days_ago=2),
        _entry("adjustment", -500, days_ago=1),
    ]
    aging = bucket_ledger_entries(entries, now=_NOW)
    assert aging.buckets.b90_plus == 10000
    assert aging.buckets.b0_30 == 0
    assert aging.credits_cents == -7500
    assert aging.balance_cents == 2500


def test_all_same_day_is_all_current():
    entries = [_entry("charge", 100, days_ago=0), _entry("charge", 200, days_ago=0)]
    aging = bucket_ledger_entries(entries, now=_NOW)
    assert aging.buckets.b0_30 == 300
    assert aging.buckets.b31_60 == 0
    assert aging.buckets.b61_90 == 0
    assert aging.buckets.b90_plus == 0


def test_oldest_charge_at_ignores_credits():
    entries = [
        _entry("patient_payment", -100, days_ago=200),
        _entry("charge", 100, days_ago=40),
        _entry("charge", 100, days_ago=10),
    ]
    aging = bucket_ledger_entries(entries, now=_NOW)
    assert aging.oldest_charge_at == _NOW - timedelta(days=40)


def test_empty_ledger_is_zero_everywhere():
    aging = bucket_ledger_entries([], now=_NOW)
    assert aging == AgingBreakdown.empty()


def test_credit_balance_is_negative():
    entries = [_entry("charge", 100, days_ago=1), _entry("patient_payment", -300, days_ago=0)]
    aging = bucket_ledger_entries(entries, now=_NOW)
    assert aging.balance_cents == -200
