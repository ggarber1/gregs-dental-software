"""Unit tests for the Lambda entry points."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers import lambda_handlers
from app.workers.reminder_worker import ReminderRunSummary

_P_LOAD = "app.workers.lambda_handlers.load_settings_from_ssm"
_P_FACTORY = "app.core.db.get_session_factory"
_P_DISPOSE = "app.core.db.dispose_engine"
_P_REMINDERS = "app.workers.reminder_worker.send_due_reminders"
_P_SCORING = "app.workers.risk_scoring_worker.score_upcoming_appointments"


@pytest.fixture(autouse=True)
def _reset_config_flag() -> None:
    lambda_handlers._config_loaded = False


def test_reminders_runs_job_with_fresh_engine_and_returns_summary() -> None:
    factory = MagicMock(name="factory")
    job = AsyncMock(return_value=ReminderRunSummary(claimed=2, sent=1, skipped=1))
    with (
        patch(_P_LOAD) as load,
        patch(_P_FACTORY, return_value=factory),
        patch(_P_DISPOSE, new_callable=AsyncMock) as dispose,
        patch(_P_REMINDERS, job),
    ):
        result = lambda_handlers.reminders({}, None)

    load.assert_called_once_with()
    job.assert_awaited_once_with(factory)
    dispose.assert_awaited_once()
    assert result == {"claimed": 2, "sent": 1, "skipped": 1, "failed": 0}


def test_config_is_loaded_once_per_container() -> None:
    with (
        patch(_P_LOAD) as load,
        patch(_P_FACTORY),
        patch(_P_DISPOSE, new_callable=AsyncMock) as dispose,
        patch(_P_REMINDERS, AsyncMock(return_value=ReminderRunSummary())),
    ):
        lambda_handlers.reminders({}, None)
        lambda_handlers.reminders({}, None)

    load.assert_called_once()
    assert dispose.await_count == 2


def test_engine_is_disposed_when_the_job_fails() -> None:
    with (
        patch(_P_LOAD),
        patch(_P_FACTORY),
        patch(_P_DISPOSE, new_callable=AsyncMock) as dispose,
        patch(_P_REMINDERS, AsyncMock(side_effect=RuntimeError("db down"))),
        pytest.raises(RuntimeError, match="db down"),
    ):
        lambda_handlers.reminders({}, None)

    dispose.assert_awaited_once()


def test_risk_scoring_returns_scored_count() -> None:
    with (
        patch(_P_LOAD),
        patch(_P_FACTORY),
        patch(_P_DISPOSE, new_callable=AsyncMock) as dispose,
        patch(_P_SCORING, AsyncMock(return_value=7)),
    ):
        result = lambda_handlers.risk_scoring({}, None)

    assert result == {"scored": 7}
    dispose.assert_awaited_once()
