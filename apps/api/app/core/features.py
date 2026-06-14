from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.practice import Practice
from app.schemas.generated import ApiError, Error


async def require_feature(
    session: AsyncSession,
    practice_id: uuid.UUID,
    flag: str,
    *,
    practice: object | None = None,
) -> None:
    """Raise 403 unless practice.features[flag] is truthy.

    Pass an already-loaded `practice` to avoid a redundant query when the caller
    already has the row (e.g. an endpoint that also needs billing/clearinghouse fields).
    """
    # A missing/inaccessible practice row is treated as "feature not enabled" (403),
    # not 404: callers always resolve practice scope + membership upstream, and we
    # avoid leaking practice existence. Denying is the safe default here.
    if practice is None:
        practice = await session.scalar(select(Practice).where(Practice.id == practice_id))
    enabled = bool(practice and (getattr(practice, "features", None) or {}).get(flag))
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
