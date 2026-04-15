from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.core.db import get_session_factory
from app.models.operatory import Operatory as OperatoryModel
from app.schemas.generated import (
    ApiError,
    CreateOperatoryBody,
    Error,
    OperatoryResponse,
    UpdateOperatoryBody,
)

router = APIRouter(prefix="/api/v1/operatories", tags=["scheduling"])

_WRITE_ROLES: frozenset[str] = frozenset({"admin", "provider", "front_desk"})


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


def _row_to_schema(row: OperatoryModel) -> OperatoryResponse:
    return OperatoryResponse(
        id=row.id,
        practiceId=row.practice_id,
        name=row.name,
        color=row.color,
        isActive=row.is_active,
        displayOrder=row.display_order,
        createdAt=row.created_at,
        updatedAt=row.updated_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", status_code=201, response_model=OperatoryResponse)
async def create_operatory(body: CreateOperatoryBody, request: Request) -> OperatoryResponse:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    row = OperatoryModel(
        id=uuid.uuid4(),
        practice_id=practice_id,
        name=body.name,
        color=body.color or "#7BC67E",
        is_active=body.is_active if body.is_active is not None else True,
        display_order=body.display_order or 0,
    )

    async with get_session_factory()() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)

    return _row_to_schema(row)


@router.get("", response_model=list[OperatoryResponse])
async def list_operatories(request: Request) -> list[OperatoryResponse]:
    practice_id = _require_practice_scope(request)

    async with get_session_factory()() as session:
        rows = (
            await session.scalars(
                select(OperatoryModel)
                .where(
                    OperatoryModel.practice_id == practice_id,
                    OperatoryModel.deleted_at.is_(None),
                )
                .order_by(OperatoryModel.display_order.asc(), OperatoryModel.name.asc())
            )
        ).all()

    return [_row_to_schema(r) for r in rows]


@router.get("/{operatory_id}", response_model=OperatoryResponse)
async def get_operatory(operatory_id: uuid.UUID, request: Request) -> OperatoryResponse:
    practice_id = _require_practice_scope(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(OperatoryModel).where(
                OperatoryModel.id == operatory_id,
                OperatoryModel.practice_id == practice_id,
                OperatoryModel.deleted_at.is_(None),
            )
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "OPERATORY_NOT_FOUND", "message": "Operatory not found"}},
        )

    return _row_to_schema(row)


@router.patch("/{operatory_id}", response_model=OperatoryResponse)
async def update_operatory(
    operatory_id: uuid.UUID,
    body: UpdateOperatoryBody,
    request: Request,
) -> OperatoryResponse:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(OperatoryModel).where(
                OperatoryModel.id == operatory_id,
                OperatoryModel.practice_id == practice_id,
                OperatoryModel.deleted_at.is_(None),
            )
        )

        if row is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "OPERATORY_NOT_FOUND", "message": "Operatory not found"}},
            )

        provided = body.model_fields_set
        field_map: dict[str, str] = {
            "name": "name",
            "color": "color",
            "is_active": "is_active",
            "display_order": "display_order",
        }

        for schema_field, model_field in field_map.items():
            if schema_field in provided:
                setattr(row, model_field, getattr(body, schema_field))

        await session.commit()
        await session.refresh(row)

    return _row_to_schema(row)


@router.delete("/{operatory_id}", status_code=204)
async def delete_operatory(operatory_id: uuid.UUID, request: Request) -> None:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(OperatoryModel).where(
                OperatoryModel.id == operatory_id,
                OperatoryModel.practice_id == practice_id,
                OperatoryModel.deleted_at.is_(None),
            )
        )

        if row is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "OPERATORY_NOT_FOUND", "message": "Operatory not found"}},
            )

        row.deleted_at = datetime.now(UTC)
        await session.commit()
