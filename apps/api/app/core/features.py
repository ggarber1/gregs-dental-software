from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.practice import Practice
from app.schemas.generated import ApiError, Error


def feature_enabled(practice: object | None, flag: str) -> bool:
    """True if practice.features[flag] is truthy. Soft check — never raises.

    Use this for side effects that should be skipped (not 403'd) when a feature is off.
    """
    return bool(practice and (getattr(practice, "features", None) or {}).get(flag))


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
    if not feature_enabled(practice, flag):
        raise HTTPException(
            status_code=403,
            detail=ApiError(
                error=Error(
                    code="FEATURE_NOT_ENABLED",
                    message=f"The '{flag}' feature is not enabled for this practice",
                )
            ).model_dump(by_alias=True),
        )
