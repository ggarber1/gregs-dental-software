from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.practice import Practice
from app.schemas.generated import ApiError, Error


async def require_feature(session: AsyncSession, practice_id: uuid.UUID, flag: str) -> None:
    """Raise 403 unless practice.features[flag] is truthy."""
    practice = await session.scalar(select(Practice).where(Practice.id == practice_id))
    enabled = bool(practice and (practice.features or {}).get(flag))
    if not enabled:
        raise HTTPException(
            status_code=403,
            detail=ApiError(
                error=Error(
                    code="FEATURE_NOT_ENABLED",
                    message=f"The '{flag}' feature is not enabled for this practice",
                )
            ).model_dump(by_alias=True),
        )
