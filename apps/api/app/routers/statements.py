"""Patient billing statements (Module 8b).

PDF bytes are only ever served from GET endpoints. IdempotencyMiddleware buffers and
text-decodes every mutation response body, so a POST that returned a PDF would reach
the client empty. The download flow is therefore POST (record) → GET (bytes).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from app.core.db import get_session_factory
from app.core.features import require_feature
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import ApiError, Error, GenerateStatementRequest, PatientStatement
from app.services.statements import service as statements

router = APIRouter(prefix="/api/v1", tags=["statements"])
_FEATURE = "billing_ledger"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True),
    )


def _statement_to_dict(row: Any) -> dict[str, Any]:
    snap = row.aging_snapshot
    return {
        "id": row.id,
        "practiceId": row.practice_id,
        "patientId": row.patient_id,
        "deliveryMethod": row.delivery_method,
        "balanceCents": row.balance_cents,
        "buckets": {
            "b0_30": snap.get("b0_30", 0),
            "b31_60": snap.get("b31_60", 0),
            "b61_90": snap.get("b61_90", 0),
            "b90_plus": snap.get("b90_plus", 0),
        },
        "generatedAt": row.generated_at,
        "deliveredAt": row.delivered_at,
        "generatedBy": row.generated_by,
    }


def _pdf_response(pdf: bytes, *, filename: str, inline: bool) -> Response:
    disposition = "inline" if inline else "attachment"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.get("/patients/{patient_id}/statements", response_model=list[PatientStatement])
async def list_patient_statements(
    request: Request, patient_id: uuid.UUID
) -> list[PatientStatement]:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        rows = await statements.list_statements(session, practice_id, patient_id)
        return [PatientStatement.model_validate(_statement_to_dict(r)) for r in rows]


@router.post("/patients/{patient_id}/statements", response_model=PatientStatement, status_code=201)
async def create_patient_statement(
    request: Request, patient_id: uuid.UUID, body: GenerateStatementRequest
) -> PatientStatement:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", None) or "system"
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        try:
            row = await statements.create_statement(
                session,
                practice_id,
                patient_id,
                delivery_method=body.delivery_method.value,
                generated_by=user_sub,
            )
        except LookupError as exc:
            raise _err(404, "PATIENT_NOT_FOUND", "Patient not found in this practice") from exc
        except statements.NoOutstandingBalanceError as exc:
            raise _err(400, "NO_OUTSTANDING_BALANCE", str(exc)) from exc
        except statements.NoPatientEmailError as exc:
            raise _err(400, "PATIENT_HAS_NO_EMAIL", str(exc)) from exc
        except statements.StatementDeliveryError as exc:
            raise _err(502, "EMAIL_DELIVERY_FAILED", "Statement email could not be sent") from exc
        return PatientStatement.model_validate(_statement_to_dict(row))


@router.get("/patients/{patient_id}/statements/preview", response_class=Response)
async def preview_patient_statement(request: Request, patient_id: uuid.UUID) -> Response:
    """Current statement as PDF. Records nothing."""
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        today = datetime.now(UTC).date()
        try:
            pdf = await statements.render_statement_pdf(
                session, practice_id, patient_id, statement_date=today, require_balance=True
            )
        except LookupError as exc:
            raise _err(404, "PATIENT_NOT_FOUND", "Patient not found in this practice") from exc
        except statements.NoOutstandingBalanceError as exc:
            raise _err(400, "NO_OUTSTANDING_BALANCE", str(exc)) from exc
    return _pdf_response(pdf, filename=statements.statement_filename(today), inline=True)


@router.get("/patients/{patient_id}/statements/{statement_id}/pdf", response_class=Response)
async def download_patient_statement(
    request: Request, patient_id: uuid.UUID, statement_id: uuid.UUID
) -> Response:
    """PDF for a recorded statement, regenerated from the live ledger and stamped with
    the recorded generation date."""
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        row = await statements.get_statement(session, practice_id, patient_id, statement_id)
        if row is None:
            raise _err(404, "STATEMENT_NOT_FOUND", "Statement not found")
        statement_date = row.generated_at.date()
        try:
            pdf = await statements.render_statement_pdf(
                session,
                practice_id,
                patient_id,
                statement_date=statement_date,
                require_balance=False,
            )
        except LookupError as exc:
            raise _err(404, "PATIENT_NOT_FOUND", "Patient not found in this practice") from exc
    return _pdf_response(pdf, filename=statements.statement_filename(statement_date), inline=False)
