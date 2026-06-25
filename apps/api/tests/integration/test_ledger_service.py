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
