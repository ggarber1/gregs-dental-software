import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.claim import Claim
from app.models.era_remittance import UnmatchedERAPayment
from app.services.era.base import RemittanceClient, Transaction
from app.services.era.service import poll_and_post_eras, resolve_unmatched_payment
from app.services.ledger.balance import get_patient_balance

pytestmark = pytest.mark.integration


def _era_doc(pcn: str, status: str = "1", paid: str = "200.00", pr: str = "50.00") -> dict:
    return {
        "transactions": [
            {
                "payer": {"name": "DELTA DENTAL"},
                "reassociationTraceNumber": {"checkOrEftTraceNumber": "EFT1"},
                "productionDate": "20260615",
                "financialInformation": {"totalActualProviderPaymentAmount": paid},
                "detailInfo": [
                    {
                        "paymentInfo": [
                            {
                                "claimPaymentInfo": {
                                    "patientControlNumber": pcn,
                                    "claimStatusCode": status,
                                    "totalClaimChargeAmount": "250.00",
                                    "claimPaymentAmount": paid,
                                    "patientResponsibilityAmount": pr,
                                    "payerClaimControlNumber": "P-1",
                                }
                            }
                        ]
                    }
                ],
            }
        ]
    }


class _FakeClient(RemittanceClient):
    def __init__(self, txn_to_doc: dict[str, dict]):
        self._docs = txn_to_doc
        self.fetches = 0

    async def poll_transactions(self, since):
        return [Transaction(transaction_id=t) for t in self._docs]

    async def fetch_era(self, transaction_id: str) -> dict:
        self.fetches += 1
        return self._docs[transaction_id]


async def _seed_claim(session: AsyncSession, pcn: str) -> Claim:
    claim = Claim(
        id=uuid.uuid4(),
        practice_id=uuid.uuid4(),
        appointment_id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        insurance_id=uuid.uuid4(),
        provider_id=uuid.uuid4(),
        idempotency_key=uuid.uuid4().hex,
        patient_control_number=pcn,
        payer_id="CDLA1",
        status="submitted",
        total_charge_cents=25000,
    )
    session.add(claim)
    await session.commit()
    return claim


@pytest.mark.asyncio
async def test_matches_and_posts_payment_onto_claim(db_session: AsyncSession):
    claim = await _seed_claim(db_session, "PCN12345")
    client = _FakeClient({"txn-1": _era_doc("PCN12345")})

    summary = await poll_and_post_eras(
        db_session, claim.practice_id, client=client,
        since=datetime.now(UTC) - timedelta(days=30), user_sub="sub-1",
    )
    assert summary["matched"] == 1
    assert summary["unmatched"] == 0

    await db_session.refresh(claim)
    assert claim.status == "partially_paid"
    assert claim.insurance_paid_cents == 20000
    assert claim.patient_responsibility_cents == 5000
    assert claim.paid_at is not None
    assert claim.remittance_id is not None


@pytest.mark.asyncio
async def test_dedup_skips_already_ingested_no_second_fetch(db_session: AsyncSession):
    claim = await _seed_claim(db_session, "PCN12345")
    client = _FakeClient({"txn-1": _era_doc("PCN12345")})
    practice_id = claim.practice_id
    since = datetime.now(UTC) - timedelta(days=30)

    await poll_and_post_eras(db_session, practice_id, client=client, since=since, user_sub="s")
    assert client.fetches == 1
    # second poll: same transaction id already ingested -> skipped, no new fetch
    summary = await poll_and_post_eras(
        db_session, practice_id, client=client, since=since, user_sub="s"
    )
    assert client.fetches == 1
    assert summary["new"] == 0


