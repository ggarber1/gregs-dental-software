from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.core.db import get_session_factory
from app.models.appointment_type import AppointmentType as AppointmentTypeModel
from app.schemas.generated import (
    ApiError,
    AppointmentType,
    CreateAppointmentType,
    Error,
    UpdateAppointmentType,
)

router = APIRouter(prefix="/api/v1/appointment-types", tags=["scheduling"])

_WRITE_ROLES: frozenset[str] = frozenset({"admin", "provider", "front_desk"})

_NOT_FOUND = {
    "code": "APPOINTMENT_TYPE_NOT_FOUND",
    "message": "Appointment type not found",
}


def _not_found_detail() -> dict[str, dict[str, str]]:
    return {"error": _NOT_FOUND}


# ── Guards ────────────────────────────────────────────────────────────────────


def _require_practice_scope(request: Request) -> uuid.UUID:
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


# ── Serialisation ─────────────────────────────────────────────────────────────


def _row_to_schema(row: AppointmentTypeModel) -> AppointmentType:
    return AppointmentType(
        id=row.id,
        practiceId=row.practice_id,
        name=row.name,
        durationMinutes=row.duration_minutes,
        color=row.color,
        defaultCdtCodes=row.default_cdt_codes or [],  # type: ignore[arg-type]
        isActive=row.is_active,
        displayOrder=row.display_order,
        createdAt=row.created_at,
        updatedAt=row.updated_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", status_code=201, response_model=AppointmentType)
async def create_appointment_type(
    body: CreateAppointmentType,
    request: Request,
) -> AppointmentType:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    row = AppointmentTypeModel(
        id=uuid.uuid4(),
        practice_id=practice_id,
        name=body.name,
        duration_minutes=body.duration_minutes,
        color=body.color or "#5B8DEF",
        default_cdt_codes=[
            str(c.root) if hasattr(c, "root") else str(c)
            for c in (body.default_cdt_codes or [])
        ],
        is_active=body.is_active if body.is_active is not None else True,
        display_order=body.display_order or 0,
    )

    async with get_session_factory()() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)

    return _row_to_schema(row)


@router.get("", response_model=list[AppointmentType])
async def list_appointment_types(request: Request) -> list[AppointmentType]:
    practice_id = _require_practice_scope(request)

    async with get_session_factory()() as session:
        rows = (
            await session.scalars(
                select(AppointmentTypeModel)
                .where(
                    AppointmentTypeModel.practice_id == practice_id,
                    AppointmentTypeModel.deleted_at.is_(None),
                )
                .order_by(AppointmentTypeModel.display_order.asc(), AppointmentTypeModel.name.asc())
            )
        ).all()

    return [_row_to_schema(r) for r in rows]


@router.get("/{appointment_type_id}", response_model=AppointmentType)
async def get_appointment_type(
    appointment_type_id: uuid.UUID,
    request: Request,
) -> AppointmentType:
    practice_id = _require_practice_scope(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(AppointmentTypeModel).where(
                AppointmentTypeModel.id == appointment_type_id,
                AppointmentTypeModel.practice_id == practice_id,
                AppointmentTypeModel.deleted_at.is_(None),
            )
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=_not_found_detail(),
        )

    return _row_to_schema(row)


@router.patch("/{appointment_type_id}", response_model=AppointmentType)
async def update_appointment_type(
    appointment_type_id: uuid.UUID,
    body: UpdateAppointmentType,
    request: Request,
) -> AppointmentType:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(AppointmentTypeModel).where(
                AppointmentTypeModel.id == appointment_type_id,
                AppointmentTypeModel.practice_id == practice_id,
                AppointmentTypeModel.deleted_at.is_(None),
            )
        )

        if row is None:
            raise HTTPException(
                status_code=404,
                detail=_not_found_detail(),
            )

        provided = body.model_fields_set
        field_map: dict[str, str] = {
            "name": "name",
            "duration_minutes": "duration_minutes",
            "color": "color",
            "is_active": "is_active",
            "display_order": "display_order",
        }

        for schema_field, model_field in field_map.items():
            if schema_field in provided:
                setattr(row, model_field, getattr(body, schema_field))

        if "default_cdt_codes" in provided:
            codes = body.default_cdt_codes or []
            row.default_cdt_codes = [
                str(c.root) if hasattr(c, "root") else str(c)
                for c in codes
            ]

        await session.commit()
        await session.refresh(row)

    return _row_to_schema(row)


@router.delete("/{appointment_type_id}", status_code=204)
async def delete_appointment_type(
    appointment_type_id: uuid.UUID,
    request: Request,
) -> None:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(AppointmentTypeModel).where(
                AppointmentTypeModel.id == appointment_type_id,
                AppointmentTypeModel.practice_id == practice_id,
                AppointmentTypeModel.deleted_at.is_(None),
            )
        )

        if row is None:
            raise HTTPException(
                status_code=404,
                detail=_not_found_detail(),
            )

        row.deleted_at = datetime.now(UTC)
        await session.commit()
