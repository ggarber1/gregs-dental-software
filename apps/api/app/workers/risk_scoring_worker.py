"""EventBridge-triggered Lambda: scores no-show risk for upcoming appointments."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import case, func, select, update

from app.core.db import get_session_factory
from app.models.appointment import Appointment
from app.models.appointment_reminder import AppointmentReminder
from app.services.reminders import stage_reminder_jobs
from app.services.risk_scoring import PatientAppointmentHistory, compute_risk_score

logger = logging.getLogger(__name__)

_WINDOW_DAYS = 7
_EXTRA_REMINDER_HOURS = 4
_UPCOMING_STATUSES = ("scheduled", "confirmed", "checked_in", "in_chair")
_HISTORY_STATUSES = ("completed", "no_show", "cancelled", "checked_in", "in_chair")


def handler(event: dict[str, Any], context: Any) -> None:
    asyncio.run(_run())


async def _run() -> None:
    now = datetime.now(UTC)
    window_end = now + timedelta(days=_WINDOW_DAYS)
    logger.info("Risk scoring started: window %s → %s", now.isoformat(), window_end.isoformat())

    factory = get_session_factory()
    async with factory() as session:
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
            return

        patient_ids = {a.patient_id for a in appts if a.patient_id is not None}
        history_map = await _batch_fetch_histories(session, patient_ids, cutoff=now)
        appt_ids = [a.id for a in appts]
        existing_4h = await _fetch_existing_4h_reminder_ids(session, appt_ids)

        scored: list[tuple[uuid.UUID, Literal["low", "medium", "high"]]] = []
        for appt in appts:
            pid = appt.patient_id
            history = (
                history_map.get(pid) if pid is not None else None
            ) or PatientAppointmentHistory(0, 0, 0)
            lead_hours = (appt.start_time - now).total_seconds() / 3600
            is_confirmed = appt.status in ("confirmed", "checked_in", "in_chair")
            risk = compute_risk_score(appt, history, is_confirmed, lead_hours)
            scored.append((appt.id, risk))

            if risk == "high" and appt.id not in existing_4h and lead_hours > _EXTRA_REMINDER_HOURS:
                stage_reminder_jobs(session, appt, reminder_hours=[_EXTRA_REMINDER_HOURS])
                logger.info("Staged extra 4h reminder for high-risk appointment %s", appt.id)

        computed_at = datetime.now(UTC)
        for appt_id, risk in scored:
            await session.execute(
                update(Appointment)
                .where(Appointment.id == appt_id)
                .values(no_show_risk=risk, no_show_risk_computed_at=computed_at)
            )

        await session.commit()
        logger.info(
            "Risk scoring complete: %d appointments scored, %d high-risk",
            len(scored),
            sum(1 for _, r in scored if r == "high"),
        )


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


async def _fetch_existing_4h_reminder_ids(
    session: Any,
    appointment_ids: list[uuid.UUID],
) -> set[uuid.UUID]:
    if not appointment_ids:
        return set()

    rows = (
        await session.scalars(
            select(AppointmentReminder.appointment_id).where(
                AppointmentReminder.appointment_id.in_(appointment_ids),
                AppointmentReminder.hours_before == _EXTRA_REMINDER_HOURS,
                AppointmentReminder.status != "cancelled",
                AppointmentReminder.deleted_at.is_(None),
            )
        )
    ).all()

    return set(rows)
