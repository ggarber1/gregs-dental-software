from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.s3 import delete_object, put_object
from app.models.appointment import Appointment
from app.models.appointment_attachment import AppointmentAttachment
from app.models.appointment_procedure import AppointmentProcedure
from app.models.perio_chart import PerioChart, PerioReading

_ACCEPTED_CONTENT_TYPES = frozenset(
    ["image/jpeg", "image/png", "application/pdf", "image/tiff", "text/plain"]
)
_MAX_SIZE_BYTES = 64 * 1024 * 1024  # 64 MB


async def _load_appointment(
    session: AsyncSession,
    practice_id: uuid.UUID,
    appointment_id: uuid.UUID,
) -> Appointment:
    appt = await session.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.deleted_at.is_(None),
        )
    )
    if appt is None or appt.practice_id != practice_id:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appt


async def upload_attachment(
    session: AsyncSession,
    *,
    practice_id: uuid.UUID,
    appointment_id: uuid.UUID,
    file_bytes: bytes,
    file_name: str,
    content_type: str,
    attachment_type: str,
    user_sub: str,
) -> AppointmentAttachment:
    if content_type not in _ACCEPTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "UNSUPPORTED_FILE_TYPE",
                "message": f"Content type {content_type!r} is not accepted",
            },
        )
    if len(file_bytes) > _MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "FILE_TOO_LARGE",
                "message": "File exceeds the 64 MB limit",
            },
        )

    await _load_appointment(session, practice_id, appointment_id)

    attachment_id = uuid.uuid4()
    settings = get_settings()
    s3_key = f"{practice_id}/appointments/{appointment_id}/{attachment_id}/{file_name}"

    put_object(settings.s3_bucket_phi_documents, s3_key, file_bytes, content_type)

    row = AppointmentAttachment(
        id=attachment_id,
        practice_id=practice_id,
        appointment_id=appointment_id,
        s3_key=s3_key,
        file_name=file_name,
        file_size_bytes=len(file_bytes),
        content_type=content_type,
        attachment_type=attachment_type,
        uploaded_by=user_sub,
        last_accessed_by=user_sub,
        last_accessed_at=datetime.now(UTC),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_attachments(
    session: AsyncSession,
    *,
    practice_id: uuid.UUID,
    appointment_id: uuid.UUID,
) -> list[AppointmentAttachment]:
    await _load_appointment(session, practice_id, appointment_id)
    rows = (
        await session.scalars(
            select(AppointmentAttachment).where(
                AppointmentAttachment.appointment_id == appointment_id,
                AppointmentAttachment.practice_id == practice_id,
                AppointmentAttachment.deleted_at.is_(None),
            )
        )
    ).all()
    return list(rows)


async def delete_attachment(
    session: AsyncSession,
    *,
    practice_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> None:
    row = await session.scalar(
        select(AppointmentAttachment).where(
            AppointmentAttachment.id == attachment_id,
            AppointmentAttachment.practice_id == practice_id,
            AppointmentAttachment.deleted_at.is_(None),
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    settings = get_settings()
    row.deleted_at = datetime.now(UTC)
    await session.commit()
    delete_object(settings.s3_bucket_phi_documents, row.s3_key)


# ── Perio narrative generator ─────────────────────────────────────────────────

_D4_PATTERN = re.compile(r"^D4\d{3}$")
_SITE_ORDER = ("db", "b", "mb", "dl", "l", "ml")


def _build_perio_narrative(
    chart: PerioChart,
    readings: list[PerioReading],
    d4_codes: list[str],
) -> str:
    """Render a plain-text periodontal examination report."""
    # Index readings by tooth then site
    by_tooth: dict[str, dict[str, PerioReading]] = {}
    for r in readings:
        by_tooth.setdefault(r.tooth_number, {})[r.site] = r

    def _tooth_sort_key(t: str) -> tuple[int, str]:
        return (len(t), t)

    lines: list[str] = [
        "PERIODONTAL EXAMINATION REPORT",
        f"Chart Date: {chart.chart_date.isoformat()}",
        f"Procedure Codes: {', '.join(d4_codes)}",
        "",
        "POCKET DEPTHS (mm) — site order: DB, B, MB, DL, L, ML",
    ]
    for tooth in sorted(by_tooth.keys(), key=_tooth_sort_key):
        site_map = by_tooth[tooth]
        depths = [
            str(site_map[s].probing_depth_mm) if s in site_map else "-"
            for s in _SITE_ORDER
        ]
        lines.append(f"  Tooth #{tooth}: {', '.join(depths)}")

    lines.append("")
    lines.append("CLINICAL FINDINGS:")

    # Bleeding on probing
    bleeding_teeth = sorted(
        {r.tooth_number for r in readings if r.bleeding},
        key=_tooth_sort_key,
    )
    lines.append(
        f"  Bleeding on probing: "
        f"{', '.join('#' + t for t in bleeding_teeth) if bleeding_teeth else 'none'}"
    )

    # Suppuration
    supp_teeth = sorted(
        {r.tooth_number for r in readings if r.suppuration},
        key=_tooth_sort_key,
    )
    lines.append(
        f"  Suppuration: "
        f"{', '.join('#' + t for t in supp_teeth) if supp_teeth else 'none'}"
    )

    # Furcation — first non-None value per tooth
    furcation_by_tooth: dict[str, str] = {}
    for r in readings:
        if r.furcation and r.tooth_number not in furcation_by_tooth:
            furcation_by_tooth[r.tooth_number] = r.furcation
    if furcation_by_tooth:
        furc_parts = [
            f"#{t} (Class {cls})"
            for t, cls in sorted(furcation_by_tooth.items(), key=lambda x: _tooth_sort_key(x[0]))
        ]
        lines.append(f"  Furcation involvement: {', '.join(furc_parts)}")
    else:
        lines.append("  Furcation involvement: none")

    # Mobility — max grade per tooth
    mobility_by_tooth: dict[str, int] = {}
    for r in readings:
        if r.mobility is not None:
            prev = mobility_by_tooth.get(r.tooth_number)
            if prev is None or r.mobility > prev:
                mobility_by_tooth[r.tooth_number] = r.mobility
    if mobility_by_tooth:
        mob_parts = [
            f"#{t} (Grade {grade})"
            for t, grade in sorted(
                mobility_by_tooth.items(), key=lambda x: _tooth_sort_key(x[0])
            )
        ]
        lines.append(f"  Mobility: {', '.join(mob_parts)}")
    else:
        lines.append("  Mobility: none")

    if chart.notes:
        lines.append("")
        lines.append(f"NOTES: {chart.notes}")

    return "\n".join(lines)


async def generate_perio_narrative(
    session: AsyncSession,
    *,
    practice_id: uuid.UUID,
    appointment_id: uuid.UUID,
) -> AppointmentAttachment | None:
    """Generate and store a perio narrative attachment for D4xxx appointments.

    Idempotent: returns the existing row if one already exists.
    Returns None if the appointment has no D4xxx procedures or no recorded chart.
    """
    # 1. Filter to D4xxx procedures (non-deleted)
    procs = (
        await session.scalars(
            select(AppointmentProcedure).where(
                AppointmentProcedure.appointment_id == appointment_id,
                AppointmentProcedure.deleted_at.is_(None),
            )
        )
    ).all()

    d4_codes = sorted(
        {
            p.procedure_code
            for p in procs
            if p.procedure_code and _D4_PATTERN.match(p.procedure_code)
        }
    )

    if not d4_codes:
        return None

    # 2. Idempotency check
    existing = await session.scalar(
        select(AppointmentAttachment).where(
            AppointmentAttachment.appointment_id == appointment_id,
            AppointmentAttachment.practice_id == practice_id,
            AppointmentAttachment.attachment_type == "perio_narrative",
            AppointmentAttachment.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return existing

    # 3. Load PerioChart
    chart = await session.scalar(
        select(PerioChart).where(
            PerioChart.appointment_id == appointment_id,
            PerioChart.deleted_at.is_(None),
        )
    )
    if chart is None:
        return None

    # 4. Load PerioReadings
    readings = list(
        (
            await session.scalars(
                select(PerioReading).where(
                    PerioReading.perio_chart_id == chart.id,
                )
            )
        ).all()
    )

    # 5. Render narrative
    content_bytes = _build_perio_narrative(chart, readings, d4_codes).encode()

    # 6. S3 key
    attachment_id = uuid.uuid4()
    settings = get_settings()
    file_name = f"perio_narrative_{appointment_id}.txt"
    s3_key = (
        f"{practice_id}/appointments/{appointment_id}/{attachment_id}/{file_name}"
    )
    put_object(settings.s3_bucket_phi_documents, s3_key, content_bytes, "text/plain")

    # 7. Persist row
    row = AppointmentAttachment(
        id=attachment_id,
        practice_id=practice_id,
        appointment_id=appointment_id,
        s3_key=s3_key,
        file_name=file_name,
        file_size_bytes=len(content_bytes),
        content_type="text/plain",
        attachment_type="perio_narrative",
        uploaded_by="system",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row
