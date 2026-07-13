from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin

_VALID_CONTENT_TYPES = (
    "image/jpeg",
    "image/png",
    "application/pdf",
    "image/tiff",
    "text/plain",
)
_VALID_ATTACHMENT_TYPES = ("xray", "photo", "perio_narrative", "lab_rx", "other")

# Maps attachment_type to the Stedi PWK01 attachmentReportTypeCode
ATTACHMENT_TYPE_TO_PWK01: dict[str, str] = {
    "xray": "B4",
    "perio_narrative": "DG",
    "photo": "DA",
    "lab_rx": "77",
    "other": "OB",
}


class AppointmentAttachment(Base, PHIMixin):
    __tablename__ = "appointment_attachments"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    attachment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    uploaded_by: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'application/pdf',"
            " 'image/tiff', 'text/plain')",
            name="ck_appointment_attachments_content_type",
        ),
        CheckConstraint(
            "attachment_type IN ('xray', 'photo', 'perio_narrative', 'lab_rx', 'other')",
            name="ck_appointment_attachments_attachment_type",
        ),
        Index("ix_appt_attachments_appointment", "appointment_id"),
        Index("ix_appt_attachments_practice", "practice_id"),
    )
