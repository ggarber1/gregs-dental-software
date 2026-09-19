"""Integration tests for statement generation (service + HTTP)."""

from __future__ import annotations

import datetime
import uuid
from datetime import UTC, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry
from app.models.patient import Patient
from app.models.patient_statement import PatientStatement
from app.models.practice import Practice
from app.models.user import PracticeUser, User
from app.services.statements import service as statements

pytestmark = pytest.mark.integration

_NOW = datetime.datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
_FAKE_PDF = b"%PDF-1.7 fake statement"

# Patch targets — both are imported by name into the service module.
_P_PDF = "app.services.statements.service.html_to_pdf"
_P_SEND = "app.services.statements.service.send_email_with_attachment"

# Auth patch targets (mirrored from test_ledger_endpoints.py)
_P_HEADER = "app.middleware.auth.jwt.get_unverified_header"
_P_KEY = "app.middleware.auth._get_public_key"
_P_DECODE = "app.middleware.auth.jwt.decode"


async def _seed(
    session: AsyncSession,
    *,
    ledger_enabled: bool = True,
    role: str = "admin",
    email: str | None = "pat@example.test",
):
    practice = Practice(
        id=uuid.uuid4(),
        name="Statement Test Practice",
        phone="+16175550100",
        address_line1="1 Main St",
        city="Boston",
        state="MA",
        zip="02110",
        features={"billing_ledger": ledger_enabled},
    )
    session.add(practice)

    cognito_sub = f"stmt-sub-{uuid.uuid4().hex}"
    user = User(
        id=uuid.uuid4(),
        cognito_sub=cognito_sub,
        email=f"stmt-staff-{uuid.uuid4().hex[:6]}@test.local",
        full_name="Statement Staff",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    session.add(PracticeUser(practice_id=practice.id, user_id=user.id, role=role, is_active=True))

    patient = Patient(
        id=uuid.uuid4(),
        practice_id=practice.id,
        first_name="Pat",
        last_name="Statement",
        date_of_birth=datetime.date(1990, 1, 1),
        email=email,
        address_line1="9 Elm Rd",
        city="Cambridge",
        state="MA",
        zip="02139",
    )
    session.add(patient)
    await session.commit()
    return practice, user, cognito_sub, patient


async def _post(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    *,
    entry_type: str = "charge",
    amount_cents: int,
    days_ago: int = 1,
    reverses: uuid.UUID | None = None,
) -> LedgerEntry:
    entry = LedgerEntry(
        id=uuid.uuid4(),
        practice_id=practice_id,
        patient_id=patient_id,
        entry_type=entry_type,
        amount_cents=amount_cents,
        reverses_entry_id=reverses,
        posted_at=_NOW - timedelta(days=days_ago),
    )
    session.add(entry)
    await session.commit()
    return entry


async def _statement_rows(session: AsyncSession, patient_id: uuid.UUID) -> list[PatientStatement]:
    rows = await session.scalars(
        select(PatientStatement)
        .where(PatientStatement.patient_id == patient_id)
        .order_by(PatientStatement.generated_at)
    )
    return list(rows)


def _decoded(user, cognito_sub, groups=("admin",)):
    return {"sub": cognito_sub, "email": user.email, "cognito:groups": list(groups)}


def _auth_patches(decoded):
    return (
        patch(_P_HEADER, return_value={"kid": "test-kid"}),
        patch(_P_KEY, new=AsyncMock(return_value="fake-public-key")),
        patch(_P_DECODE, return_value=decoded),
    )


# ── Service ───────────────────────────────────────────────────────────────────


class TestCreateStatementService:
    async def test_email_sends_pdf_and_records_delivered(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=10000, days_ago=45)
        await _post(
            db_session, practice.id, patient.id, entry_type="patient_payment", amount_cents=-2500
        )

        send = AsyncMock(return_value="ses-msg-1")
        with patch(_P_PDF, return_value=_FAKE_PDF), patch(_P_SEND, send):
            row = await statements.create_statement(
                db_session,
                practice.id,
                patient.id,
                delivery_method="email",
                generated_by="user-sub-1",
                now=_NOW,
            )

        assert row.delivery_method == "email"
        assert row.balance_cents == 7500
        assert row.aging_snapshot == {"b0_30": 0, "b31_60": 10000, "b61_90": 0, "b90_plus": 0}
        assert row.generated_at == _NOW
        assert row.delivered_at == _NOW
        assert row.generated_by == "user-sub-1"
        kwargs = send.call_args.kwargs
        assert kwargs["to"] == "pat@example.test"
        assert kwargs["subject"] == "Statement from Statement Test Practice"
        assert kwargs["from_name"] == "Statement Test Practice"
        assert kwargs["attachment_bytes"] == _FAKE_PDF
        assert kwargs["attachment_filename"] == "statement-2026-09-18.pdf"
        assert "$75.00" in kwargs["text_body"]
        assert len(await _statement_rows(db_session, patient.id)) == 1

    async def test_download_records_without_sending(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)

        send = AsyncMock()
        with patch(_P_PDF) as pdf, patch(_P_SEND, send):
            row = await statements.create_statement(
                db_session,
                practice.id,
                patient.id,
                delivery_method="download",
                generated_by="user-sub-1",
                now=_NOW,
            )

        assert row.delivery_method == "download"
        assert row.delivered_at is None
        send.assert_not_called()
        pdf.assert_not_called()

    async def test_zero_balance_rejected(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)
        await _post(
            db_session, practice.id, patient.id, entry_type="patient_payment", amount_cents=-600
        )

        with pytest.raises(statements.NoOutstandingBalanceError):
            await statements.create_statement(
                db_session, practice.id, patient.id, delivery_method="download", generated_by="u"
            )
        assert await _statement_rows(db_session, patient.id) == []

    async def test_email_without_address_rejected(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session, email=None)
        await _post(db_session, practice.id, patient.id, amount_cents=600)

        with pytest.raises(statements.NoPatientEmailError):
            await statements.create_statement(
                db_session, practice.id, patient.id, delivery_method="email", generated_by="u"
            )
        assert await _statement_rows(db_session, patient.id) == []

    async def test_ses_failure_records_nothing(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)

        with (
            patch(_P_PDF, return_value=_FAKE_PDF),
            patch(_P_SEND, AsyncMock(side_effect=RuntimeError("SES send_raw_email failed"))),
            pytest.raises(statements.StatementDeliveryError),
        ):
            await statements.create_statement(
                db_session, practice.id, patient.id, delivery_method="email", generated_by="u"
            )
        assert await _statement_rows(db_session, patient.id) == []

    async def test_email_opt_out_is_ignored_for_statements(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        patient.email_opt_out = True
        await db_session.commit()
        await _post(db_session, practice.id, patient.id, amount_cents=600)

        send = AsyncMock(return_value="ses-msg-2")
        with patch(_P_PDF, return_value=_FAKE_PDF), patch(_P_SEND, send):
            await statements.create_statement(
                db_session, practice.id, patient.id, delivery_method="email", generated_by="u"
            )
        send.assert_awaited_once()

    async def test_wrong_practice_is_lookup_error(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        other, _, _, _ = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)

        with pytest.raises(LookupError):
            await statements.create_statement(
                db_session, other.id, patient.id, delivery_method="download", generated_by="u"
            )

    async def test_soft_deleted_patient_is_lookup_error(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)
        patient.deleted_at = _NOW
        await db_session.commit()

        with pytest.raises(LookupError):
            await statements.create_statement(
                db_session, practice.id, patient.id, delivery_method="download", generated_by="u"
            )

    async def test_dev_no_send_still_records_delivered_at(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)

        with patch(_P_PDF, return_value=_FAKE_PDF), patch(_P_SEND, AsyncMock(return_value=None)):
            row = await statements.create_statement(
                db_session,
                practice.id,
                patient.id,
                delivery_method="email",
                generated_by="u",
                now=_NOW,
            )
        assert row.delivered_at == _NOW


class TestListAndRenderService:
    async def test_list_is_most_recent_first_and_practice_scoped(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        other, _, _, _ = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)
        with patch(_P_PDF, return_value=_FAKE_PDF), patch(_P_SEND, AsyncMock(return_value="m")):
            first = await statements.create_statement(
                db_session,
                practice.id,
                patient.id,
                delivery_method="download",
                generated_by="u",
                now=_NOW - timedelta(days=1),
            )
            second = await statements.create_statement(
                db_session,
                practice.id,
                patient.id,
                delivery_method="email",
                generated_by="u",
                now=_NOW,
            )

        mine = await statements.list_statements(db_session, practice.id, patient.id)
        theirs = await statements.list_statements(db_session, other.id, patient.id)

        assert [s.id for s in mine] == [second.id, first.id]
        assert theirs == []
        assert await statements.get_statement(db_session, other.id, patient.id, first.id) is None
        found = await statements.get_statement(db_session, practice.id, patient.id, first.id)
        assert found is not None and found.id == first.id

    async def test_render_uses_live_ledger_and_excludes_reversals(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=1000, days_ago=2)
        wrong = await _post(db_session, practice.id, patient.id, amount_cents=9000, days_ago=3)
        await _post(db_session, practice.id, patient.id, amount_cents=-9000, reverses=wrong.id)

        captured: dict[str, str] = {}

        def fake_pdf(html: str) -> bytes:
            captured["html"] = html
            return _FAKE_PDF

        with patch(_P_PDF, side_effect=fake_pdf):
            pdf = await statements.render_statement_pdf(
                db_session, practice.id, patient.id, statement_date=_NOW.date()
            )

        assert pdf == _FAKE_PDF
        assert "$10.00" in captured["html"]
        assert "$90.00" not in captured["html"]
        assert "Pat Statement" in captured["html"]

    async def test_render_without_require_balance_works_after_full_payment(
        self, db_session: AsyncSession
    ):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)
        await _post(
            db_session, practice.id, patient.id, entry_type="patient_payment", amount_cents=-600
        )

        with patch(_P_PDF, return_value=_FAKE_PDF):
            pdf = await statements.render_statement_pdf(
                db_session, practice.id, patient.id, statement_date=_NOW.date()
            )
        assert pdf == _FAKE_PDF

    async def test_render_preview_requires_balance(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        with pytest.raises(statements.NoOutstandingBalanceError):
            await statements.render_statement_pdf(
                db_session,
                practice.id,
                patient.id,
                statement_date=_NOW.date(),
                require_balance=True,
            )
