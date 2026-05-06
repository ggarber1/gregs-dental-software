from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.models.appointment import Appointment


@dataclass
class PatientAppointmentHistory:
    total: int
    no_show_count: int
    cancel_count: int

    @property
    def no_show_rate(self) -> float:
        return self.no_show_count / self.total if self.total else 0.0

    @property
    def cancel_rate(self) -> float:
        return self.cancel_count / self.total if self.total else 0.0


def compute_risk_score(
    appointment: Appointment,
    history: PatientAppointmentHistory,
    is_confirmed: bool,
    lead_time_hours: float,
) -> Literal["low", "medium", "high"]:
    score = 0

    if history.no_show_rate >= 0.33:
        score += 40
    elif history.no_show_rate >= 0.15:
        score += 20

    if history.cancel_rate >= 0.33:
        score += 15
    elif history.cancel_rate >= 0.15:
        score += 8

    if not is_confirmed:
        score += 25

    # 0=Mon … 4=Fri (start_time is UTC — close enough for scheduling signals)
    if appointment.start_time.weekday() in (0, 4):
        score += 10

    hour = appointment.start_time.hour
    if hour < 9 or hour >= 16:
        score += 10

    if lead_time_hours < 24:
        score += 10

    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    return "low"
