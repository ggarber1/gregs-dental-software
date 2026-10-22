"""AWS Lambda entry points for the scheduled workers.

Both functions run the API container image; each Lambda's image_config.command
selects one handler (see infra/terraform/modules/lambda-workers). Every invocation
gets a fresh DB engine: asyncio.run() creates a new event loop per call, and a
pooled engine from a previous (frozen) invocation would be bound to a closed loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.lambda_config import load_settings_from_ssm

logging.getLogger().setLevel(logging.INFO)
logger = logging.getLogger(__name__)

_config_loaded = False


def _ensure_config() -> None:
    global _config_loaded
    if not _config_loaded:
        load_settings_from_ssm()
        _config_loaded = True


async def _with_fresh_engine[T](
    job: Callable[[async_sessionmaker[AsyncSession]], Awaitable[T]],
) -> T:
    from app.core.db import dispose_engine, get_session_factory

    try:
        return await job(get_session_factory())
    finally:
        await dispose_engine()


def reminders(event: dict[str, Any], context: Any) -> dict[str, int]:
    """EventBridge every 15 min: send reminders that are due."""
    _ensure_config()
    from app.workers.reminder_worker import send_due_reminders

    summary = asyncio.run(_with_fresh_engine(send_due_reminders))
    return asdict(summary)


def risk_scoring(event: dict[str, Any], context: Any) -> dict[str, int]:
    """EventBridge nightly: score no-show risk for the next 7 days."""
    _ensure_config()
    from app.workers.risk_scoring_worker import score_upcoming_appointments

    scored = asyncio.run(_with_fresh_engine(score_upcoming_appointments))
    return {"scored": scored}
