"""Statement orchestration: load ledger → aging → PDF → email/record.

Raises domain exceptions the router maps to HTTP codes:
  LookupError               → 404 patient not in this practice
  NoOutstandingBalanceError → 400
  NoPatientEmailError       → 400
  RuntimeError              → 502 (SES failure, from send_email_with_attachment)
"""

from __future__ import annotations

import asyncio
import html as html_mod
import uuid
from datetime import UTC, date, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry
from app.models.patient import Patient
from app.models.patient_statement import PatientStatement
from app.models.practice import Practice
from app.services.email import send_email_with_attachment
from app.services.ledger.balance import get_unreversed_entries
from app.services.reports.patient_aging import AgingBreakdown, bucket_ledger_entries
from app.services.statements.pdf import build_context, html_to_pdf, render_statement_html, usd

DeliveryMethod = Literal["email", "download"]


class NoOutstandingBalanceError(ValueError):
    pass


class NoPatientEmailError(ValueError):
    pass


def statement_filename(statement_date: date) -> str:
    return f"statement-{statement_date.isoformat()}.pdf"


async def _load_practice_and_patient(
    session: AsyncSession, practice_id: uuid.UUID, patient_id: uuid.UUID
) -> tuple[Practice, Patient]:
    patient = await session.scalar(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.practice_id == practice_id,
            Patient.deleted_at.is_(None),
        )
    )
    if patient is None:
        raise LookupError("Patient not found in this practice")
    practice = await session.scalar(select(Practice).where(Practice.id == practice_id))
    if practice is None:
        raise LookupError("Practice not found")
    return practice, patient


async def _build(
    session: AsyncSession, practice_id: uuid.UUID, patient_id: uuid.UUID, *, now: datetime
) -> tuple[Practice, Patient, list[LedgerEntry], AgingBreakdown]:
    practice, patient = await _load_practice_and_patient(session, practice_id, patient_id)
    entries = await get_unreversed_entries(session, practice_id, [patient_id])
    return practice, patient, entries, bucket_ledger_entries(entries, now=now)


async def _render(
    practice: Practice,
    patient: Patient,
    entries: list[LedgerEntry],
    aging: AgingBreakdown,
    statement_date: date,
) -> bytes:
    ctx = build_context(practice, patient, entries, aging, statement_date=statement_date)
    # WeasyPrint is CPU-bound; keep it off the event loop.
    return await asyncio.to_thread(html_to_pdf, render_statement_html(ctx))


async def render_statement_pdf(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    *,
    statement_date: date,
    require_balance: bool = False,
    now: datetime | None = None,
) -> bytes:
    """PDF bytes for the patient's current ledger, stamped with `statement_date`.

    `require_balance=True` is the preview rule (spec: no statement without a balance).
    Re-downloads of a recorded statement pass False so they still work after payment.
    """
    now = now or datetime.now(UTC)
    practice, patient, entries, aging = await _build(session, practice_id, patient_id, now=now)
    if require_balance and aging.balance_cents <= 0:
        raise NoOutstandingBalanceError("No outstanding balance.")
    return await _render(practice, patient, entries, aging, statement_date)


async def send_statement_email(
    practice: Practice, patient: Patient, pdf: bytes, *, statement_date: date, balance_cents: int
) -> str | None:
    # email_opt_out is deliberately NOT checked here. That flag governs marketing and
    # appointment reminders (see reminder_worker._deliver_email); a billing statement is
    # a transactional communication about money the patient owes.
    assert patient.email  # guarded by create_statement
    phone = f" at {practice.phone}" if practice.phone else ""
    text = (
        f"Your statement from {practice.name} is attached.\n\n"
        f"Amount due: {usd(balance_cents)}\n\n"
        f"Please contact our office{phone} to arrange payment.\n"
    )
    html = (
        f"<p>Your statement from {html_mod.escape(practice.name)} is attached.</p>"
        f"<p><strong>Amount due: {usd(balance_cents)}</strong></p>"
        f"<p>Please contact our office{html_mod.escape(phone)} to arrange payment.</p>"
    )
    return await send_email_with_attachment(
        to=patient.email,
        subject=f"Statement from {practice.name}",
        html_body=html,
        text_body=text,
        attachment_bytes=pdf,
        attachment_filename=statement_filename(statement_date),
        from_name=practice.name,
    )


async def create_statement(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    *,
    delivery_method: DeliveryMethod,
    generated_by: str,
    now: datetime | None = None,
) -> PatientStatement:
    """Generate (and for `email`, deliver) a statement, then record it.

    Nothing is written if validation or SES fails. For `download` no PDF is rendered
    here — the client fetches bytes from the GET endpoint after this returns.
    """
    now = now or datetime.now(UTC)
    practice, patient, entries, aging = await _build(session, practice_id, patient_id, now=now)
    if aging.balance_cents <= 0:
        raise NoOutstandingBalanceError("No outstanding balance.")
    if delivery_method == "email" and not patient.email:
        raise NoPatientEmailError("Patient has no email address on file.")

    delivered_at: datetime | None = None
    if delivery_method == "email":
        pdf = await _render(practice, patient, entries, aging, now.date())
        await send_statement_email(
            practice, patient, pdf, statement_date=now.date(), balance_cents=aging.balance_cents
        )
        # send returned None only in dev no-send mode (logged, not rejected);
        # RuntimeError is the sole failure path.
        delivered_at = now

    row = PatientStatement(
        id=uuid.uuid4(),
        practice_id=practice_id,
        patient_id=patient_id,
        delivery_method=delivery_method,
        balance_cents=aging.balance_cents,
        aging_snapshot=aging.snapshot(),
        generated_at=now,
        delivered_at=delivered_at,
        generated_by=generated_by,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_statements(
    session: AsyncSession, practice_id: uuid.UUID, patient_id: uuid.UUID
) -> list[PatientStatement]:
    rows = await session.scalars(
        select(PatientStatement)
        .where(
            PatientStatement.practice_id == practice_id,
            PatientStatement.patient_id == patient_id,
            PatientStatement.deleted_at.is_(None),
        )
        .order_by(PatientStatement.generated_at.desc(), PatientStatement.id)
    )
    return list(rows)


async def get_statement(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    statement_id: uuid.UUID,
) -> PatientStatement | None:
    row: PatientStatement | None = await session.scalar(
        select(PatientStatement).where(
            PatientStatement.id == statement_id,
            PatientStatement.practice_id == practice_id,
            PatientStatement.patient_id == patient_id,
            PatientStatement.deleted_at.is_(None),
        )
    )
    return row
