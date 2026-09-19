"""Statement rendering: pure HTML render is fully tested; WeasyPrint is optional."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.reports.insurance_ar import Buckets
from app.services.reports.patient_aging import AgingBreakdown, bucket_ledger_entries
from app.services.statements.pdf import (
    StatementContext,
    build_context,
    render_statement_html,
    usd,
)

_NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def _practice(**overrides):
    base = dict(
        name="Sunrise Dental",
        address_line1="1 Main St",
        address_line2=None,
        city="Boston",
        state="MA",
        zip="02110",
        phone="+16175550100",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _patient(**overrides):
    base = dict(
        id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        first_name="Jane",
        last_name="Smith",
        address_line1="9 Elm Rd",
        address_line2="Apt 2",
        city="Cambridge",
        state="MA",
        zip="02139",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _entry(entry_type: str, amount: int, days_ago: int, memo: str | None = None, method=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        entry_type=entry_type,
        amount_cents=amount,
        posted_at=_NOW - timedelta(days=days_ago),
        memo=memo,
        payment_method=method,
        reverses_entry_id=None,
    )


def test_usd_formats_cents_with_grouping_and_sign():
    assert usd(0) == "$0.00"
    assert usd(5) == "$0.05"
    assert usd(123456) == "$1,234.56"
    assert usd(-250) == "-$2.50"


def test_build_context_lines_and_running_balance():
    entries = [
        _entry("charge", 10000, days_ago=100, memo="D1110 Prophylaxis"),
        _entry("insurance_payment", -6000, days_ago=50),
        _entry("patient_payment", -1000, days_ago=2, method="card"),
    ]
    aging = bucket_ledger_entries(entries, now=_NOW)

    ctx = build_context(_practice(), _patient(), entries, aging, statement_date=date(2026, 9, 18))

    assert isinstance(ctx, StatementContext)
    assert ctx.practice_name == "Sunrise Dental"
    assert ctx.practice_address_lines == ["1 Main St", "Boston, MA 02110"]
    assert ctx.patient_name == "Jane Smith"
    assert ctx.patient_address_lines == ["9 Elm Rd", "Apt 2", "Cambridge, MA 02139"]
    assert ctx.account_number == "12345678"
    assert [line.description for line in ctx.lines] == [
        "Charge — D1110 Prophylaxis",
        "Insurance payment",
        "Patient payment (Card)",
    ]
    assert [line.charge_cents for line in ctx.lines] == [10000, None, None]
    assert [line.credit_cents for line in ctx.lines] == [None, 6000, 1000]
    assert [line.running_balance_cents for line in ctx.lines] == [10000, 4000, 3000]
    assert ctx.aging.balance_cents == 3000


def test_build_context_handles_missing_addresses():
    ctx = build_context(
        _practice(address_line1=None, city=None, state=None, zip=None, phone=None),
        _patient(address_line1=None, address_line2=None, city=None, state=None, zip=None),
        [],
        AgingBreakdown.empty(),
        statement_date=date(2026, 9, 18),
    )
    assert ctx.practice_address_lines == []
    assert ctx.patient_address_lines == []
    assert ctx.practice_phone is None


def test_render_html_contains_key_content():
    entries = [
        _entry("charge", 12345, days_ago=45, memo="D0120 Exam"),
        _entry("patient_payment", -2000, days_ago=1, method="cash"),
    ]
    aging = bucket_ledger_entries(entries, now=_NOW)
    ctx = build_context(_practice(), _patient(), entries, aging, statement_date=date(2026, 9, 18))

    html = render_statement_html(ctx)

    assert "Sunrise Dental" in html
    assert "Jane Smith" in html
    assert "D0120 Exam" in html
    assert "$123.45" in html  # the 31-60 bucket
    assert "$103.45" in html  # amount due
    assert "$20.00" in html  # payments & credits shown as a positive figure
    assert "-$20.00" not in html
    assert "September 18, 2026" in html
    assert "+16175550100" in html
    assert "Thank you for choosing Sunrise Dental" in html
    assert "pay_url" not in html  # the Jinja comment placeholder must not leak


def test_render_html_escapes_user_content():
    entries = [_entry("charge", 100, days_ago=1, memo="<script>alert(1)</script>")]
    aging = bucket_ledger_entries(entries, now=_NOW)
    ctx = build_context(
        _practice(name="Evil & Co"), _patient(), entries, aging, statement_date=date(2026, 9, 18)
    )

    html = render_statement_html(ctx)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "Evil &amp; Co" in html


def test_html_to_pdf_produces_a_pdf_when_weasyprint_is_available():
    # Pango missing raises OSError from dlopen, not ImportError.
    pytest.importorskip("weasyprint", exc_type=OSError)
    from app.services.statements.pdf import html_to_pdf

    ctx = build_context(
        _practice(),
        _patient(),
        [],
        AgingBreakdown(buckets=Buckets(b0_30=100), balance_cents=100),
        statement_date=date(2026, 9, 18),
    )
    pdf = html_to_pdf(render_statement_html(ctx))
    assert pdf.startswith(b"%PDF-")
