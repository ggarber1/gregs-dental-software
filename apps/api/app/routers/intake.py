from __future__ import annotations

import json
import logging
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.encryption import decrypt, encrypt
from app.models.intake_form import IntakeForm
from app.models.patient import Patient as PatientModel
from app.models.practice import Practice
from app.routers.patients import _require_practice_scope, _require_write_role, _row_to_schema
from app.schemas.generated import (
    ApiError,
    Error,
    IntakeFormDetail,
    IntakeFormSummary,
    IntakeFormTokenInfo,
    Patient,
    SendIntakeForm,
    SendIntakeFormResponse,
    SubmitIntakeForm,
)
from app.services import sms

logger = logging.getLogger(__name__)

_INTAKE_TTL_HOURS = 72

# ── Public router ─────────────────────────────────────────────────────────────
# Routes under /intake/ are bypassed by CognitoAuthMiddleware and
# IdempotencyMiddleware — no auth or Idempotency-Key header required.

public_router = APIRouter(tags=["intake-public"])


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _expire_if_due(form: IntakeForm, now: datetime) -> bool:
    """Return True if the form should be treated as expired. Does NOT flush."""
    return form.status == "pending" and form.expires_at.replace(tzinfo=UTC) < now


@public_router.get("/intake/form/{token}", response_model=IntakeFormTokenInfo)
async def get_intake_form_public(token: str) -> IntakeFormTokenInfo:
    """Validate a token and return the minimum context for the form greeting.

    Returns 404 if token unknown, 410 Gone if already completed or expired.
    Lazily transitions pending → expired if the TTL has passed.
    """
    now = datetime.now(UTC)

    async with get_session_factory()() as session:
        form = await session.scalar(
            select(IntakeForm).where(IntakeForm.token == token)
        )
        if form is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "INTAKE_NOT_FOUND", "message": "Intake form not found"}},
            )

        if _expire_if_due(form, now):
            await session.execute(
                update(IntakeForm)
                .where(IntakeForm.id == form.id)
                .values(status="expired", updated_at=now)
            )
            await session.commit()
            raise HTTPException(
                status_code=410,
                detail={
                    "error": {
                        "code": "INTAKE_EXPIRED",
                        "message": "This intake form link has expired",
                    }
                },
            )

        if form.status != "pending":
            code = "INTAKE_COMPLETED" if form.status == "completed" else "INTAKE_EXPIRED"
            raise HTTPException(
                status_code=410,
                detail={
                    "error": {"code": code, "message": "This intake form link is no longer active"}
                },
            )

        # Fetch practice name and patient first name for the greeting
        practice = await session.scalar(
            select(Practice).where(Practice.id == form.practice_id)
        )
        patient = await session.scalar(
            select(PatientModel).where(PatientModel.id == form.patient_id)
        )

    practice_name = practice.name if practice else "Your dental practice"
    patient_first_name = patient.first_name if patient else "Patient"

    return IntakeFormTokenInfo(
        practiceName=practice_name,
        patientFirstName=patient_first_name,
    )


@public_router.post("/intake/form/{token}/submit", status_code=204)
async def submit_intake_form(token: str, body: SubmitIntakeForm, request: Request) -> None:
    """Submit a completed intake form.

    Single-use: returns 410 if the token has already been used or expired.
    Encrypts the full form payload with AES-256-GCM before storage.
    """
    if not body.hipaa_consent_accepted:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "HIPAA_CONSENT_REQUIRED",
                    "message": "HIPAA consent must be accepted to submit the form",
                }
            },
        )

    now = datetime.now(UTC)

    async with get_session_factory()() as session:
        form = await session.scalar(
            select(IntakeForm).where(IntakeForm.token == token)
        )
        if form is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "INTAKE_NOT_FOUND", "message": "Intake form not found"}},
            )

        if _expire_if_due(form, now):
            await session.execute(
                update(IntakeForm)
                .where(IntakeForm.id == form.id)
                .values(status="expired", updated_at=now)
            )
            await session.commit()
            raise HTTPException(
                status_code=410,
                detail={
                    "error": {
                        "code": "INTAKE_EXPIRED",
                        "message": "This intake form link has expired",
                    }
                },
            )

        if form.status != "pending":
            code = "INTAKE_COMPLETED" if form.status == "completed" else "INTAKE_EXPIRED"
            raise HTTPException(
                status_code=410,
                detail={
                    "error": {"code": code, "message": "This intake form link is no longer active"}
                },
            )

        # Encrypt the full form payload. model_dump_json serialises date/datetime
        # objects to ISO strings automatically.
        json_payload = body.model_dump_json(by_alias=True)
        encrypted = encrypt(json_payload)

        await session.execute(
            update(IntakeForm)
            .where(IntakeForm.id == form.id)
            .values(
                status="completed",
                responses_encrypted=encrypted,
                submission_ip=_client_ip(request),
                submission_user_agent=request.headers.get("User-Agent"),
                updated_at=now,
            )
        )
        await session.commit()


