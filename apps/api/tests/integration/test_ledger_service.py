import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment_procedure import AppointmentProcedure
from app.models.claim import Claim
from app.models.ledger_entry import LedgerEntry
from app.services.ledger.balance import get_ledger, get_patient_balance
from app.services.ledger.posting import (
    add_manual_adjustment,
    post_insurance_remittance,
    reconcile_charges_for_appointment,
    record_patient_payment,
    reverse_entry,
)

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


@pytest.mark.asyncio
async def test_record_patient_payment_posts_negative(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    entry = await record_patient_payment(
        db_session, practice_id, patient_id,
        amount_cents=5000, payment_method="card", memo="copay", posted_by="user-1",
    )
    assert entry.entry_type == "patient_payment"
    assert entry.amount_cents == -5000
    assert entry.payment_method == "card"
    assert await get_patient_balance(db_session, practice_id, patient_id) == -5000


@pytest.mark.asyncio
async def test_record_patient_payment_rejects_non_positive(db_session: AsyncSession):
    with pytest.raises(ValueError):
        await record_patient_payment(
            db_session, uuid.uuid4(), uuid.uuid4(),
            amount_cents=0, payment_method="cash", memo=None, posted_by="u",
        )


@pytest.mark.asyncio
async def test_add_manual_adjustment_requires_memo(db_session: AsyncSession):
    with pytest.raises(ValueError):
        await add_manual_adjustment(
            db_session, uuid.uuid4(), uuid.uuid4(),
            amount_cents=-1000, memo="", posted_by="u",
        )


@pytest.mark.asyncio
async def test_add_manual_adjustment_posts(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    await _add(db_session, practice_id, patient_id, "charge", 10000)
    entry = await add_manual_adjustment(
        db_session, practice_id, patient_id,
        amount_cents=-1500, memo="senior discount", posted_by="user-1",
    )
    assert entry.entry_type == "adjustment"
    assert entry.amount_cents == -1500
    assert await get_patient_balance(db_session, practice_id, patient_id) == 8500


@pytest.mark.asyncio
async def test_reverse_entry_mirrors_and_zeroes(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    pay = await record_patient_payment(
        db_session, practice_id, patient_id,
        amount_cents=5000, payment_method="cash", memo=None, posted_by="u",
    )
    rev = await reverse_entry(db_session, practice_id, pay.id, posted_by="u", memo="entered twice")
    assert rev is not None
    assert rev.amount_cents == 5000  # mirror of -5000
    assert rev.reverses_entry_id == pay.id
    assert rev.payment_method == "cash"
    assert await get_patient_balance(db_session, practice_id, patient_id) == 0


@pytest.mark.asyncio
async def test_reverse_entry_rejects_double_reverse(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    pay = await record_patient_payment(
        db_session, practice_id, patient_id,
        amount_cents=5000, payment_method="cash", memo=None, posted_by="u",
    )
    await reverse_entry(db_session, practice_id, pay.id, posted_by="u")
    assert await reverse_entry(db_session, practice_id, pay.id, posted_by="u") is None


@pytest.mark.asyncio
async def test_reverse_entry_other_practice_returns_none(db_session: AsyncSession):
    pay = await record_patient_payment(
        db_session, uuid.uuid4(), uuid.uuid4(),
        amount_cents=5000, payment_method="cash", memo=None, posted_by="u",
    )
    assert await reverse_entry(db_session, uuid.uuid4(), pay.id, posted_by="u") is None


@pytest.mark.asyncio
async def test_reverse_entry_rejects_reversing_a_reversal(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    pay = await record_patient_payment(
        db_session, practice_id, patient_id,
        amount_cents=5000, payment_method="cash", memo=None, posted_by="u",
    )
    rev = await reverse_entry(db_session, practice_id, pay.id, posted_by="u")
    assert rev is not None
    # cannot reverse a reversal entry itself
    assert await reverse_entry(db_session, practice_id, rev.id, posted_by="u") is None


async def _ensure_appointment(session, practice_id, appointment_id):
    """Insert the practice + appointment that appointment_procedures.appointment_id
    FKs to, once per id (re-running for a second procedure is a no-op)."""
    from datetime import UTC, datetime, timedelta

    from app.models.appointment import Appointment
    from app.models.practice import Practice

    if await session.get(Appointment, appointment_id) is not None:
        return
    if await session.get(Practice, practice_id) is None:
        session.add(
            Practice(id=practice_id, name="Test Practice", timezone="America/New_York")
        )
        await session.flush()
    start = datetime.now(UTC)
    session.add(
        Appointment(
            id=appointment_id,
            practice_id=practice_id,
            start_time=start,
            end_time=start + timedelta(minutes=30),
        )
    )
    await session.commit()


async def _seed_proc(session, practice_id, patient_id, appointment_id, fee, name="Exam"):
    await _ensure_appointment(session, practice_id, appointment_id)
    proc = AppointmentProcedure(
        id=uuid.uuid4(),
        practice_id=practice_id,
        appointment_id=appointment_id,
        patient_id=patient_id,
        procedure_code="D0120",
        procedure_name=name,
        fee_cents=fee,
    )
    session.add(proc)
    await session.commit()
    return proc


@pytest.mark.asyncio
async def test_reconcile_posts_one_charge_per_procedure(db_session: AsyncSession):
    practice_id, patient_id, appt_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed_proc(db_session, practice_id, patient_id, appt_id, 12000)
    await _seed_proc(db_session, practice_id, patient_id, appt_id, 8000, name="X-ray")
    appt = SimpleNamespace(id=appt_id, practice_id=practice_id, patient_id=patient_id)

    await reconcile_charges_for_appointment(db_session, appt, user_sub="u")
    assert await get_patient_balance(db_session, practice_id, patient_id) == 20000


@pytest.mark.asyncio
async def test_reconcile_is_idempotent(db_session: AsyncSession):
    practice_id, patient_id, appt_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed_proc(db_session, practice_id, patient_id, appt_id, 12000)
    appt = SimpleNamespace(id=appt_id, practice_id=practice_id, patient_id=patient_id)

    await reconcile_charges_for_appointment(db_session, appt, user_sub="u")
    await reconcile_charges_for_appointment(db_session, appt, user_sub="u")  # no-op
    entries, balance = await get_ledger(db_session, practice_id, patient_id)
    assert balance == 12000
    assert len(entries) == 1  # not double-posted


@pytest.mark.asyncio
async def test_reconcile_reverses_and_reposts_on_fee_change(db_session: AsyncSession):
    practice_id, patient_id, appt_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    proc = await _seed_proc(db_session, practice_id, patient_id, appt_id, 12000)
    appt = SimpleNamespace(id=appt_id, practice_id=practice_id, patient_id=patient_id)
    await reconcile_charges_for_appointment(db_session, appt, user_sub="u")

    proc.fee_cents = 15000
    await db_session.commit()
    await reconcile_charges_for_appointment(db_session, appt, user_sub="u")

    entries, balance = await get_ledger(db_session, practice_id, patient_id)
    assert balance == 15000  # 12000 charge, -12000 reversal, 15000 new charge
    assert len(entries) == 3


@pytest.mark.asyncio
async def test_reconcile_reverses_when_procedure_deleted(db_session: AsyncSession):
    practice_id, patient_id, appt_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    proc = await _seed_proc(db_session, practice_id, patient_id, appt_id, 12000)
    appt = SimpleNamespace(id=appt_id, practice_id=practice_id, patient_id=patient_id)
    await reconcile_charges_for_appointment(db_session, appt, user_sub="u")

    from datetime import UTC, datetime
    proc.deleted_at = datetime.now(UTC)
    await db_session.commit()
    await reconcile_charges_for_appointment(db_session, appt, user_sub="u")
    assert await get_patient_balance(db_session, practice_id, patient_id) == 0


@pytest.mark.asyncio
async def test_reconcile_only_touches_changed_procedure(db_session: AsyncSession):
    practice_id, patient_id, appt_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed_proc(db_session, practice_id, patient_id, appt_id, 12000)
    p2 = await _seed_proc(db_session, practice_id, patient_id, appt_id, 8000, name="X-ray")
    appt = SimpleNamespace(id=appt_id, practice_id=practice_id, patient_id=patient_id)
    await reconcile_charges_for_appointment(db_session, appt, user_sub="u")

    # change only p2's fee
    p2.fee_cents = 9000
    await db_session.commit()
    await reconcile_charges_for_appointment(db_session, appt, user_sub="u")

    entries, balance = await get_ledger(db_session, practice_id, patient_id)
    assert balance == 21000  # 12000 (p1 untouched) + 9000 (p2 new)
    # p1: 1 charge; p2: charge + reversal + new charge = 3 => 4 total
    assert len(entries) == 4


async def _seed_claim_for_ledger(session, practice_id, patient_id):
    claim = Claim(
        id=uuid.uuid4(),
        practice_id=practice_id,
        appointment_id=uuid.uuid4(),
        patient_id=patient_id,
        insurance_id=uuid.uuid4(),
        provider_id=uuid.uuid4(),
        idempotency_key=uuid.uuid4().hex,
        patient_control_number=uuid.uuid4().hex[:12],
        payer_id="CDLA1",
        status="partially_paid",
        total_charge_cents=25000,
        insurance_paid_cents=20000,
        patient_responsibility_cents=2000,
        adjustments=[
            {"group": "CO", "code": "45", "cents": 3000},   # contractual write-off
            {"group": "PR", "code": "2", "cents": 2000},    # patient responsibility
        ],
    )
    session.add(claim)
    await session.commit()
    return claim


@pytest.mark.asyncio
async def test_post_insurance_remittance_payment_and_writeoff(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    await _add(db_session, practice_id, patient_id, "charge", 25000)
    claim = await _seed_claim_for_ledger(db_session, practice_id, patient_id)
    remittance_id = uuid.uuid4()

    await post_insurance_remittance(db_session, claim, remittance_id, user_sub="u")

    # 25000 charge - 20000 payment - 3000 contractual write-off = 2000 patient responsibility
    balance = await get_patient_balance(db_session, practice_id, patient_id)
    assert balance == claim.patient_responsibility_cents == 2000


@pytest.mark.asyncio
async def test_post_insurance_remittance_is_idempotent(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    await _add(db_session, practice_id, patient_id, "charge", 25000)
    claim = await _seed_claim_for_ledger(db_session, practice_id, patient_id)
    remittance_id = uuid.uuid4()

    await post_insurance_remittance(db_session, claim, remittance_id, user_sub="u")
    await post_insurance_remittance(db_session, claim, remittance_id, user_sub="u")  # no-op
    assert await get_patient_balance(db_session, practice_id, patient_id) == 2000


@pytest.mark.asyncio
async def test_post_insurance_remittance_no_writeoff_when_only_pr(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    await _add(db_session, practice_id, patient_id, "charge", 25000)
    claim = await _seed_claim_for_ledger(db_session, practice_id, patient_id)
    claim.adjustments = [{"group": "PR", "code": "2", "cents": 5000}]
    claim.insurance_paid_cents = 20000
    await db_session.commit()

    await post_insurance_remittance(db_session, claim, uuid.uuid4(), user_sub="u")
    # only the payment posts; PR is not written off -> 25000 - 20000 = 5000
    assert await get_patient_balance(db_session, practice_id, patient_id) == 5000


@pytest.mark.asyncio
async def test_post_insurance_remittance_writes_off_oa_not_just_co(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    await _add(db_session, practice_id, patient_id, "charge", 26000)
    claim = await _seed_claim_for_ledger(db_session, practice_id, patient_id)
    claim.adjustments = [
        {"group": "CO", "code": "45", "cents": 3000},
        {"group": "OA", "code": "23", "cents": 1000},
        {"group": "PR", "code": "2", "cents": 2000},
    ]
    claim.insurance_paid_cents = 20000
    claim.patient_responsibility_cents = 2000
    await db_session.commit()

    await post_insurance_remittance(db_session, claim, uuid.uuid4(), user_sub="u")
    # 26000 - 20000 paid - 4000 (CO+OA written off, PR excluded) = 2000 = patient responsibility
    assert await get_patient_balance(db_session, practice_id, patient_id) == 2000


@pytest.mark.asyncio
async def test_post_insurance_remittance_denied_zero_paid(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    await _add(db_session, practice_id, patient_id, "charge", 25000)
    claim = await _seed_claim_for_ledger(db_session, practice_id, patient_id)
    claim.insurance_paid_cents = 0
    claim.adjustments = [{"group": "CO", "code": "45", "cents": 5000}]
    await db_session.commit()

    await post_insurance_remittance(db_session, claim, uuid.uuid4(), user_sub="u")
    # no payment entry (0 paid); CO write-off of 5000 posts -> 25000 - 5000 = 20000
    assert await get_patient_balance(db_session, practice_id, patient_id) == 20000
