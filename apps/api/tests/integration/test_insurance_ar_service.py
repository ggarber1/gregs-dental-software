import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.claim import Claim
from app.services.reports.insurance_ar import (
    accept_underpayment,
    flag_for_appeal,
    get_summary,
    get_worklist,
)

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


async def _seed_estimate(session, appointment_id, insurance_owes_cents):
    from app.models.copay_calculation import CopayCalculation

    calc = CopayCalculation(
        id=uuid.uuid4(),
        practice_id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        appointment_id=appointment_id,
        calculated_at=_NOW,
        plan_type="PPO",
        total_provider_fee_cents=insurance_owes_cents,
        total_write_off_cents=0,
        total_insurance_owes_cents=insurance_owes_cents,
        total_patient_owes_cents=0,
        line_items=[],
        idempotency_key=uuid.uuid4().hex,
    )
    session.add(calc)
    await session.commit()
    return calc


# ---------------------------------------------------------------------------
# Task 5 tests — get_worklist
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Task 6 tests — get_summary + accept/appeal actions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_summary_reconciles_with_worklist(db_session: AsyncSession):
    practice_id = uuid.uuid4()
    await _claim(
        db_session,
        practice_id,
        payer_id="DELTA",
        total_charge_cents=1000,
        submitted_at=_NOW - timedelta(days=10),
    )
    await _claim(
        db_session,
        practice_id,
        payer_id="DELTA",
        total_charge_cents=500,
        submitted_at=_NOW - timedelta(days=70),
    )
    summary = await get_summary(db_session, practice_id, now=_NOW)
    delta = next(c for c in summary.carriers if c.payer_id == "DELTA")
    assert delta.buckets.b0_30 == 1000
    assert delta.buckets.b61_90 == 500
    assert summary.totals.total_billed_cents == 1500


@pytest.mark.asyncio
async def test_accept_underpayment_marks_reviewed_and_drops_off(db_session: AsyncSession):
    practice_id = uuid.uuid4()
    # underpaid: paid 200 with a procedure-estimate of 1000 (>5% below)
    appt_id = uuid.uuid4()
    claim = await _claim(
        db_session,
        practice_id,
        appointment_id=appt_id,
        status="partially_paid",
        insurance_paid_cents=20000,
        total_charge_cents=120000,
    )
    await _seed_estimate(db_session, appt_id, 100000)

    rows = await get_worklist(db_session, practice_id, now=_NOW)
    assert [r.category for r in rows] == ["underpaid"]

    updated = await accept_underpayment(db_session, practice_id, claim.id, now=_NOW)
    assert updated.insurance_reviewed_at is not None
    rows_after = await get_worklist(db_session, practice_id, now=_NOW)
    assert rows_after == []


@pytest.mark.asyncio
async def test_flag_for_appeal_moves_to_appealing(db_session: AsyncSession):
    practice_id = uuid.uuid4()
    appt_id = uuid.uuid4()
    claim = await _claim(
        db_session,
        practice_id,
        appointment_id=appt_id,
        status="partially_paid",
        insurance_paid_cents=20000,
        total_charge_cents=120000,
    )
    await _seed_estimate(db_session, appt_id, 100000)

    updated = await flag_for_appeal(db_session, practice_id, claim.id)
    assert updated.status == "appealing"
    rows = await get_worklist(db_session, practice_id, now=_NOW)
    assert [r.category for r in rows] == ["appealing"]


@pytest.mark.asyncio
async def test_actions_reject_claim_not_underpaid(db_session: AsyncSession):
    practice_id = uuid.uuid4()
    claim = await _claim(db_session, practice_id, status="submitted")  # awaiting, not underpaid
    with pytest.raises(ValueError):
        await accept_underpayment(db_session, practice_id, claim.id, now=_NOW)
    with pytest.raises(ValueError):
        await flag_for_appeal(db_session, practice_id, claim.id)


@pytest.mark.asyncio
async def test_actions_reject_other_practice(db_session: AsyncSession):
    practice_id = uuid.uuid4()
    other = uuid.uuid4()
    claim = await _claim(
        db_session,
        practice_id,
        status="partially_paid",
        insurance_paid_cents=20000,
        total_charge_cents=120000,
    )
    with pytest.raises(LookupError):
        await accept_underpayment(db_session, other, claim.id, now=_NOW)