@pytest.mark.asyncio
async def test_no_matching_claim_writes_unmatched(db_session: AsyncSession):
    practice_id = uuid.uuid4()
    client = _FakeClient({"txn-9": _era_doc("NOPE999")})
    summary = await poll_and_post_eras(
        db_session, practice_id, client=client,
        since=datetime.now(UTC) - timedelta(days=30), user_sub="s",
    )
    assert summary["matched"] == 0
    assert summary["unmatched"] == 1
    rows = (await db_session.scalars(
        select(UnmatchedERAPayment).where(UnmatchedERAPayment.practice_id == practice_id)
    )).all()
    assert len(rows) == 1
    assert rows[0].patient_control_number == "NOPE999"


@pytest.mark.asyncio
async def test_prefix_match_handles_truncated_pcn(db_session: AsyncSession):
    claim = await _seed_claim(db_session, "ABCDEFGHIJKLMNOPQ")  # 17 chars
    client = _FakeClient({"txn-1": _era_doc("ABCDEFGHIJKLM")})  # payer truncated to 13
    summary = await poll_and_post_eras(
        db_session, claim.practice_id, client=client,
        since=datetime.now(UTC) - timedelta(days=30), user_sub="s",
    )
    assert summary["matched"] == 1
    await db_session.refresh(claim)
    assert claim.status == "partially_paid"


@pytest.mark.asyncio
async def test_resolve_unmatched_marks_resolved(db_session: AsyncSession):
    practice_id = uuid.uuid4()
    client = _FakeClient({"txn-1": _era_doc("NOPE")})
    await poll_and_post_eras(
        db_session, practice_id, client=client,
        since=datetime.now(UTC) - timedelta(days=30), user_sub="s",
    )
    row = (
        await db_session.scalars(
            select(UnmatchedERAPayment).where(UnmatchedERAPayment.practice_id == practice_id)
        )
    ).first()
    assert row is not None
    resolved = await resolve_unmatched_payment(db_session, practice_id, row.id)
    assert resolved is not None
    assert resolved.resolved is True
    assert resolved.resolved_at is not None


