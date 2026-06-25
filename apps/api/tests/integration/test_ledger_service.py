import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry
from app.services.ledger.balance import get_ledger, get_patient_balance

pytestmark = pytest.mark.integration


async def _add(session, practice_id, patient_id, entry_type, amount, **kw):
    e = LedgerEntry(
        id=uuid.uuid4(),
        practice_id=practice_id,
        patient_id=patient_id,
        entry_type=entry_type,
        amount_cents=amount,
        **kw,
    )
    session.add(e)
    await session.commit()
    return e


@pytest.mark.asyncio
async def test_ledger_entry_inserts(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    db_session.add(
        LedgerEntry(
            id=uuid.uuid4(),
            practice_id=practice_id,
            patient_id=patient_id,
            entry_type="charge",
            amount_cents=25000,
        )
    )
    await db_session.commit()
    row = await db_session.scalar(
        select(LedgerEntry).where(LedgerEntry.patient_id == patient_id)
    )
    assert row is not None
    assert row.amount_cents == 25000
    assert row.posted_by == "system"


@pytest.mark.asyncio
async def test_payment_method_rejected_on_non_payment_entry(db_session: AsyncSession):
    """ck_ledger_entries_payment_method: payment_method is only allowed on
    patient_payment entries."""
    from sqlalchemy.exc import IntegrityError

    db_session.add(
        LedgerEntry(
            id=uuid.uuid4(),
            practice_id=uuid.uuid4(),
            patient_id=uuid.uuid4(),
            entry_type="charge",
            amount_cents=1000,
            payment_method="cash",  # invalid: charge cannot carry a payment_method
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_balance_and_ledger_read(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    await _add(db_session, practice_id, patient_id, "charge", 25000)
    await _add(db_session, practice_id, patient_id, "insurance_payment", -20000)
    await _add(db_session, practice_id, patient_id, "patient_payment", -5000,
               payment_method="cash")

    assert await get_patient_balance(db_session, practice_id, patient_id) == 0
    entries, balance = await get_ledger(db_session, practice_id, patient_id)
    assert balance == 0
    assert len(entries) == 3
    assert entries[0][1] == 25000  # running balance after first charge
