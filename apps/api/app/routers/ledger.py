from __future__ import annotations

import uuid
from datetime import UTC
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.core.db import get_session_factory
from app.core.features import require_feature
from app.models.ledger_entry import LedgerEntry as LedgerEntryModel
from app.models.patient import Patient as PatientModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import (
    AddAdjustmentRequest,
    ApiError,
    Entry,
    Error,
    LedgerEntry,
    PatientLedger,
    RecordPaymentRequest,
    ReverseEntryRequest,
)
from app.services.ledger.balance import get_ledger
from app.services.ledger.posting import (
    add_manual_adjustment,
    record_patient_payment,
    reverse_entry,
)

router = APIRouter(prefix="/api/v1", tags=["ledger"])

_FEATURE = "billing_ledger"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True),
    )


def _entry_fields(row: LedgerEntryModel, running_balance: int) -> dict[str, Any]:
    """camelCase dict for one ledger entry (coerced into the generated Entry/LedgerEntry)."""
    return {
        "id": row.id,
        "practiceId": row.practice_id,
        "patientId": row.patient_id,
        "entryType": row.entry_type,
        "amountCents": row.amount_cents,
        "runningBalanceCents": running_balance,
        "appointmentId": row.appointment_id,
        "appointmentProcedureId": row.appointment_procedure_id,
        "claimId": row.claim_id,
        "remittanceId": row.remittance_id,
        "reversesEntryId": row.reverses_entry_id,
        "paymentMethod": row.payment_method,
        "memo": row.memo,
        "postedBy": row.posted_by,
        "postedAt": row.posted_at.replace(tzinfo=UTC),
    }


def _entry_model(row: LedgerEntryModel, running_balance: int) -> LedgerEntry:
    # Single-entry mutation responses (payment/adjustment/reversal) pass
    # running_balance=amount_cents as a placeholder — they do not recompute the
    # accumulated balance. The authoritative runningBalanceCents comes only from
    # GET /patients/{id}/ledger, which annotates every entry via get_ledger().
    return LedgerEntry(**_entry_fields(row, running_balance))


async def _require_patient(
    session: Any, practice_id: uuid.UUID, patient_id: uuid.UUID
) -> None:
    found = await session.scalar(
        select(PatientModel.id).where(
            PatientModel.id == patient_id,
            PatientModel.practice_id == practice_id,
            PatientModel.deleted_at.is_(None),
        )
    )
    if found is None:
        raise _err(404, "PATIENT_NOT_FOUND", "Patient not found in this practice")


@router.get("/patients/{patient_id}/ledger", response_model=PatientLedger)
async def get_patient_ledger(patient_id: uuid.UUID, request: Request) -> PatientLedger:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        await _require_patient(session, practice_id, patient_id)
        annotated, balance = await get_ledger(session, practice_id, patient_id)
        return PatientLedger(
            patientId=patient_id,
            balanceCents=balance,
            entries=[Entry(**_entry_fields(row, rb)) for row, rb in annotated],
        )


@router.post("/patients/{patient_id}/payments", status_code=201, response_model=LedgerEntry)
async def post_payment(
    patient_id: uuid.UUID, body: RecordPaymentRequest, request: Request
) -> LedgerEntry:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", None) or "system"
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        await _require_patient(session, practice_id, patient_id)
        try:
            entry = await record_patient_payment(
                session,
                practice_id,
                patient_id,
                amount_cents=body.amount_cents,
                payment_method=body.payment_method,
                memo=body.memo,
                posted_by=user_sub,
            )
        except ValueError as exc:
            raise _err(422, "INVALID_PAYMENT", str(exc)) from exc
        return _entry_model(entry, entry.amount_cents)


@router.post("/patients/{patient_id}/adjustments", status_code=201, response_model=LedgerEntry)
async def post_adjustment(
    patient_id: uuid.UUID, body: AddAdjustmentRequest, request: Request
) -> LedgerEntry:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", None) or "system"
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        await _require_patient(session, practice_id, patient_id)
        try:
            entry = await add_manual_adjustment(
                session,
                practice_id,
                patient_id,
                amount_cents=body.amount_cents,
                memo=body.memo,
                posted_by=user_sub,
            )
        except ValueError as exc:
            raise _err(422, "INVALID_ADJUSTMENT", str(exc)) from exc
        return _entry_model(entry, entry.amount_cents)


@router.post("/ledger/entries/{entry_id}/reverse", response_model=LedgerEntry)
async def post_reverse(
    entry_id: uuid.UUID, body: ReverseEntryRequest, request: Request
) -> LedgerEntry:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", None) or "system"
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        reversal = await reverse_entry(
            session, practice_id, entry_id, posted_by=user_sub, memo=body.memo
        )
        if reversal is None:
            raise _err(
                422,
                "CANNOT_REVERSE",
                "Entry not found, already reversed, or is itself a reversal",
            )
        return _entry_model(reversal, reversal.amount_cents)
