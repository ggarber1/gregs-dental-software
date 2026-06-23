import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.claim import Claim
from app.models.era_remittance import ERARemittance, UnmatchedERAPayment
from app.services.era.base import RemittanceClient, Transaction
from app.services.era.service import poll_and_post_eras

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
    summary = await poll_and_post_eras(db_session, practice_id, client=client, since=since, user_sub="s")
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
