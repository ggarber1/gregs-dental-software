"""Unit tests for the risk scoring worker.

The DB session and risk scoring service are mocked — no real Postgres needed.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.risk_scoring_worker import (
    _run,
)

_NOW = datetime(2026, 6, 15, 7, 0, tzinfo=UTC)


def _make_appt(
    appt_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    start_offset_hours: float = 24,
    status: str = "scheduled",
) -> MagicMock:
    appt = MagicMock()
    appt.id = appt_id or uuid.uuid4()
    appt.patient_id = patient_id or uuid.uuid4()
    appt.start_time = _NOW + timedelta(hours=start_offset_hours)
    appt.status = status
    appt.deleted_at = None
    return appt


class TestRunIdempotency:
    @pytest.mark.asyncio
    async def test_second_run_does_not_create_duplicate_4h_reminder(self) -> None:
        appt_id = uuid.uuid4()
        patient_id = uuid.uuid4()
        appt = _make_appt(appt_id=appt_id, patient_id=patient_id, start_offset_hours=24)

        session = AsyncMock()

        # scalars() for appointments query
        appts_result = MagicMock()
        appts_result.all.return_value = [appt]

        # execute() for history query — returns empty aggregate
        history_row = MagicMock()
        history_row.patient_id = patient_id
        history_row.total = 0
        history_row.no_show_count = 0
        history_row.cancel_count = 0
        history_execute_result = MagicMock()
        history_execute_result.all.return_value = [history_row]

        # scalars() for existing 4h reminders — already exists (simulates second run)
        existing_4h_result = MagicMock()
        existing_4h_result.all.return_value = [appt_id]

        # update() execute results
        update_result = MagicMock()

        session.scalars = AsyncMock(side_effect=[appts_result, existing_4h_result])
        session.execute = AsyncMock(side_effect=[history_execute_result, update_result])
        session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.workers.risk_scoring_worker.get_session_factory", return_value=mock_factory),
            patch("app.workers.risk_scoring_worker.datetime") as mock_dt,
            patch("app.workers.risk_scoring_worker.stage_reminder_jobs") as mock_stage,
        ):
            mock_dt.now.return_value = _NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            await _run()

        # stage_reminder_jobs must NOT have been called because 4h reminder already exists
        mock_stage.assert_not_called()

    @pytest.mark.asyncio
    async def test_appointment_less_than_4h_away_does_not_get_extra_reminder(self) -> None:
        appt_id = uuid.uuid4()
        patient_id = uuid.uuid4()
        # Only 2h lead time — too close for an extra reminder
        appt = _make_appt(appt_id=appt_id, patient_id=patient_id, start_offset_hours=2)

        session = AsyncMock()

        appts_result = MagicMock()
        appts_result.all.return_value = [appt]

        history_row = MagicMock()
        history_row.patient_id = patient_id
        history_row.total = 6
        history_row.no_show_count = 3  # 50% → high risk
        history_row.cancel_count = 0
        history_execute_result = MagicMock()
        history_execute_result.all.return_value = [history_row]

        # No existing 4h reminders
        existing_4h_result = MagicMock()
        existing_4h_result.all.return_value = []

        update_result = MagicMock()

        session.scalars = AsyncMock(side_effect=[appts_result, existing_4h_result])
        session.execute = AsyncMock(side_effect=[history_execute_result, update_result])
        session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.workers.risk_scoring_worker.get_session_factory", return_value=mock_factory),
            patch("app.workers.risk_scoring_worker.datetime") as mock_dt,
            patch("app.workers.risk_scoring_worker.stage_reminder_jobs") as mock_stage,
        ):
            mock_dt.now.return_value = _NOW
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            await _run()

        # Appointment is high-risk but < 4h away — no extra reminder
        mock_stage.assert_not_called()
