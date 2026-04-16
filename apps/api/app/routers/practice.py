from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.core.db import get_session_factory
from app.models.practice import Practice as PracticeModel
from app.schemas.generated import ApiError, Error, Features, Practice

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/practice", tags=["practice"])


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


def _row_to_schema(row: PracticeModel) -> Practice:
    return Practice(
        id=row.id,
        name=row.name,
        timezone=row.timezone,
        phone=row.phone,
        addressLine1=row.address_line1,
        addressLine2=row.address_line2,
        city=row.city,
        state=row.state,
        zip=row.zip,
        features=Features(**row.features) if row.features else None,
        createdAt=row.created_at,
        updatedAt=row.updated_at,
    )


@router.get("", response_model=Practice)
async def get_practice(request: Request) -> Practice:
    practice_id = _require_practice_scope(request)

    async with get_session_factory()() as session:
        row = await session.scalar(
            select(PracticeModel).where(PracticeModel.id == practice_id)
        )

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=ApiError(
                error=Error(
                    code="PRACTICE_NOT_FOUND",
                    message="Practice not found",
                )
            ).model_dump(by_alias=True),
        )

    return _row_to_schema(row)
