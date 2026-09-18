"""Statement rendering: ledger → template context → HTML → PDF.

`build_context` and `render_statement_html` are pure. `html_to_pdf` imports
WeasyPrint lazily because it needs native Pango/HarfBuzz libraries that are not
present on every dev machine or the CI runner.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.reports.patient_aging import AgingBreakdown

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_ENTRY_TYPE_LABEL = {
    "charge": "Charge",
    "insurance_payment": "Insurance payment",
    "patient_payment": "Patient payment",
    "adjustment": "Adjustment",
}
_PAYMENT_METHOD_LABEL = {
    "cash": "Cash",
    "check": "Check",
    "card": "Card",
    "external_terminal": "External terminal",
    "other": "Other",
}


class _PracticeLike(Protocol):
    name: str
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    zip: str | None
    phone: str | None


class _PatientLike(Protocol):
    id: object
    first_name: str
    last_name: str
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    zip: str | None


class _EntryLike(Protocol):
    entry_type: str
    amount_cents: int
    posted_at: datetime
    memo: str | None
    payment_method: str | None


@dataclass(frozen=True)
class StatementLine:
    posted_on: date
    description: str
    charge_cents: int | None
    credit_cents: int | None
    running_balance_cents: int


@dataclass(frozen=True)
class StatementContext:
    practice_name: str
    practice_address_lines: list[str]
    practice_phone: str | None
    patient_name: str
    patient_address_lines: list[str]
    account_number: str
    statement_date: date
    aging: AgingBreakdown
    lines: list[StatementLine]


def usd(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


def _address_lines(
    line1: str | None, line2: str | None, city: str | None, state: str | None, zip_: str | None
) -> list[str]:
    lines = [line for line in (line1, line2) if line]
    city_state = ", ".join(part for part in (city, state) if part)
    last = " ".join(part for part in (city_state, zip_) if part)
    if last:
        lines.append(last)
    return lines


def _describe(entry: _EntryLike) -> str:
    parts = [_ENTRY_TYPE_LABEL.get(entry.entry_type, entry.entry_type)]
    if entry.entry_type == "patient_payment" and entry.payment_method:
        label = _PAYMENT_METHOD_LABEL.get(entry.payment_method, entry.payment_method)
        parts.append(f"({label})")
    if entry.memo:
        parts.append(f"— {entry.memo}")
    return " ".join(parts)


def build_context(
    practice: _PracticeLike,
    patient: _PatientLike,
    entries: Sequence[_EntryLike],
    aging: AgingBreakdown,
    *,
    statement_date: date,
) -> StatementContext:
    """Pure. `entries` must be oldest-first and already exclude reversal pairs."""
    lines: list[StatementLine] = []
    running = 0
    for entry in entries:
        running += entry.amount_cents
        lines.append(
            StatementLine(
                posted_on=entry.posted_at.date(),
                description=_describe(entry),
                charge_cents=entry.amount_cents if entry.amount_cents > 0 else None,
                credit_cents=-entry.amount_cents if entry.amount_cents < 0 else None,
                running_balance_cents=running,
            )
        )
    return StatementContext(
        practice_name=practice.name,
        practice_address_lines=_address_lines(
            practice.address_line1,
            practice.address_line2,
            practice.city,
            practice.state,
            practice.zip,
        ),
        practice_phone=practice.phone,
        patient_name=f"{patient.first_name} {patient.last_name}",
        patient_address_lines=_address_lines(
            patient.address_line1, patient.address_line2, patient.city, patient.state, patient.zip
        ),
        account_number=str(patient.id)[:8],
        statement_date=statement_date,
        aging=aging,
        lines=lines,
    )


_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)
_env.filters["usd"] = usd


def render_statement_html(ctx: StatementContext) -> str:
    return _env.get_template("statement.html").render(ctx=ctx)


def html_to_pdf(html: str) -> bytes:
    """Render HTML to PDF bytes. Imported lazily — see module docstring."""
    from weasyprint import HTML

    result: bytes = HTML(string=html).write_pdf()
    return result
