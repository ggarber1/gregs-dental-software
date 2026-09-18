"""Integration tests for the patient aging worklist (Module 8b)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry
from app.models.patient import Patient
from app.models.practice import Practice
from app.services.ledger.balance import get_unreversed_entries

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


async def _seed_practice(session: AsyncSession) -> Practice:
    practice = Practice(id=uuid.uuid4(), name="Aging Test Practice")
    session.add(practice)
    await session.commit()
    return practice


async def _seed_patient(
    session: AsyncSession,
    practice_id: uuid.UUID,
    *,
    first: str = "Pat",
    last: str = "Aging",
    email: str | None = "pat@example.test",
) -> Patient:
    patient = Patient(
        id=uuid.uuid4(),
        practice_id=practice_id,
        first_name=first,
        last_name=last,
        date_of_birth=datetime(1990, 1, 1).date(),
        email=email,
    )
    session.add(patient)
    await session.commit()
    return patient


async def _post(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    *,
    entry_type: str,
    amount_cents: int,
    days_ago: int,
    reverses: uuid.UUID | None = None,
) -> LedgerEntry:
    entry = LedgerEntry(
        id=uuid.uuid4(),
        practice_id=practice_id,
        patient_id=patient_id,
        entry_type=entry_type,
        amount_cents=amount_cents,
        reverses_entry_id=reverses,
        posted_at=_NOW - timedelta(days=days_ago),
    )
    session.add(entry)
    await session.commit()
    return entry


class TestUnreversedEntries:
    async def test_excludes_both_sides_of_a_reversal(self, db_session: AsyncSession):
        practice = await _seed_practice(db_session)
        patient = await _seed_patient(db_session, practice.id)
        kept = await _post(
            db_session, practice.id, patient.id, entry_type="charge", amount_cents=10000, days_ago=5
        )
        wrong = await _post(
            db_session, practice.id, patient.id, entry_type="charge", amount_cents=5000, days_ago=4
        )
        await _post(
            db_session,
            practice.id,
            patient.id,
            entry_type="charge",
            amount_cents=-5000,
            days_ago=1,
            reverses=wrong.id,
        )

        entries = await get_unreversed_entries(db_session, practice.id, {patient.id})

        assert [e.id for e in entries] == [kept.id]

    async def test_returns_oldest_first_across_patients(self, db_session: AsyncSession):
        practice = await _seed_practice(db_session)
        a = await _seed_patient(db_session, practice.id, first="A")
        b = await _seed_patient(db_session, practice.id, first="B")
        newer = await _post(
            db_session, practice.id, a.id, entry_type="charge", amount_cents=100, days_ago=1
        )
        older = await _post(
            db_session, practice.id, b.id, entry_type="charge", amount_cents=100, days_ago=9
        )

        entries = await get_unreversed_entries(db_session, practice.id, {a.id, b.id})

        assert [e.id for e in entries] == [older.id, newer.id]
