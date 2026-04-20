from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import ColumnElement, func, or_, select, update

from app.core.db import get_session_factory
from app.core.encryption import decrypt, encrypt
from app.models.patient import Patient as PatientModel
from app.schemas.generated import (
    ApiError,
    CreatePatient,
    Error,
    PaginationMeta,
    Patient,
    UpdatePatient,
)

router = APIRouter(prefix="/api/v1/patients", tags=["patients"])

_WRITE_ROLES: frozenset[str] = frozenset({"admin", "provider", "front_desk"})

_DOB_US_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$")


@dataclass(frozen=True)
class _ParsedSearch:
    raw: str
    phone_digits: str | None
    dob: date | None


def _parse_search(q: str) -> _ParsedSearch:
    raw = q.strip()
    digits = re.sub(r"\D", "", raw)
    phone_digits = digits if digits else None

    parsed_dob: date | None = None
    match = _DOB_US_RE.fullmatch(raw)
    if match is not None:
        month, day, year = (int(g) for g in match.groups())
        try:
            parsed_dob = date(year, month, day)
        except ValueError:
            parsed_dob = None

    return _ParsedSearch(raw=raw, phone_digits=phone_digits, dob=parsed_dob)


# ── Guards ────────────────────────────────────────────────────────────────────


def _require_practice_scope(request: Request) -> uuid.UUID:
    """Returns practice_id or raises 403."""
    practice_id = getattr(request.state.user, "practice_id", None)
    if practice_id is None:
        raise HTTPException(
            status_code=403,
            detail=ApiError(
                error=Error(
                    code="PRACTICE_SCOPE_REQUIRED",
                    message="X-Practice-ID header is required for this endpoint",
                )
            ).model_dump(by_alias=True),
        )
    assert isinstance(practice_id, uuid.UUID)
    return practice_id


def _require_write_role(request: Request) -> None:
    """Raises 403 if the user's role does not permit writes."""
    role = getattr(request.state.user, "role", None)
    if role not in _WRITE_ROLES:
        raise HTTPException(
            status_code=403,
            detail=ApiError(
                error=Error(
                    code="INSUFFICIENT_ROLE",
                    message="Your role does not permit this action",
                )
            ).model_dump(by_alias=True),
        )


# ── Serialisation helpers ─────────────────────────────────────────────────────


def _row_to_schema(row: PatientModel, *, include_ssn: bool = False) -> Patient:
    ssn: str | None = None
    if include_ssn and row.ssn_encrypted:
        ssn = decrypt(row.ssn_encrypted)

    return Patient(
        id=row.id,
        practiceId=row.practice_id,
        firstName=row.first_name,
        lastName=row.last_name,
        dateOfBirth=row.date_of_birth,
        sex=row.sex,  # type: ignore[arg-type]
        maritalStatus=row.marital_status,  # type: ignore[arg-type]
        lastXrayDate=row.last_xray_date,
        phone=row.phone,
        email=row.email,
        addressLine1=row.address_line1,
        addressLine2=row.address_line2,
        city=row.city,
        state=row.state,
        zip=row.zip,
        ssn=ssn,
        emergencyContactName=row.emergency_contact_name,
        emergencyContactPhone=row.emergency_contact_phone,
        occupation=row.occupation,
        employer=row.employer,
        referralSource=row.referral_source,
        allergies=row.allergies or [],
        medicalAlerts=row.medical_alerts or [],
        medications=row.medications or [],
        dentalSymptoms=row.dental_symptoms or [],
        lastDentalVisit=row.last_dental_visit,
        previousDentist=row.previous_dentist,
        doctorNotes=row.doctor_notes,
        smsOptOut=row.sms_opt_out,
        deletedAt=row.deleted_at,
        createdAt=row.created_at,
        updatedAt=row.updated_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", status_code=201, response_model=Patient)
async def create_patient(body: CreatePatient, request: Request) -> Patient:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    # Validate the client isn't accidentally sending a mismatched practiceId.
    if body.practice_id is not None and body.practice_id != practice_id:
        raise HTTPException(
            status_code=400,
            detail=ApiError(
                error=Error(
                    code="PRACTICE_ID_MISMATCH",
                    message="Body practiceId does not match authenticated practice scope",
                )
            ).model_dump(by_alias=True),
        )

    ssn_encrypted: bytes | None = None
    if body.ssn is not None:
        ssn_encrypted = encrypt(body.ssn)

    row = PatientModel(
        id=uuid.uuid4(),
        practice_id=practice_id,
        first_name=body.first_name,
        last_name=body.last_name,
        date_of_birth=body.date_of_birth,
        sex=body.sex,
        marital_status=body.marital_status,
        emergency_contact_name=body.emergency_contact_name,
        emergency_contact_phone=body.emergency_contact_phone,
        occupation=body.occupation,
        employer=body.employer,
        referral_source=body.referral_source,
        phone=body.phone,
        email=str(body.email) if body.email else None,
        address_line1=body.address_line1,
        address_line2=body.address_line2,
        city=body.city,
        state=body.state,
        zip=body.zip,
        ssn_encrypted=ssn_encrypted,
        allergies=body.allergies or [],
        medical_alerts=body.medical_alerts or [],
        medications=body.medications or [],
        dental_symptoms=body.dental_symptoms or [],
        doctor_notes=body.doctor_notes,
        sms_opt_out=body.sms_opt_out or False,
    )

    async with get_session_factory()() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)

    return _row_to_schema(row, include_ssn=True)