# ── Staff router ──────────────────────────────────────────────────────────────
# All routes here require a valid Cognito JWT + X-Practice-ID header.

staff_router = APIRouter(prefix="/api/v1/intake", tags=["intake"])


def _form_to_summary(form: IntakeForm) -> IntakeFormSummary:
    return IntakeFormSummary(
        id=form.id,
        patientId=form.patient_id,
        status=form.status,  # type: ignore[arg-type]
        expiresAt=form.expires_at.replace(tzinfo=UTC),
        createdAt=form.created_at.replace(tzinfo=UTC),
        createdBy=form.created_by,
    )


@staff_router.post("/send", status_code=201, response_model=SendIntakeFormResponse)
async def send_intake_form(body: SendIntakeForm, request: Request) -> SendIntakeFormResponse:
    """Create a single-use intake form token and send it to the patient via SMS."""
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_id = getattr(request.state.user, "user_id", None)

    async with get_session_factory()() as session:
        patient = await session.scalar(
            select(PatientModel).where(
                PatientModel.id == body.patient_id,
                PatientModel.practice_id == practice_id,
                PatientModel.deleted_at.is_(None),
            )
        )
        if patient is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="PATIENT_NOT_FOUND", message="Patient not found")
                ).model_dump(by_alias=True),
            )

        if not patient.phone:
            raise HTTPException(
                status_code=422,
                detail=ApiError(
                    error=Error(
                        code="PATIENT_NO_PHONE",
                        message="Patient does not have a phone number on file",
                    )
                ).model_dump(by_alias=True),
            )

        if patient.sms_opt_out:
            raise HTTPException(
                status_code=422,
                detail=ApiError(
                    error=Error(
                        code="PATIENT_SMS_OPT_OUT",
                        message="Patient has opted out of SMS communications",
                    )
                ).model_dump(by_alias=True),
            )

        practice = await session.scalar(
            select(Practice).where(Practice.id == practice_id)
        )

        token = secrets.token_hex(32)
        expires_at = datetime.now(UTC) + timedelta(hours=_INTAKE_TTL_HOURS)

        form = IntakeForm(
            id=uuid.uuid4(),
            practice_id=practice_id,
            patient_id=body.patient_id,
            token=token,
            status="pending",
            expires_at=expires_at,
            created_by=user_id or uuid.uuid4(),
        )
        session.add(form)
        await session.commit()
        await session.refresh(form)

    settings = get_settings()
    practice_name = practice.name if practice else "Your dental practice"
    form_url = f"{settings.app_url}/intake/{token}"
    message = (
        f"Hi {patient.first_name}, {practice_name} has sent you a patient intake form. "
        f"Please complete it before your appointment: {form_url}\n\n"
        f"This link expires in {_INTAKE_TTL_HOURS} hours and can only be used once."
    )

    try:
        await sms.send_sms(to=patient.phone, body=message)
    except Exception:
        logger.warning(
            "SMS delivery failed for intake form %s (patient %s) — form was created",
            form.id,
            body.patient_id,
            exc_info=True,
        )

    return SendIntakeFormResponse(
        intakeFormId=form.id,
        expiresAt=form.expires_at.replace(tzinfo=UTC),
        formUrl=form_url,
    )


@staff_router.get("", response_model=list[IntakeFormSummary])
async def list_intake_forms(
    request: Request,
    patient_id: uuid.UUID | None = None,
    status: str | None = None,
) -> list[IntakeFormSummary]:
    """List intake forms for the practice, optionally filtered by patient or status."""
    practice_id = _require_practice_scope(request)

    filters = [IntakeForm.practice_id == practice_id]
    if patient_id is not None:
        filters.append(IntakeForm.patient_id == patient_id)
    if status is not None:
        filters.append(IntakeForm.status == status)

    async with get_session_factory()() as session:
        rows = (
            await session.scalars(
                select(IntakeForm)
                .where(*filters)
                .order_by(IntakeForm.created_at.desc())
            )
        ).all()

    return [_form_to_summary(r) for r in rows]


