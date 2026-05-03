from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.models.medical_history_version import MedicalHistoryVersion as MedicalHistoryVersionModel
from app.models.patient import Patient as PatientModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import (
    Allergy,
    ApiError,
    Condition,
    CreateMedicalHistory,
    Error,
    Flags,
    Item,
    MedicalHistoryHistoryResponse,
    MedicalHistoryVersion,
    Medication,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/patients/{patient_id}/medical-history",
    tags=["medical-history"],
)

# ── Flag inference keywords ───────────────────────────────────────────────────

_BLOOD_THINNER_KW: frozenset[str] = frozenset(
    {"warfarin", "coumadin", "xarelto", "eliquis", "heparin"}
)
_BISPHOSPHONATE_KW: frozenset[str] = frozenset(
    {"bisphosphonate", "fosamax", "boniva", "prolia", "actonel"}
)
_HEART_CONDITION_KW: frozenset[str] = frozenset(
    {"heart", "cardiac", "arrhythmia", "afib", "murmur"}
)
_DIABETES_KW: frozenset[str] = frozenset({"diabetes", "diabetic", "insulin", "metformin"})
_PACEMAKER_KW: frozenset[str] = frozenset({"pacemaker", "icd", "defibrillator"})


def _kw_match(names: set[str], keywords: frozenset[str]) -> bool:
    return any(kw in name for name in names for kw in keywords)


def _compute_flags(
    conditions: list[Any],
    allergies: list[Any],
    client_flags: Flags | None,
) -> dict[str, bool]:
    condition_names = {c.name.lower() for c in conditions}
    allergy_names = {a.name.lower() for a in allergies}
    all_names = condition_names | allergy_names

    computed = {
        "flag_blood_thinners": _kw_match(condition_names, _BLOOD_THINNER_KW),
        "flag_bisphosphonates": _kw_match(condition_names, _BISPHOSPHONATE_KW),
        "flag_heart_condition": _kw_match(condition_names, _HEART_CONDITION_KW),
        "flag_diabetes": _kw_match(condition_names, _DIABETES_KW),
        "flag_pacemaker": _kw_match(condition_names, _PACEMAKER_KW),
        "flag_latex_allergy": _kw_match(all_names, frozenset({"latex"})),
    }

    if client_flags is not None:
        if client_flags.flag_blood_thinners:
            computed["flag_blood_thinners"] = True
        if client_flags.flag_bisphosphonates:
            computed["flag_bisphosphonates"] = True
        if client_flags.flag_heart_condition:
            computed["flag_heart_condition"] = True
        if client_flags.flag_diabetes:
            computed["flag_diabetes"] = True
        if client_flags.flag_pacemaker:
            computed["flag_pacemaker"] = True
        if client_flags.flag_latex_allergy:
            computed["flag_latex_allergy"] = True

    return computed


# ── Serialisation helpers ─────────────────────────────────────────────────────


def _row_to_schema(row: MedicalHistoryVersionModel) -> MedicalHistoryVersion:
    allergies = [Allergy.model_validate(a) for a in (row.allergies or [])]
    medications = [Medication.model_validate(m) for m in (row.medications or [])]
    conditions = [Condition.model_validate(c) for c in (row.conditions or [])]
    flags = Flags(
        flagBloodThinners=row.flag_blood_thinners,
        flagBisphosphonates=row.flag_bisphosphonates,
        flagHeartCondition=row.flag_heart_condition,
        flagDiabetes=row.flag_diabetes,
        flagPacemaker=row.flag_pacemaker,
        flagLatexAllergy=row.flag_latex_allergy,
    )
    return MedicalHistoryVersion(
        id=row.id,
        practiceId=row.practice_id,
        patientId=row.patient_id,
        versionNumber=row.version_number,
        recordedBy=row.recorded_by,
        recordedAt=row.recorded_at.replace(tzinfo=UTC),
        allergies=allergies,
        medications=medications,
        conditions=conditions,
        flags=flags,
        additionalNotes=row.additional_notes,
        createdAt=row.created_at.replace(tzinfo=UTC),
        updatedAt=row.updated_at.replace(tzinfo=UTC),
    )


def _row_to_summary(row: MedicalHistoryVersionModel) -> Item:
    flags = Flags(
        flagBloodThinners=row.flag_blood_thinners,
        flagBisphosphonates=row.flag_bisphosphonates,
        flagHeartCondition=row.flag_heart_condition,
        flagDiabetes=row.flag_diabetes,
        flagPacemaker=row.flag_pacemaker,
        flagLatexAllergy=row.flag_latex_allergy,
    )
    return Item(
        id=row.id,
        versionNumber=row.version_number,
        recordedBy=row.recorded_by,
        recordedAt=row.recorded_at.replace(tzinfo=UTC),
        allergyCount=len(row.allergies or []),
        medicationCount=len(row.medications or []),
        conditionCount=len(row.conditions or []),
        flags=flags,
    )


async def _phi_audit(
    session: AsyncSession,
    row_id: uuid.UUID,
    user_sub: str | None,
) -> None:
    await session.execute(
        update(MedicalHistoryVersionModel)
        .where(MedicalHistoryVersionModel.id == row_id)
        .values(
            last_accessed_by=user_sub,
            last_accessed_at=datetime.now(UTC),
        )
        .execution_options(synchronize_session=False)
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=MedicalHistoryVersion)
async def get_latest_medical_history(
    patient_id: uuid.UUID,
    request: Request,
) -> MedicalHistoryVersion:
    practice_id = _require_practice_scope(request)
    user_sub = getattr(request.state.user, "sub", None)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(MedicalHistoryVersionModel)
            .where(
                MedicalHistoryVersionModel.patient_id == patient_id,
                MedicalHistoryVersionModel.practice_id == practice_id,
                MedicalHistoryVersionModel.deleted_at.is_(None),
            )
            .order_by(MedicalHistoryVersionModel.version_number.desc())
            .limit(1)
        )

        if row is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(
                        code="MEDICAL_HISTORY_NOT_FOUND",
                        message="No medical history recorded for this patient",
                    )
                ).model_dump(by_alias=True),
            )

        await _phi_audit(session, row.id, user_sub)
        await session.commit()

    return _row_to_schema(row)


