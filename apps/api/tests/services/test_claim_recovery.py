"""Unit tests for resubmit_claim and write_off_claim."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.claims.service import ClaimSubmissionPrereqError, resubmit_claim, write_off_claim


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_claim(
    *,
    status: str,
    remittance_id: uuid.UUID | None = None,
    denial_codes: list[str] | None = None,
    adjustments: list[dict] | None = None,
    payer_ccn: str | None = None,
    submission_attempt: int = 1,
    submission_history: list[dict] | None = None,
) -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.practice_id = uuid.uuid4()
    c.appointment_id = uuid.uuid4()
    c.patient_id = uuid.uuid4()
    c.insurance_id = uuid.uuid4()
    c.provider_id = uuid.uuid4()
    c.status = status
    c.remittance_id = remittance_id
    c.denial_codes = denial_codes
    c.adjustments = adjustments
    c.payer_claim_control_number = payer_ccn
    c.submission_attempt = submission_attempt
    c.submission_history = submission_history
    c.submitted_at = datetime(2026, 6, 1, tzinfo=UTC)
    c.insurance_paid_cents = 0 if status == "denied" else None
    c.patient_responsibility_cents = None
    c.paid_at = datetime(2026, 6, 10, tzinfo=UTC) if status == "denied" else None
    c.insurance_reviewed_at = None
    return c


def _prereqs():
    """Minimal fake return value for _load_claim_prereqs."""
    return SimpleNamespace(
        appt=MagicMock(patient_id=uuid.uuid4(), provider_id=uuid.uuid4()),
        patient=MagicMock(),
        insurance=MagicMock(insurance_plan_id=uuid.uuid4(), relationship_to_insured="self"),
        plan=MagicMock(payer_id="CIGNA"),
        provider=MagicMock(),
        practice=MagicMock(
            billing_npi="1234567890",
            clearinghouse_submitter_id="S123",
            billing_tax_id_encrypted=b"enc",
            billing_address=None,
        ),
        billing_tax_id="123456789",
    )


# ── resubmit_claim ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resubmit_wrong_status_raises():
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=_make_claim(status="paid"))
    client = AsyncMock()

    with pytest.raises(ClaimSubmissionPrereqError) as exc_info:
        await resubmit_claim(
            session, uuid.uuid4(), uuid.uuid4(), client=client, usage_indicator="T", user_sub=None
        )

    assert exc_info.value.code == "CLAIM_NOT_RESUBMITTABLE"


@pytest.mark.asyncio
async def test_resubmit_clearinghouse_rejected_uses_frequency_code_1():
    """clearinghouse_rejected → carrier never saw it → resubmit as original."""
    claim = _make_claim(status="clearinghouse_rejected")
    session = AsyncMock()

    procedures_result = AsyncMock()
    procedures_result.all = MagicMock(return_value=[MagicMock()])
    session.scalars = AsyncMock(return_value=procedures_result)
    session.scalar = AsyncMock(return_value=claim)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    with (
        patch("app.services.claims.service._load_claim_prereqs", new=AsyncMock(return_value=_prereqs())),
        patch("app.services.claims.service.build_claim_input", return_value=MagicMock(total_charge_cents=10000)),
        patch("app.services.claims.service.validate_claim", return_value=MagicMock(valid=True)),
        patch("app.services.claims.service.decrypt", return_value="decrypted-tax-id"),
    ):
        client = AsyncMock()
        client.submit_dental_claim = AsyncMock(
            return_value=MagicMock(
                accepted=True,
                clearinghouse_claim_id="CH123",
                clearinghouse_status="accepted",
                errors=[],
                raw_request={},
                raw_response={},
            )
        )
        await resubmit_claim(
            session, claim.practice_id, claim.id, client=client, usage_indicator="T", user_sub=None
        )

    assert claim.claim_frequency_code == "1"
    assert claim.submission_attempt == 2


@pytest.mark.asyncio
async def test_resubmit_denied_uses_frequency_code_7_and_snapshots():
    """denied → corrected claim → frequency code 7, prior attempt snapshotted."""
    rem_id = uuid.uuid4()
    claim = _make_claim(
        status="denied",
        remittance_id=rem_id,
        denial_codes=["96"],
        payer_ccn="CCN999",
        submission_attempt=1,
        submission_history=None,
    )
    session = AsyncMock()

    procedures_result = AsyncMock()
    procedures_result.all = MagicMock(return_value=[MagicMock()])
    session.scalars = AsyncMock(return_value=procedures_result)
    session.scalar = AsyncMock(return_value=claim)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    with (
        patch("app.services.claims.service._load_claim_prereqs", new=AsyncMock(return_value=_prereqs())),
        patch("app.services.claims.service._reverse_claim_ledger_entries", new=AsyncMock()),
        patch("app.services.claims.service.build_claim_input", return_value=MagicMock(total_charge_cents=10000)),
        patch("app.services.claims.service.validate_claim", return_value=MagicMock(valid=True)),
        patch("app.services.claims.service.decrypt", return_value="decrypted-tax-id"),
    ):
        client = AsyncMock()
        client.submit_dental_claim = AsyncMock(
            return_value=MagicMock(
                accepted=True,
                clearinghouse_claim_id="CH456",
                clearinghouse_status="accepted",
                errors=[],
                raw_request={},
                raw_response={},
            )
        )
        await resubmit_claim(
            session, claim.practice_id, claim.id, client=client, usage_indicator="T", user_sub=None
        )

    assert claim.claim_frequency_code == "7"
    assert claim.submission_attempt == 2
    assert claim.remittance_id is None
    assert claim.denial_codes is None
    assert claim.paid_at is None
    assert claim.submission_history is not None
    assert claim.submission_history[0]["attempt"] == 1
    assert claim.submission_history[0]["status"] == "denied"
    assert claim.submission_history[0]["denialCodes"] == ["96"]


@pytest.mark.asyncio
async def test_resubmit_clearinghouse_rejects_sets_rejected_status():
    """Clearinghouse rejects on resubmit → status=clearinghouse_rejected, not submitted."""
    claim = _make_claim(status="clearinghouse_rejected")
    session = AsyncMock()

    procedures_result = AsyncMock()
    procedures_result.all = MagicMock(return_value=[MagicMock()])
    session.scalars = AsyncMock(return_value=procedures_result)
    session.scalar = AsyncMock(return_value=claim)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    with (
        patch("app.services.claims.service._load_claim_prereqs", new=AsyncMock(return_value=_prereqs())),
        patch("app.services.claims.service.build_claim_input", return_value=MagicMock(total_charge_cents=10000)),
        patch("app.services.claims.service.validate_claim", return_value=MagicMock(valid=True)),
        patch("app.services.claims.service.decrypt", return_value="decrypted-tax-id"),
    ):
        client = AsyncMock()
        client.submit_dental_claim = AsyncMock(
            return_value=MagicMock(
                accepted=False,
                clearinghouse_claim_id="CH999",
                clearinghouse_status="rejected",
                errors=["invalid NPI"],
                raw_request={},
                raw_response={},
            )
        )
        await resubmit_claim(
            session, claim.practice_id, claim.id, client=client, usage_indicator="T", user_sub=None
        )

    assert claim.status == "clearinghouse_rejected"
    assert claim.submission_errors == ["invalid NPI"]


# ── write_off_claim ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_write_off_wrong_status_raises():
    claim = _make_claim(status="paid")
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=claim)

    with pytest.raises(ClaimSubmissionPrereqError) as exc_info:
        await write_off_claim(session, uuid.uuid4(), uuid.uuid4(), memo=None, user_sub=None)

    assert exc_info.value.code == "CLAIM_NOT_WRITABLE"


@pytest.mark.asyncio
async def test_write_off_already_reviewed_raises():
    claim = _make_claim(status="denied")
    claim.insurance_reviewed_at = datetime(2026, 6, 20, tzinfo=UTC)
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=claim)

    with pytest.raises(ClaimSubmissionPrereqError) as exc_info:
        await write_off_claim(session, uuid.uuid4(), uuid.uuid4(), memo=None, user_sub=None)

    assert exc_info.value.code == "ALREADY_RESOLVED"


@pytest.mark.asyncio
async def test_write_off_posts_adjustment_and_marks_reviewed():
    claim = _make_claim(status="denied")
    claim.insurance_reviewed_at = None
    session = AsyncMock()
    # Two scalar calls: first returns claim, second returns remaining balance
    session.scalar = AsyncMock(side_effect=[claim, 50000])

    added_entries = []

    def _add(obj):
        added_entries.append(obj)

    session.add = _add
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    result = await write_off_claim(session, claim.practice_id, claim.id, memo=None, user_sub="staff-sub")

    assert claim.insurance_reviewed_at is not None
    assert len(added_entries) == 1
    entry = added_entries[0]
    assert entry.entry_type == "adjustment"
    assert entry.amount_cents == -50000
    assert entry.claim_id == claim.id
    assert entry.posted_by == "staff-sub"
    assert result is not None


@pytest.mark.asyncio
async def test_resubmit_submission_failed_uses_frequency_code_1():
    """submission_failed → carrier never saw it → resubmit as original (freq code 1)."""
    claim = _make_claim(status="submission_failed")
    session = AsyncMock()

    procedures_result = AsyncMock()
    procedures_result.all = MagicMock(return_value=[MagicMock()])
    session.scalars = AsyncMock(return_value=procedures_result)
    session.scalar = AsyncMock(return_value=claim)
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    with (
        patch("app.services.claims.service._load_claim_prereqs", new=AsyncMock(return_value=_prereqs())),
        patch("app.services.claims.service.build_claim_input", return_value=MagicMock(total_charge_cents=10000)),
        patch("app.services.claims.service.validate_claim", return_value=MagicMock(valid=True)),
        patch("app.services.claims.service.decrypt", return_value="decrypted-tax-id"),
    ):
        client = AsyncMock()
        client.submit_dental_claim = AsyncMock(
            return_value=MagicMock(
                accepted=True,
                clearinghouse_claim_id="CH789",
                clearinghouse_status="accepted",
                errors=[],
                raw_request={},
                raw_response={},
            )
        )
        await resubmit_claim(
            session, claim.practice_id, claim.id, client=client, usage_indicator="T", user_sub=None
        )

    assert claim.claim_frequency_code == "1"
    assert claim.submission_attempt == 2


@pytest.mark.asyncio
async def test_write_off_appealing_status():
    """appealing status is writable; adjustment is posted and claim marked reviewed."""
    claim = _make_claim(status="appealing")
    claim.insurance_reviewed_at = None
    session = AsyncMock()
    session.scalar = AsyncMock(side_effect=[claim, 30000])

    added_entries = []

    def _add(obj):
        added_entries.append(obj)

    session.add = _add
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    result = await write_off_claim(session, claim.practice_id, claim.id, memo=None, user_sub="staff-sub")

    assert claim.insurance_reviewed_at is not None
    assert len(added_entries) == 1
    assert added_entries[0].amount_cents == -30000
    assert result is not None


@pytest.mark.asyncio
async def test_write_off_zero_balance_skips_ledger_entry():
    claim = _make_claim(status="denied")
    claim.insurance_reviewed_at = None
    session = AsyncMock()
    session.scalar = AsyncMock(side_effect=[claim, 0])
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    result = await write_off_claim(session, claim.practice_id, claim.id, memo=None, user_sub=None)

    session.add.assert_not_called()
    assert claim.insurance_reviewed_at is not None
    assert result is None
