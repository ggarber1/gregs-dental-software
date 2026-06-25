import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry

pytestmark = pytest.mark.integration


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
