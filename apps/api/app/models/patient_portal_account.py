from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PatientPortalAccount(Base, TimestampMixin):
    __tablename__ = "patient_portal_accounts"

    practice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    cognito_sub: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="invited",
    )
    invite_token: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    invited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    enrolled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('invited', 'active', 'revoked')",
            name="ck_patient_portal_accounts_status",
        ),
        UniqueConstraint(
            "practice_id",
            "patient_id",
            name="uq_patient_portal_accounts_practice_patient",
        ),
        Index(
            "ix_patient_portal_accounts_practice_patient",
            "practice_id",
            "patient_id",
        ),
        Index(
            "ix_patient_portal_accounts_practice_status",
            "practice_id",
            "status",
        ),
    )
