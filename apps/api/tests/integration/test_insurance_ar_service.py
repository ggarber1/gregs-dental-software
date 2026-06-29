import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.claim import Claim
from app.services.reports.insurance_ar import get_worklist

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 6, 29, 12, 0, tzinfo=UTC)


async def _claim(session, practice_id, **kw):
    defaults = dict(
        id=uuid.uuid4(),
        practice_id=practice_id,
        appointment_id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        insurance_id=uuid.uuid4(),
        provider_id=uuid.uuid4(),
        idempotency_key=uuid.uuid4().hex,
        patient_control_number=uuid.uuid4().hex[:12],
        payer_id="DELTA",
        status="submitted",
        total_charge_cents=120000,
        submitted_at=_NOW - timedelta(days=10),
    )
    defaults.update(kw)
    claim = Claim(**defaults)
    session.add(claim)
    await session.commit()
    return claim


@pytest.mark.asyncio
async def test_worklist_classifies_and_excludes_draft_and_done(db_session: AsyncSession):
    practice_id = uuid.uuid4()
    await _claim(db_session, practice_id, status="submitted")  # awaiting
    await _claim(db_session, practice_id, status="draft")  # excluded
    await _claim(db_session, practice_id, status="denied", denial_codes=["45"])  # problem
    await _claim(
        db_session, practice_id, status="paid", insurance_paid_cents=120000
    )  # done (paid full, no estimate)

    rows = await get_worklist(db_session, practice_id, now=_NOW)
    cats = sorted(r.category for r in rows)
    assert cats == ["awaiting", "problem"]


@pytest.mark.asyncio
async def test_worklist_sets_days_out_and_bucket(db_session: AsyncSession):
    practice_id = uuid.uuid4()
    await _claim(db_session, practice_id, submitted_at=_NOW - timedelta(days=95))
    rows = await get_worklist(db_session, practice_id, now=_NOW)
    assert rows[0].days_out == 95
    assert rows[0].bucket == "90+"


@pytest.mark.asyncio
async def test_worklist_filters_by_category(db_session: AsyncSession):
    practice_id = uuid.uuid4()
    await _claim(db_session, practice_id, status="submitted")
    await _claim(db_session, practice_id, status="denied", denial_codes=["45"])
    rows = await get_worklist(db_session, practice_id, category="problem", now=_NOW)
    assert len(rows) == 1
    assert rows[0].category == "problem"
    assert rows[0].reason == "denied: 45"


@pytest.mark.asyncio
async def test_worklist_oldest_first(db_session: AsyncSession):
    practice_id = uuid.uuid4()
    await _claim(db_session, practice_id, submitted_at=_NOW - timedelta(days=5))
    await _claim(db_session, practice_id, submitted_at=_NOW - timedelta(days=50))
    rows = await get_worklist(db_session, practice_id, now=_NOW)
    assert [r.days_out for r in rows] == [50, 5]
