"""Integration tests for the patient aging worklist (Module 8b)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry
from app.models.patient import Patient
from app.models.patient_statement import PatientStatement
from app.models.practice import Practice
from app.services.ledger.balance import get_unreversed_entries
from app.services.reports.patient_aging import get_patient_aging_worklist

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


class TestPatientAgingWorklist:
    async def test_buckets_ordering_and_exclusions(self, db_session: AsyncSession):
        practice = await _seed_practice(db_session)
        big = await _seed_patient(db_session, practice.id, first="Big", last="Balance")
        small = await _seed_patient(db_session, practice.id, first="Small", last="Balance")
        zero = await _seed_patient(db_session, practice.id, first="Zero", last="Balance")
        credit = await _seed_patient(db_session, practice.id, first="Credit", last="Balance")

        # big: 100 current + 200 (31-60) + 300 (61-90) + 400 (90+), minus 50 paid = 950
        await _post(
            db_session, practice.id, big.id, entry_type="charge", amount_cents=100, days_ago=1
        )
        await _post(
            db_session, practice.id, big.id, entry_type="charge", amount_cents=200, days_ago=40
        )
        await _post(
            db_session, practice.id, big.id, entry_type="charge", amount_cents=300, days_ago=70
        )
        await _post(
            db_session, practice.id, big.id, entry_type="charge", amount_cents=400, days_ago=100
        )
        await _post(
            db_session,
            practice.id,
            big.id,
            entry_type="patient_payment",
            amount_cents=-50,
            days_ago=0,
        )
        # small: 600 current
        await _post(
            db_session, practice.id, small.id, entry_type="charge", amount_cents=600, days_ago=3
        )
        # zero: charged and fully paid
        await _post(
            db_session, practice.id, zero.id, entry_type="charge", amount_cents=700, days_ago=3
        )
        await _post(
            db_session,
            practice.id,
            zero.id,
            entry_type="patient_payment",
            amount_cents=-700,
            days_ago=1,
        )
        # credit: overpaid
        await _post(
            db_session, practice.id, credit.id, entry_type="charge", amount_cents=100, days_ago=3
        )
        await _post(
            db_session,
            practice.id,
            credit.id,
            entry_type="patient_payment",
            amount_cents=-300,
            days_ago=1,
        )

        rows = await get_patient_aging_worklist(db_session, practice.id, now=_NOW)

        assert [r.patient_id for r in rows] == [big.id, small.id]
        b = rows[0]
        assert b.patient_name == "Big Balance"
        assert b.email == "pat@example.test"
        assert b.aging.buckets.b0_30 == 100
        assert b.aging.buckets.b31_60 == 200
        assert b.aging.buckets.b61_90 == 300
        assert b.aging.buckets.b90_plus == 400
        assert b.aging.credits_cents == -50
        assert b.aging.balance_cents == 950
        assert b.aging.oldest_charge_at == _NOW - timedelta(days=100)
        assert b.last_statement_at is None
        assert b.last_statement_method is None

    async def test_min_balance_is_inclusive(self, db_session: AsyncSession):
        practice = await _seed_practice(db_session)
        exact = await _seed_patient(db_session, practice.id, first="Exact")
        under = await _seed_patient(db_session, practice.id, first="Under")
        await _post(
            db_session, practice.id, exact.id, entry_type="charge", amount_cents=500, days_ago=1
        )
        await _post(
            db_session, practice.id, under.id, entry_type="charge", amount_cents=499, days_ago=1
        )

        default_rows = await get_patient_aging_worklist(db_session, practice.id, now=_NOW)
        all_rows = await get_patient_aging_worklist(
            db_session, practice.id, min_balance_cents=1, now=_NOW
        )

        assert [r.patient_id for r in default_rows] == [exact.id]
        assert {r.patient_id for r in all_rows} == {exact.id, under.id}

    async def test_reversal_pair_does_not_age(self, db_session: AsyncSession):
        practice = await _seed_practice(db_session)
        patient = await _seed_patient(db_session, practice.id)
        await _post(
            db_session, practice.id, patient.id, entry_type="charge", amount_cents=1000, days_ago=2
        )
        wrong = await _post(
            db_session,
            practice.id,
            patient.id,
            entry_type="charge",
            amount_cents=9000,
            days_ago=120,
        )
        await _post(
            db_session,
            practice.id,
            patient.id,
            entry_type="charge",
            amount_cents=-9000,
            days_ago=0,
            reverses=wrong.id,
        )

        rows = await get_patient_aging_worklist(db_session, practice.id, now=_NOW)

        assert len(rows) == 1
        assert rows[0].aging.buckets.b90_plus == 0
        assert rows[0].aging.buckets.b0_30 == 1000
        assert rows[0].aging.balance_cents == 1000

    async def test_sort_modes(self, db_session: AsyncSession):
        practice = await _seed_practice(db_session)
        never = await _seed_patient(db_session, practice.id, first="Never")
        recent = await _seed_patient(db_session, practice.id, first="Recent")
        stale = await _seed_patient(db_session, practice.id, first="Stale")
        await _post(
            db_session, practice.id, never.id, entry_type="charge", amount_cents=1000, days_ago=10
        )
        await _post(
            db_session, practice.id, recent.id, entry_type="charge", amount_cents=3000, days_ago=95
        )
        await _post(
            db_session, practice.id, stale.id, entry_type="charge", amount_cents=2000, days_ago=50
        )
        for pid, days in ((recent.id, 2), (stale.id, 30)):
            db_session.add(
                PatientStatement(
                    id=uuid.uuid4(),
                    practice_id=practice.id,
                    patient_id=pid,
                    delivery_method="email",
                    balance_cents=1,
                    aging_snapshot={"b0_30": 1, "b31_60": 0, "b61_90": 0, "b90_plus": 0},
                    generated_at=_NOW - timedelta(days=days),
                    delivered_at=_NOW - timedelta(days=days),
                    generated_by="test",
                )
            )
        await db_session.commit()

        by_balance = await get_patient_aging_worklist(db_session, practice.id, now=_NOW)
        by_oldest = await get_patient_aging_worklist(
            db_session, practice.id, sort_by="oldest_charge", now=_NOW
        )
        by_statement = await get_patient_aging_worklist(
            db_session, practice.id, sort_by="last_statement", now=_NOW
        )

        assert [r.patient_id for r in by_balance] == [recent.id, stale.id, never.id]
        assert [r.patient_id for r in by_oldest] == [recent.id, stale.id, never.id]
        assert [r.patient_id for r in by_statement] == [never.id, stale.id, recent.id]
        assert by_balance[0].last_statement_at == _NOW - timedelta(days=2)
        assert by_balance[0].last_statement_method == "email"

    async def test_scoped_to_practice_and_skips_deleted_patients(self, db_session: AsyncSession):
        practice = await _seed_practice(db_session)
        other = await _seed_practice(db_session)
        mine = await _seed_patient(db_session, practice.id, first="Mine")
        theirs = await _seed_patient(db_session, other.id, first="Theirs")
        gone = await _seed_patient(db_session, practice.id, first="Gone")
        gone.deleted_at = _NOW
        await db_session.commit()
        for pid, prac in ((mine.id, practice.id), (theirs.id, other.id), (gone.id, practice.id)):
            await _post(db_session, prac, pid, entry_type="charge", amount_cents=1000, days_ago=1)

        rows = await get_patient_aging_worklist(db_session, practice.id, now=_NOW)

        assert [r.patient_id for r in rows] == [mine.id]
