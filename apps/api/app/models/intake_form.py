from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import BYTEA, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class IntakeForm(Base, TimestampMixin):
    __tablename__ = "intake_forms"

    practice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # No FK — matches PHI table pattern; avoids hard cross-schema constraint.
        nullable=False,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    # 64-char hex of 32 cryptographically random bytes
    token: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="pending",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    # AES-256-GCM encrypted JSON; null until patient submits
    responses_encrypted: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    submission_ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    submission_user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    # practice_user.id who triggered the send
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'completed', 'expired')",
            name="ck_intake_forms_status",
        ),
        Index("ix_intake_forms_practice_patient", "practice_id", "patient_id"),
        Index("ix_intake_forms_practice_status", "practice_id", "status"),
    )
