"""Unit tests for reminder_templates — pure functions, no I/O."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.reminder_templates import (
    build_email_subject,
    build_email_text,
    build_sms_body,
)

# A fixed UTC datetime: 2026-05-06 14:00 UTC = 10:00 AM EDT (UTC-4)
_APT_UTC = datetime(2026, 5, 6, 14, 0, 0, tzinfo=UTC)


# ── build_sms_body ────────────────────────────────────────────────────────────


def test_sms_body_contains_patient_name():
    body = build_sms_body(
        patient_first_name="Jane",
        practice_name="Sunrise Dental",
        appointment_start=_APT_UTC,
        practice_timezone="America/New_York",
        hours_before=24,
    )
    assert "Jane" in body


def test_sms_body_contains_practice_name():
    body = build_sms_body(
        patient_first_name="Jane",
        practice_name="Sunrise Dental",
        appointment_start=_APT_UTC,
        practice_timezone="America/New_York",
        hours_before=24,
    )
    assert "Sunrise Dental" in body


def test_sms_body_shows_local_time_not_utc():
    body = build_sms_body(
        patient_first_name="Jane",
        practice_name="Sunrise Dental",
        appointment_start=_APT_UTC,
        practice_timezone="America/New_York",
        hours_before=24,
    )
    # 14:00 UTC = 10:00 AM EDT; must NOT see "2:00 PM" (UTC wall-clock)
    assert "10:00 AM" in body
    assert "2:00 PM" not in body


def test_sms_body_contains_48h_window_label():
    body = build_sms_body(
        patient_first_name="Jane",
        practice_name="Sunrise Dental",
        appointment_start=_APT_UTC,
        practice_timezone="America/New_York",
        hours_before=48,
    )
    assert "48-hour" in body


def test_sms_body_contains_yes_stop_instructions():
    body = build_sms_body(
        patient_first_name="Jane",
        practice_name="Sunrise Dental",
        appointment_start=_APT_UTC,
        practice_timezone="America/New_York",
        hours_before=24,
    )
    assert "YES" in body
    assert "STOP" in body


def test_sms_body_falls_back_gracefully_for_unknown_timezone():
    # Should not raise — falls back to America/New_York
    body = build_sms_body(
        patient_first_name="Jane",
        practice_name="Clinic",
        appointment_start=_APT_UTC,
        practice_timezone="Not/AReal_Zone",
        hours_before=24,
    )
    assert "Jane" in body


# ── build_email_subject ───────────────────────────────────────────────────────


def test_email_subject_contains_practice_name():
    subject = build_email_subject(
        practice_name="Sunrise Dental",
        appointment_start=_APT_UTC,
        practice_timezone="America/New_York",
    )
    assert "Sunrise Dental" in subject


def test_email_subject_contains_local_time():
    subject = build_email_subject(
        practice_name="Sunrise Dental",
        appointment_start=_APT_UTC,
        practice_timezone="America/New_York",
    )
    assert "10:00 AM" in subject


# ── build_email_text ──────────────────────────────────────────────────────────


def test_email_text_contains_patient_name():
    text = build_email_text(
        patient_first_name="Jane",
        practice_name="Sunrise Dental",
        appointment_start=_APT_UTC,
        practice_timezone="America/New_York",
        practice_phone="(617) 555-1234",
    )
    assert "Jane" in text


def test_email_text_contains_practice_phone():
    text = build_email_text(
        patient_first_name="Jane",
        practice_name="Sunrise Dental",
        appointment_start=_APT_UTC,
        practice_timezone="America/New_York",
        practice_phone="(617) 555-1234",
    )
    assert "(617) 555-1234" in text


def test_email_text_omits_phone_line_when_none():
    text = build_email_text(
        patient_first_name="Jane",
        practice_name="Sunrise Dental",
        appointment_start=_APT_UTC,
        practice_timezone="America/New_York",
        practice_phone=None,
    )
    assert "Call us" not in text