@pytest.mark.asyncio
async def test_resolve_unmatched_not_found_returns_none(db_session: AsyncSession):
    assert await resolve_unmatched_payment(db_session, uuid.uuid4(), uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_resolve_unmatched_other_practice_returns_none(db_session: AsyncSession):
    practice_id = uuid.uuid4()
    client = _FakeClient({"txn-1": _era_doc("NOPE")})
    await poll_and_post_eras(
        db_session, practice_id, client=client,
        since=datetime.now(UTC) - timedelta(days=30), user_sub="s",
    )
    row = (
        await db_session.scalars(
            select(UnmatchedERAPayment).where(UnmatchedERAPayment.practice_id == practice_id)
        )
    ).first()
    assert row is not None
    # a different practice cannot resolve another practice's unmatched payment
    assert await resolve_unmatched_payment(db_session, uuid.uuid4(), row.id) is None


@pytest.mark.asyncio
async def test_draft_claim_is_not_matched(db_session: AsyncSession):
    claim = await _seed_claim(db_session, "PCNDRAFT")
    claim.status = "draft"
    await db_session.commit()
    client = _FakeClient({"txn-1": _era_doc("PCNDRAFT")})
    summary = await poll_and_post_eras(
        db_session, claim.practice_id, client=client,
        since=datetime.now(UTC) - timedelta(days=30), user_sub="s",
    )
    assert summary["matched"] == 0
    assert summary["unmatched"] == 1
    await db_session.refresh(claim)
    assert claim.status == "draft"  # untouched


@pytest.mark.asyncio
async def test_already_posted_claim_is_not_overwritten(db_session: AsyncSession):
    claim = await _seed_claim(db_session, "PCNPAID1")
    client = _FakeClient({"txn-1": _era_doc("PCNPAID1")})
    practice_id = claim.practice_id
    since = datetime.now(UTC) - timedelta(days=30)
    # first ERA posts and sets remittance_id
    await poll_and_post_eras(db_session, practice_id, client=client, since=since, user_sub="s")
    await db_session.refresh(claim)
    first_remittance = claim.remittance_id
    assert first_remittance is not None
    # a different ERA (different txn id) for the same PCN must NOT overwrite — goes to review
    client2 = _FakeClient({"txn-2": _era_doc("PCNPAID1", paid="100.00", pr="0.00")})
    summary = await poll_and_post_eras(
        db_session, practice_id, client=client2, since=since, user_sub="s"
    )
    assert summary["matched"] == 0
    assert summary["unmatched"] == 1
    await db_session.refresh(claim)
    assert claim.remittance_id == first_remittance  # unchanged
    assert claim.insurance_paid_cents == 20000  # original payment, not overwritten


@pytest.mark.asyncio
async def test_ambiguous_prefix_is_routed_to_unmatched(db_session: AsyncSession):
    practice_id = uuid.uuid4()
    # two postable claims sharing a prefix
    for pcn in ("ABCDEF12345", "ABCDEF67890"):
        c = await _seed_claim(db_session, pcn)
        c.practice_id = practice_id
    await db_session.commit()
    client = _FakeClient({"txn-1": _era_doc("ABCDEF")})  # truncated prefix matches both
    summary = await poll_and_post_eras(
        db_session, practice_id, client=client,
        since=datetime.now(UTC) - timedelta(days=30), user_sub="s",
    )
    assert summary["matched"] == 0
    assert summary["unmatched"] == 1


@pytest.mark.asyncio
async def test_unique_prefix_still_matches(db_session: AsyncSession):
    claim = await _seed_claim(db_session, "ZZZUNIQUE12345")
    client = _FakeClient({"txn-1": _era_doc("ZZZUNIQUE")})  # unambiguous prefix
    summary = await poll_and_post_eras(
        db_session, claim.practice_id, client=client,
        since=datetime.now(UTC) - timedelta(days=30), user_sub="s",
    )
    assert summary["matched"] == 1


@pytest.mark.asyncio
async def test_era_match_posts_ledger_insurance_entries(db_session: AsyncSession):
    claim = await _seed_claim(db_session, "PCNLED123")
    # gross charge already on the ledger for this patient
    from app.models.ledger_entry import LedgerEntry
    db_session.add(LedgerEntry(
        id=uuid.uuid4(), practice_id=claim.practice_id, patient_id=claim.patient_id,
        entry_type="charge", amount_cents=25000,
    ))
    await db_session.commit()

    client = _FakeClient({"txn-1": _era_doc("PCNLED123")})  # paid 200.00
    summary = await poll_and_post_eras(
        db_session, claim.practice_id, client=client,
        since=datetime.now(UTC) - timedelta(days=30), user_sub="s",
        post_to_ledger=True,
    )
    assert summary["matched"] == 1
    # 25000 charge - 20000 insurance payment = 5000 (no non-PR adjustment in _era_doc)
    balance = await get_patient_balance(db_session, claim.practice_id, claim.patient_id)
    assert balance == 5000


@pytest.mark.asyncio
async def test_era_match_skips_ledger_when_flag_off(db_session: AsyncSession):
    claim = await _seed_claim(db_session, "PCNLED456")
    from app.models.ledger_entry import LedgerEntry
    db_session.add(LedgerEntry(
        id=uuid.uuid4(), practice_id=claim.practice_id, patient_id=claim.patient_id,
        entry_type="charge", amount_cents=25000,
    ))
    await db_session.commit()

    client = _FakeClient({"txn-2": _era_doc("PCNLED456")})
    summary = await poll_and_post_eras(
        db_session, claim.practice_id, client=client,
        since=datetime.now(UTC) - timedelta(days=30), user_sub="s",
        post_to_ledger=False,  # default; ledger untouched
    )
    assert summary["matched"] == 1
    # claim still posted (7b behavior) but NO ledger insurance entry -> charge only
    assert await get_patient_balance(db_session, claim.practice_id, claim.patient_id) == 25000