@router.get("/history", response_model=MedicalHistoryHistoryResponse)
async def list_medical_history(
    patient_id: uuid.UUID,
    request: Request,
    page: int = 1,
    page_size: int = 20,
) -> MedicalHistoryHistoryResponse:
    practice_id = _require_practice_scope(request)
    user_sub = getattr(request.state.user, "sub", None)

    if page < 1:
        page = 1
    page_size = min(max(page_size, 1), 100)
    offset = (page - 1) * page_size

    async with get_session_factory()() as session:
        total = await session.scalar(
            select(func.count())
            .select_from(MedicalHistoryVersionModel)
            .where(
                MedicalHistoryVersionModel.patient_id == patient_id,
                MedicalHistoryVersionModel.practice_id == practice_id,
                MedicalHistoryVersionModel.deleted_at.is_(None),
            )
        ) or 0

        rows = (
            await session.scalars(
                select(MedicalHistoryVersionModel)
                .where(
                    MedicalHistoryVersionModel.patient_id == patient_id,
                    MedicalHistoryVersionModel.practice_id == practice_id,
                    MedicalHistoryVersionModel.deleted_at.is_(None),
                )
                .order_by(MedicalHistoryVersionModel.version_number.desc())
                .offset(offset)
                .limit(page_size)
            )
        ).all()

        if rows:
            for row in rows:
                await _phi_audit(session, row.id, user_sub)
            await session.commit()

    return MedicalHistoryHistoryResponse(
        items=[_row_to_summary(r) for r in rows],
        total=total,
        page=page,
        pageSize=page_size,
    )


@router.get("/{version_id}", response_model=MedicalHistoryVersion)
async def get_medical_history_version(
    patient_id: uuid.UUID,
    version_id: uuid.UUID,
    request: Request,
) -> MedicalHistoryVersion:
    practice_id = _require_practice_scope(request)
    user_sub = getattr(request.state.user, "sub", None)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(MedicalHistoryVersionModel).where(
                MedicalHistoryVersionModel.id == version_id,
                MedicalHistoryVersionModel.patient_id == patient_id,
                MedicalHistoryVersionModel.practice_id == practice_id,
                MedicalHistoryVersionModel.deleted_at.is_(None),
            )
        )

        if row is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(
                        code="MEDICAL_HISTORY_VERSION_NOT_FOUND",
                        message="Medical history version not found",
                    )
                ).model_dump(by_alias=True),
            )

        await _phi_audit(session, row.id, user_sub)
        await session.commit()

    return _row_to_schema(row)


@router.post("", status_code=201, response_model=MedicalHistoryVersion)
async def create_medical_history_version(
    patient_id: uuid.UUID,
    body: CreateMedicalHistory,
    request: Request,
) -> MedicalHistoryVersion:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_id = getattr(request.state.user, "user_id", None)

    allergies = body.allergies or []
    medications = body.medications or []
    conditions = body.conditions or []

    flags = _compute_flags(conditions, allergies, body.flags)

    allergies_json = [a.model_dump(by_alias=True, exclude_none=True) for a in allergies]
    medications_json = [m.model_dump(by_alias=True, exclude_none=True) for m in medications]
    conditions_json = [c.model_dump(by_alias=True, exclude_none=True) for c in conditions]

    async with get_session_factory()() as session:
        patient = await session.scalar(
            select(PatientModel)
            .where(
                PatientModel.id == patient_id,
                PatientModel.practice_id == practice_id,
                PatientModel.deleted_at.is_(None),
            )
            .with_for_update()
        )

        if patient is None:
            raise HTTPException(
                status_code=404,
                detail=ApiError(
                    error=Error(code="PATIENT_NOT_FOUND", message="Patient not found")
                ).model_dump(by_alias=True),
            )

        max_version = await session.scalar(
            select(func.max(MedicalHistoryVersionModel.version_number)).where(
                MedicalHistoryVersionModel.patient_id == patient_id
            )
        )
        new_version_number = (max_version or 0) + 1

        now = datetime.now(UTC)
        row = MedicalHistoryVersionModel(
            id=uuid.uuid4(),
            practice_id=practice_id,
            patient_id=patient_id,
            version_number=new_version_number,
            recorded_by=user_id or uuid.uuid4(),
            recorded_at=now,
            allergies=allergies_json,
            medications=medications_json,
            conditions=conditions_json,
            flag_blood_thinners=flags["flag_blood_thinners"],
            flag_bisphosphonates=flags["flag_bisphosphonates"],
            flag_heart_condition=flags["flag_heart_condition"],
            flag_diabetes=flags["flag_diabetes"],
            flag_pacemaker=flags["flag_pacemaker"],
            flag_latex_allergy=flags["flag_latex_allergy"],
            additional_notes=body.additional_notes,
        )
        session.add(row)

        patient.allergies = [a["name"] for a in allergies_json]
        patient.medical_alerts = [c["name"] for c in conditions_json]
        patient.medications = [m["name"] for m in medications_json]
        patient.updated_at = now

        await session.commit()
        await session.refresh(row)

    logger.info(
        "Medical history version created: patient_id=%s version=%d user_id=%s",
        patient_id,
        new_version_number,
        user_id,
    )

    return _row_to_schema(row)
