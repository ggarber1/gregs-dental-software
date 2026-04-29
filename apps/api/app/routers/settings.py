from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.models.practice import Practice as PracticeModel
from app.schemas.generated import ApiError, Error, ReminderSettings, UpdateReminderSettings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

_MAX_WINDOWS = 5
_MIN_HOURS = 1
_MAX_HOURS = 168  # 1 week


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


def _require_admin_role(request: Request) -> None:
    role = getattr(request.state.user, "role", None)
    if role != "admin":
        raise HTTPException(
            status_code=403,
            detail=ApiError(
                error=Error(
                    code="INSUFFICIENT_ROLE",
                    message="Only practice admins can modify settings",
                )
            ).model_dump(by_alias=True),
        )


async def _get_practice(session: AsyncSession, practice_id: uuid.UUID) -> PracticeModel:
    practice = await session.scalar(
        select(PracticeModel).where(PracticeModel.id == practice_id)
    )
    if practice is None:
        raise HTTPException(
            status_code=404,
            detail=ApiError(
                error=Error(code="PRACTICE_NOT_FOUND", message="Practice not found")
            ).model_dump(by_alias=True),
        )
    return practice


@router.get("/reminders", response_model=ReminderSettings)
async def get_reminder_settings(request: Request) -> ReminderSettings:
    practice_id = _require_practice_scope(request)

    async with get_session_factory()() as session:
        practice = await _get_practice(session, practice_id)

    return ReminderSettings(reminderHours=practice.reminder_hours)


@router.put("/reminders", response_model=ReminderSettings)
async def update_reminder_settings(
    body: UpdateReminderSettings,
    request: Request,
) -> ReminderSettings:
    practice_id = _require_practice_scope(request)
    _require_admin_role(request)

    # Validate: each value in range, deduplicate, sort descending
    raw = body.reminder_hours
    if not raw:
        raise HTTPException(
            status_code=422,
            detail=ApiError(
                error=Error(
                    code="INVALID_REMINDER_HOURS",
                    message="At least one reminder window is required",
                )
            ).model_dump(by_alias=True),
        )

    invalid = [h for h in raw if not (_MIN_HOURS <= h <= _MAX_HOURS)]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=ApiError(
                error=Error(
                    code="INVALID_REMINDER_HOURS",
                    message=(
                        f"Each reminder window must be between {_MIN_HOURS}"
                        f" and {_MAX_HOURS} hours"
                    ),
                )
            ).model_dump(by_alias=True),
        )

    hours = sorted(set(raw), reverse=True)
    if len(hours) > _MAX_WINDOWS:
        raise HTTPException(
            status_code=422,
            detail=ApiError(
                error=Error(
                    code="INVALID_REMINDER_HOURS",
                    message=f"Maximum {_MAX_WINDOWS} reminder windows allowed",
                )
            ).model_dump(by_alias=True),
        )

    async with get_session_factory()() as session:
        practice = await _get_practice(session, practice_id)
        practice.reminder_hours = hours
        await session.commit()

    logger.info("Updated reminder_hours for practice %s to %s", practice_id, hours)
    return ReminderSettings(reminderHours=hours)
