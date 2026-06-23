from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.claim import Claim
from app.models.era_remittance import ERARemittance, UnmatchedERAPayment
from app.services.era.base import ClaimPayment, ERAPayment, RemittanceClient
from app.services.era.parser import parse_stedi_era
from app.services.era.posting import claim_payment_fields


async def _match_claim(
    session: AsyncSession, practice_id: uuid.UUID, pcn: str
) -> Claim | None:
    """Match by PCN: exact first, then prefix (payers may truncate the PCN)."""
    if not pcn:
        return None
    exact: Claim | None = await session.scalar(
        select(Claim).where(
            Claim.practice_id == practice_id,
            Claim.patient_control_number == pcn,
            Claim.deleted_at.is_(None),
        )
    )
    if exact is not None:
        return exact
    # Prefix: the stored claim PCN starts with the (possibly truncated) ERA value.
    # pcn is hex-safe (no SQL LIKE wildcards) — see generate_pcn() in claims/idempotency.py.
    prefix: Claim | None = await session.scalar(
        select(Claim).where(
            Claim.practice_id == practice_id,
            Claim.patient_control_number.like(f"{pcn}%"),
            Claim.deleted_at.is_(None),
        )
    )
    return prefix


def _post_to_claim(
    claim: Claim, cp: ClaimPayment, remittance_id: uuid.UUID, user_sub: str | None
) -> None:
    fields = claim_payment_fields(cp)
    claim.insurance_paid_cents = fields["insurance_paid_cents"]
    claim.patient_responsibility_cents = fields["patient_responsibility_cents"]
    claim.payer_claim_control_number = fields["payer_claim_control_number"]
    claim.adjustments = fields["adjustments"]
    claim.denial_codes = fields["denial_codes"]
    claim.status = fields["status"]
    claim.paid_at = datetime.now(UTC)
    claim.remittance_id = remittance_id
    claim.last_accessed_by = user_sub
    claim.last_accessed_at = datetime.now(UTC)


async def poll_and_post_eras(
    session: AsyncSession,
    practice_id: uuid.UUID,
    *,
    client: RemittanceClient,
    since: datetime,
    user_sub: str | None,
) -> dict[str, Any]:
    """Poll Stedi for 835 ERAs, dedup, fetch, parse, match by PCN, and auto-post.

    Idempotent: a transaction already in era_remittances is skipped (no re-fetch,
    no double-post). Safe to re-run after a crash.
    """
    transactions = await client.poll_transactions(since)
    polled = len(transactions)
    new = matched = unmatched = 0
    remittance_ids: list[str] = []

    for txn in transactions:
        already = await session.scalar(
            select(ERARemittance.id).where(
                ERARemittance.stedi_transaction_id == txn.transaction_id
            )
        )
        if already is not None:
            continue
        new += 1

        raw = await client.fetch_era(txn.transaction_id)
        era: ERAPayment = parse_stedi_era(raw)

        remittance = ERARemittance(
            id=uuid.uuid4(),
            practice_id=practice_id,
            stedi_transaction_id=txn.transaction_id,
            payer_name=era.payer_name,
            trace_number=era.trace_number,
            payment_cents=era.payment_cents,
            payment_date=era.payment_date,
            claim_count=len(era.claim_payments),
            matched_count=0,
            unmatched_count=0,
            raw_response=era.raw,
            last_accessed_by=user_sub,
            last_accessed_at=datetime.now(UTC),
        )
        session.add(remittance)

        r_matched = r_unmatched = 0
        for cp in era.claim_payments:
            claim = await _match_claim(session, practice_id, cp.patient_control_number)
            if claim is not None:
                _post_to_claim(claim, cp, remittance.id, user_sub)
                r_matched += 1
            else:
                session.add(
                    UnmatchedERAPayment(
                        id=uuid.uuid4(),
                        practice_id=practice_id,
                        remittance_id=remittance.id,
                        patient_control_number=cp.patient_control_number or None,
                        payer_claim_control_number=cp.payer_claim_control_number,
                        paid_cents=cp.paid_cents,
                        raw_claim_payment=cp.raw,
                    )
                )
                r_unmatched += 1

        remittance.matched_count = r_matched
        remittance.unmatched_count = r_unmatched
        matched += r_matched
        unmatched += r_unmatched
        remittance_ids.append(str(remittance.id))
        await session.commit()

    return {
        "polled": polled,
        "new": new,
        "matched": matched,
        "unmatched": unmatched,
        "remittance_ids": remittance_ids,
    }


async def resolve_unmatched_payment(
    session: AsyncSession, practice_id: uuid.UUID, unmatched_id: uuid.UUID
) -> UnmatchedERAPayment | None:
    """Mark an unmatched payment resolved (operator handled it manually)."""
    row = await session.scalar(
        select(UnmatchedERAPayment).where(
            UnmatchedERAPayment.id == unmatched_id,
            UnmatchedERAPayment.practice_id == practice_id,
            UnmatchedERAPayment.deleted_at.is_(None),
        )
    )
    if row is None:
        return None
    row.resolved = True
    row.resolved_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(row)
    return row
