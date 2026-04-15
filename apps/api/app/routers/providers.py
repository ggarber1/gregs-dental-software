from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.core.db import get_session_factory
from app.models.provider import Provider as ProviderModel
from app.schemas.generated import (
    ApiError,
    CreateProviderBody,
    Error,
    ProviderResponse,
    UpdateProviderBody,
)

router = APIRouter(prefix="/api/v1/providers", tags=["scheduling"])

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


def _row_to_schema(row: ProviderModel) -> ProviderResponse:
    return ProviderResponse(
        id=row.id,
        practiceId=row.practice_id,
        fullName=row.full_name,
        npi=row.npi,
        providerType=row.provider_type,  # type: ignore[arg-type]
        licenseNumber=row.license_number,
        specialty=row.specialty,
        color=row.color,
        isActive=row.is_active,
        displayOrder=row.display_order,
        createdAt=row.created_at,
        updatedAt=row.updated_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", status_code=201, response_model=ProviderResponse)
async def create_provider(body: CreateProviderBody, request: Request) -> ProviderResponse:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    row = ProviderModel(
        id=uuid.uuid4(),
        practice_id=practice_id,
        full_name=body.full_name,
        npi=body.npi,
        provider_type=body.provider_type,
        license_number=body.license_number,
        specialty=body.specialty,
        color=body.color or "#4F86C6",
        is_active=body.is_active if body.is_active is not None else True,
        display_order=body.display_order or 0,
    )

    async with get_session_factory()() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)

    return _row_to_schema(row)


@router.get("", response_model=list[ProviderResponse])
async def list_providers(request: Request) -> list[ProviderResponse]:
    practice_id = _require_practice_scope(request)

    async with get_session_factory()() as session:
        rows = (
            await session.scalars(
                select(ProviderModel)
                .where(
                    ProviderModel.practice_id == practice_id,
                    ProviderModel.deleted_at.is_(None),
                )
                .order_by(ProviderModel.display_order.asc(), ProviderModel.full_name.asc())
            )
        ).all()

    return [_row_to_schema(r) for r in rows]


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(provider_id: uuid.UUID, request: Request) -> ProviderResponse:
    practice_id = _require_practice_scope(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(ProviderModel).where(
                ProviderModel.id == provider_id,
                ProviderModel.practice_id == practice_id,
                ProviderModel.deleted_at.is_(None),
            )
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "PROVIDER_NOT_FOUND", "message": "Provider not found"}},
        )

    return _row_to_schema(row)


@router.patch("/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: uuid.UUID,
    body: UpdateProviderBody,
    request: Request,
) -> ProviderResponse:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(ProviderModel).where(
                ProviderModel.id == provider_id,
                ProviderModel.practice_id == practice_id,
                ProviderModel.deleted_at.is_(None),
            )
        )

        if row is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "PROVIDER_NOT_FOUND", "message": "Provider not found"}},
            )

        provided = body.model_fields_set
        field_map: dict[str, str] = {
            "full_name": "full_name",
            "npi": "npi",
            "provider_type": "provider_type",
            "license_number": "license_number",
            "specialty": "specialty",
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


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(provider_id: uuid.UUID, request: Request) -> None:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(ProviderModel).where(
                ProviderModel.id == provider_id,
                ProviderModel.practice_id == practice_id,
                ProviderModel.deleted_at.is_(None),
            )
        )

        if row is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "PROVIDER_NOT_FOUND", "message": "Provider not found"}},
            )

        row.deleted_at = datetime.now(UTC)
        await session.commit()