@staff_router.get("/{intake_form_id}", response_model=IntakeFormDetail)
async def get_intake_form_detail(intake_form_id: uuid.UUID, request: Request) -> IntakeFormDetail:
    """Return intake form details including decrypted responses (if completed).

    Reading decrypted responses is audited by the AuditLogMiddleware.
    """
    practice_id = _require_practice_scope(request)

    async with get_session_factory()() as session:
        form = await session.scalar(
            select(IntakeForm).where(
                IntakeForm.id == intake_form_id,
                IntakeForm.practice_id == practice_id,
            )
        )

    if form is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "INTAKE_NOT_FOUND", "message": "Intake form not found"}},
        )

    responses: dict[str, Any] | None = None
    if form.responses_encrypted:
        responses = json.loads(decrypt(form.responses_encrypted))

    return IntakeFormDetail(
        id=form.id,
        patientId=form.patient_id,
        status=form.status,  # type: ignore[arg-type]
        expiresAt=form.expires_at.replace(tzinfo=UTC),
        createdAt=form.created_at.replace(tzinfo=UTC),
        createdBy=form.created_by,
        responses=responses,  # type: ignore[arg-type]
    )


@staff_router.post("/{intake_form_id}/apply", response_model=Patient)
async def apply_intake_form(intake_form_id: uuid.UUID, request: Request) -> Patient:
    """Apply completed intake form data to the linked patient record.

    Maps the patient-submitted fields to the patient model. Insurance and
    clinical detail fields remain in the encrypted response for reference.
    """
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        form = await session.scalar(
            select(IntakeForm).where(
                IntakeForm.id == intake_form_id,
                IntakeForm.practice_id == practice_id,
            )
        )
        if form is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "INTAKE_NOT_FOUND", "message": "Intake form not found"}},
            )

        if form.status != "completed":
            raise HTTPException(
                status_code=422,
                detail=ApiError(
                    error=Error(
                        code="INTAKE_NOT_COMPLETED",
                        message="Cannot apply an intake form that has not been completed",
                    )
                ).model_dump(by_alias=True),
            )

        if not form.responses_encrypted:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "INTAKE_NO_RESPONSES",
                        "message": "Intake form has no responses",
                    }
                },
            )

        patient = await session.scalar(
            select(PatientModel).where(
                PatientModel.id == form.patient_id,
                PatientModel.practice_id == practice_id,
                PatientModel.deleted_at.is_(None),
            )
        )
        if patient is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "PATIENT_NOT_FOUND", "message": "Patient not found"}},
            )

        data: dict[str, Any] = json.loads(decrypt(form.responses_encrypted))

        # Apply demographic and contact fields
        if data.get("firstName"):
            patient.first_name = data["firstName"]
        if data.get("lastName"):
            patient.last_name = data["lastName"]
        if data.get("dateOfBirth"):
            patient.date_of_birth = date.fromisoformat(data["dateOfBirth"])
        if data.get("sex"):
            patient.sex = data["sex"]
        if data.get("phone"):
            patient.phone = data["phone"]
        if data.get("email"):
            patient.email = data["email"]
        if data.get("addressLine1") is not None:
            patient.address_line1 = data["addressLine1"] or None
        if data.get("addressLine2") is not None:
            patient.address_line2 = data["addressLine2"] or None
        if data.get("city") is not None:
            patient.city = data["city"] or None
        if data.get("state") is not None:
            patient.state = data["state"] or None
        if data.get("zip") is not None:
            patient.zip = data["zip"] or None

        # Clinical flags
        if data.get("allergies"):
            patient.allergies = data["allergies"]

        # Combine medical conditions and medications into medical_alerts
        medical_alerts: list[str] = []
        if data.get("medicalConditions"):
            medical_alerts.extend(data["medicalConditions"])
        if data.get("medications"):
            medical_alerts.extend(data["medications"])
        if medical_alerts:
            patient.medical_alerts = medical_alerts

        # SMS opt-in → invert to sms_opt_out
        if "smsOptIn" in data:
            patient.sms_opt_out = not data["smsOptIn"]

        patient.updated_at = datetime.now(UTC)

        await session.commit()
        await session.refresh(patient)

    return _row_to_schema(patient, include_ssn=False)
