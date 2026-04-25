"""Pure functions for building reminder message content.

No I/O — fully unit-testable. All time formatting is done in the practice's
local timezone so patients see a human-readable local time.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _format_appt_time(dt: datetime, timezone: str) -> str:
    """Return e.g. 'Tuesday, May 6 at 2:30 PM' in the practice's timezone."""
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, KeyError):
        tz = ZoneInfo("America/New_York")

    local = dt.astimezone(tz)
    return local.strftime("%A, %B %-d at %-I:%M %p")


def build_sms_body(
    *,
    patient_first_name: str,
    practice_name: str,
    appointment_start: datetime,
    practice_timezone: str,
    hours_before: int,
) -> str:
    time_str = _format_appt_time(appointment_start, practice_timezone)
    window = f"{hours_before}-hour" if hours_before != 1 else "1-hour"
    return (
        f"Hi {patient_first_name}, this is a {window} reminder from {practice_name}. "
        f"Your appointment is {time_str}. "
        f"Reply YES to confirm or STOP to opt out of reminders."
    )


def build_email_subject(
    *,
    practice_name: str,
    appointment_start: datetime,
    practice_timezone: str,
) -> str:
    time_str = _format_appt_time(appointment_start, practice_timezone)
    return f"Appointment reminder from {practice_name} — {time_str}"


def build_email_html(
    *,
    patient_first_name: str,
    practice_name: str,
    appointment_start: datetime,
    practice_timezone: str,
    practice_phone: str | None,
) -> str:
    time_str = _format_appt_time(appointment_start, practice_timezone)
    contact = f"<p>Questions? Call us at {practice_phone}.</p>" if practice_phone else ""
    return f"""<!DOCTYPE html>
<html>
<body style="font-family: sans-serif; max-width: 560px; margin: 0 auto; padding: 24px;">
  <h2 style="color: #1a1a1a;">Appointment Reminder</h2>
  <p>Hi {patient_first_name},</p>
  <p>This is a reminder of your upcoming appointment at <strong>{practice_name}</strong>.</p>
  <p style="font-size: 1.1em; font-weight: bold;">{time_str}</p>
  <p>If you need to reschedule or cancel, please contact us as soon as possible.</p>
  {contact}
  <p style="color: #888; font-size: 0.85em;">
    You received this email because you are a patient at {practice_name}.
  </p>
</body>
</html>"""


def build_email_text(
    *,
    patient_first_name: str,
    practice_name: str,
    appointment_start: datetime,
    practice_timezone: str,
    practice_phone: str | None,
) -> str:
    time_str = _format_appt_time(appointment_start, practice_timezone)
    contact = f"Questions? Call us at {practice_phone}.\n" if practice_phone else ""
    return (
        f"Hi {patient_first_name},\n\n"
        f"This is a reminder of your upcoming appointment at {practice_name}.\n\n"
        f"{time_str}\n\n"
        f"If you need to reschedule or cancel, please contact us as soon as possible.\n"
        f"{contact}"
    )
