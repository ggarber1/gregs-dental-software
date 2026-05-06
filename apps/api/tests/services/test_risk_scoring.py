from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.services.risk_scoring import PatientAppointmentHistory, compute_risk_score


def _appt(weekday_hour: tuple[int, int] = (2, 10)) -> MagicMock:
    """Return a mock Appointment with start_time set to the given (weekday, hour) in UTC.

    weekday: 0=Monday … 6=Sunday; hour: 0–23 UTC.
    """
    # Find a date that lands on the requested weekday.
    # 2026-05-04 is a Monday (weekday=0).
    base_monday = datetime(2026, 5, 4, tzinfo=UTC)
    days_offset = weekday_hour[0]  # 0=Mon, 4=Fri
    start = base_monday.replace(
        day=base_monday.day + days_offset,
        hour=weekday_hour[1],
    )
    appt = MagicMock()
    appt.start_time = start
    return appt


def _history(total: int = 0, no_show: int = 0, cancel: int = 0) -> PatientAppointmentHistory:
    return PatientAppointmentHistory(total=total, no_show_count=no_show, cancel_count=cancel)


class TestPatientAppointmentHistory:
    def test_no_show_rate_zero_when_no_history(self) -> None:
        assert _history().no_show_rate == 0.0

    def test_no_show_rate_computed(self) -> None:
        h = _history(total=4, no_show=2)
        assert h.no_show_rate == 0.5

    def test_cancel_rate_computed(self) -> None:
        h = _history(total=3, cancel=1)
        assert h.cancel_rate == pytest.approx(0.333, abs=0.001)


class TestComputeRiskScore:
    def test_clean_confirmed_patient_is_low(self) -> None:
        appt = _appt((2, 10))  # Wednesday 10am — no penalty slots
        result = compute_risk_score(appt, _history(total=10), is_confirmed=True, lead_time_hours=48)
        assert result == "low"

    def test_fifty_percent_no_show_rate_confirmed_is_medium(self) -> None:
        # 50% no-show → +40; confirmed → no extra penalty; total 40 → medium
        appt = _appt((2, 10))
        history = _history(total=4, no_show=2)
        result = compute_risk_score(appt, history, is_confirmed=True, lead_time_hours=48)
        assert result == "medium"

    def test_fifty_percent_no_show_rate_unconfirmed_is_high(self) -> None:
        # 50% no-show → +40; unconfirmed → +25; total 65 → high
        appt = _appt((2, 10))
        history = _history(total=4, no_show=2)
        result = compute_risk_score(appt, history, is_confirmed=False, lead_time_hours=48)
        assert result == "high"

    def test_unconfirmed_monday_early_morning_is_high_or_medium(self) -> None:
        appt = _appt((0, 8))  # Monday 8am: weekday +10, early +10
        # unconfirmed +25, Monday +10, early +10 = 45 → medium
        result = compute_risk_score(appt, _history(), is_confirmed=False, lead_time_hours=48)
        assert result in ("medium", "high")

    def test_confirmed_no_history_is_low(self) -> None:
        appt = _appt((2, 10))
        result = compute_risk_score(appt, _history(), is_confirmed=True, lead_time_hours=48)
        assert result == "low"

    def test_unconfirmed_alone_is_medium(self) -> None:
        appt = _appt((2, 10))  # No other signals
        result = compute_risk_score(appt, _history(), is_confirmed=False, lead_time_hours=48)
        assert result == "medium"

    def test_short_lead_time_adds_to_score(self) -> None:
        appt = _appt((2, 10))
        # unconfirmed +25, lead <24h +10 = 35 → medium
        result = compute_risk_score(appt, _history(), is_confirmed=False, lead_time_hours=12)
        assert result == "medium"

    def test_friday_end_of_day_adds_to_score(self) -> None:
        appt = _appt((4, 16))  # Friday 4pm: +10 Friday, +10 end-of-day
        # Confirmed, no history: 0 + 20 = 20 → low
        result_confirmed = compute_risk_score(
            appt, _history(), is_confirmed=True, lead_time_hours=48
        )
        assert result_confirmed == "low"
        # Same but unconfirmed: 0 + 25 + 20 = 45 → medium
        result_unconfirmed = compute_risk_score(
            appt, _history(), is_confirmed=False, lead_time_hours=48
        )
        assert result_unconfirmed == "medium"

    def test_high_cancel_rate_pushes_to_medium(self) -> None:
        appt = _appt((2, 10))
        # cancel_rate=0.4 (+15), unconfirmed (+25) = 40 → medium
        history = _history(total=5, cancel=2)  # 40% cancel rate
        result = compute_risk_score(appt, history, is_confirmed=False, lead_time_hours=48)
        assert result == "medium"

    def test_combined_signals_reach_high(self) -> None:
        appt = _appt((0, 8))  # Monday 8am
        history = _history(total=6, no_show=2)  # ~33% no-show → +40
        # +40 no_show, +25 unconfirmed, +10 Monday, +10 early = 85 → high
        result = compute_risk_score(appt, history, is_confirmed=False, lead_time_hours=48)
        assert result == "high"