@router.get("", response_model=dict)
async def list_patients(
    request: Request,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    practice_id = _require_practice_scope(request)

    if page < 1:
        page = 1
    if not (1 <= page_size <= 100):
        page_size = min(max(page_size, 1), 100)

    base_filter = [
        PatientModel.practice_id == practice_id,
        PatientModel.deleted_at.is_(None),
    ]

    if q:
        parsed = _parse_search(q)
        term = f"%{parsed.raw}%"
        clauses: list[ColumnElement[bool]] = [
            PatientModel.first_name.ilike(term),
            PatientModel.last_name.ilike(term),
            func.concat(PatientModel.first_name, " ", PatientModel.last_name).ilike(term),
            PatientModel.email.ilike(term),
        ]
        if parsed.phone_digits:
            clauses.append(
                func.regexp_replace(PatientModel.phone, r"\D", "", "g").like(
                    f"%{parsed.phone_digits}%"
                )
            )
        if parsed.dob is not None:
            clauses.append(PatientModel.date_of_birth == parsed.dob)
        base_filter.append(or_(*clauses))

    async with get_session_factory()() as session:
        total: int = (
            await session.scalar(select(func.count()).select_from(PatientModel).where(*base_filter))
            or 0
        )

        rows = (
            await session.scalars(
                select(PatientModel)
                .where(*base_filter)
                .order_by(PatientModel.last_name.asc(), PatientModel.first_name.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()

    total_pages = max(1, math.ceil(total / page_size))
    meta = PaginationMeta(
        page=page,
        pageSize=page_size,
        total=total,
        totalPages=total_pages,
    )

    return {
        "data": [_row_to_schema(r, include_ssn=False) for r in rows],
        "meta": meta.model_dump(by_alias=True),
    }


@router.get("/{patient_id}", response_model=Patient)
async def get_patient(patient_id: uuid.UUID, request: Request) -> Patient:
    practice_id = _require_practice_scope(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(PatientModel).where(
                PatientModel.id == patient_id,
                PatientModel.practice_id == practice_id,
                PatientModel.deleted_at.is_(None),
            )
        )

        if row is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "PATIENT_NOT_FOUND", "message": "Patient not found"}},
            )

        # Update access tracking — fire-and-forget style (same session, still fast).
        # Use synchronize_session=False to prevent ORM from expiring `row` attributes
        # (particularly server-computed columns like updated_at) before we serialize.
        user_sub = getattr(request.state.user, "sub", None)
        await session.execute(
            update(PatientModel)
            .where(PatientModel.id == patient_id)
            .values(
                last_accessed_by=user_sub,
                last_accessed_at=datetime.now(UTC),
            )
            .execution_options(synchronize_session=False)
        )
        await session.commit()

    return _row_to_schema(row, include_ssn=True)


@router.patch("/{patient_id}", response_model=Patient)
async def update_patient(
    patient_id: uuid.UUID,
    body: UpdatePatient,
    request: Request,
) -> Patient:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(PatientModel).where(
                PatientModel.id == patient_id,
                PatientModel.practice_id == practice_id,
                PatientModel.deleted_at.is_(None),
            )
        )

        if row is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "PATIENT_NOT_FOUND", "message": "Patient not found"}},
            )

        # Apply only the fields that were explicitly provided in the request.
        provided = body.model_fields_set

        field_map: dict[str, str] = {
            "first_name": "first_name",
            "last_name": "last_name",
            "date_of_birth": "date_of_birth",
            "sex": "sex",
            "marital_status": "marital_status",
            "emergency_contact_name": "emergency_contact_name",
            "emergency_contact_phone": "emergency_contact_phone",
            "occupation": "occupation",
            "employer": "employer",
            "referral_source": "referral_source",
            "phone": "phone",
            "address_line1": "address_line1",
            "address_line2": "address_line2",
            "city": "city",
            "state": "state",
            "zip": "zip",
            "allergies": "allergies",
            "medical_alerts": "medical_alerts",
            "medications": "medications",
            "dental_symptoms": "dental_symptoms",
            "last_xray_date": "last_xray_date",
            "last_dental_visit": "last_dental_visit",
            "previous_dentist": "previous_dentist",
            "doctor_notes": "doctor_notes",
            "sms_opt_out": "sms_opt_out",
        }

        for schema_field, model_field in field_map.items():
            if schema_field in provided:
                setattr(row, model_field, getattr(body, schema_field))

        if "email" in provided:
            row.email = str(body.email) if body.email else None

        if "ssn" in provided:
            row.ssn_encrypted = encrypt(body.ssn) if body.ssn else None

        await session.commit()
        await session.refresh(row)

    return _row_to_schema(row, include_ssn=True)


@router.delete("/{patient_id}", status_code=204)
async def delete_patient(patient_id: uuid.UUID, request: Request) -> None:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(PatientModel).where(
                PatientModel.id == patient_id,
                PatientModel.practice_id == practice_id,
                PatientModel.deleted_at.is_(None),
            )
        )

        if row is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "PATIENT_NOT_FOUND", "message": "Patient not found"}},
            )

        row.deleted_at = datetime.now(UTC)
        await session.commit()
