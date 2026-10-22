"""Nightly no-show risk scoring for appointments in the next 7 days.

Runs on AWS Lambda (app.workers.lambda_handlers.risk_scoring, EventBridge nightly)
or locally with `python -m app.workers.risk_scoring_worker` (one pass).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.appointment import Appointment
from app.services.risk_scoring import PatientAppointmentHistory, compute_risk_score

logger = logging.getLogger(__name__)

_WINDOW_DAYS = 7
_UPCOMING_STATUSES = ("scheduled", "confirmed", "checked_in", "in_chair")
_HISTORY_STATUSES = ("completed", "no_show", "cancelled", "checked_in", "in_chair")


async def score_upcoming_appointments(session_factory: async_sessionmaker[AsyncSession]) -> int:
    """Score every upcoming appointment in the window; returns how many were scored."""
    now = datetime.now(UTC)
    window_end = now + timedelta(days=_WINDOW_DAYS)
    logger.info("Risk scoring started: window %s → %s", now.isoformat(), window_end.isoformat())

    async with session_factory() as session:
        appts = (
            await session.scalars(
                select(Appointment).where(
                    Appointment.start_time >= now,
                    Appointment.start_time <= window_end,
                    Appointment.status.in_(_UPCOMING_STATUSES),
                    Appointment.deleted_at.is_(None),
                )
            )
        ).all()
        if not appts:
            logger.info("No upcoming appointments to score")
            return 0

        patient_ids = {a.patient_id for a in appts if a.patient_id is not None}
        history_map = await _batch_fetch_histories(session, patient_ids, cutoff=now)
        computed_at = datetime.now(UTC)
        rows = []
        for appt in appts:
            history = (
                history_map.get(appt.patient_id) if appt.patient_id is not None else None
            ) or PatientAppointmentHistory(0, 0, 0)
            lead_hours = (appt.start_time - now).total_seconds() / 3600
            is_confirmed = appt.status in ("confirmed", "checked_in", "in_chair")
            rows.append(
                {
                    "id": appt.id,
                    "no_show_risk": compute_risk_score(appt, history, is_confirmed, lead_hours),
                    "no_show_risk_computed_at": computed_at,
                }
            )

        # One executemany (ORM bulk UPDATE by primary key), not a query per appointment.
        await session.execute(update(Appointment), rows)
        await session.commit()

    logger.info(
        "Risk scoring complete: %d appointments scored, %d high-risk",
        len(rows),
        sum(1 for r in rows if r["no_show_risk"] == "high"),
    )
    return len(rows)


async def _batch_fetch_histories(
    session: Any,
    patient_ids: set[uuid.UUID],
    cutoff: datetime,
) -> dict[uuid.UUID, PatientAppointmentHistory]:
    if not patient_ids:
        return {}

    rows = (
        await session.execute(
            select(
                Appointment.patient_id,
                func.count().label("total"),
                func.sum(case((Appointment.status == "no_show", 1), else_=0)).label(
                    "no_show_count"
                ),
                func.sum(case((Appointment.status == "cancelled", 1), else_=0)).label(
                    "cancel_count"
                ),
            )
            .where(
                Appointment.patient_id.in_(patient_ids),
                Appointment.status.in_(_HISTORY_STATUSES),
                Appointment.start_time < cutoff,
                Appointment.deleted_at.is_(None),
            )
            .group_by(Appointment.patient_id)
        )
    ).all()

    return {
        row.patient_id: PatientAppointmentHistory(
            total=row.total or 0,
            no_show_count=row.no_show_count or 0,
            cancel_count=row.cancel_count or 0,
        )
        for row in rows
    }


async def _main() -> None:
    from app.core.db import dispose_engine, get_session_factory

    try:
        await score_upcoming_appointments(get_session_factory())
    finally:
        await dispose_engine()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
