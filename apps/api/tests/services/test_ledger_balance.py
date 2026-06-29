import uuid
from types import SimpleNamespace

from app.services.ledger.balance import annotate_running_balance


def _entry(amount: int):
    return SimpleNamespace(id=uuid.uuid4(), amount_cents=amount)


def test_running_balance_accumulates_in_order():
    entries = [_entry(25000), _entry(-20000), _entry(-3000), _entry(-2000)]
    annotated = annotate_running_balance(entries)
    assert [rb for _, rb in annotated] == [25000, 5000, 2000, 0]


def test_running_balance_allows_credit():
    entries = [_entry(5000), _entry(-8000)]
    annotated = annotate_running_balance(entries)
    assert annotated[-1][1] == -3000  # patient overpaid -> credit balance
