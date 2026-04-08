from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, Date, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin


class Patient(Base, PHIMixin):
    __tablename__ = "patients"

    practice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        # No FK here — practices lives in the same DB but we avoid a hard FK
        # on PHI tables to make cross-schema moves easier later.
        nullable=False,
        index=True,
    )

    # Demographics
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[Date] = mapped_column(Date, nullable=False)
    sex: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Contact
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Address
    address_line1: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_line2: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    zip: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # PHI — AES-256-GCM encrypted at the application layer before storage.
    # We store the last-4 digits only (never full SSN).
    ssn_encrypted: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)

    # Clinical flags
    allergies: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default="{}",
    )
    medical_alerts: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default="{}",
    )
    sms_opt_out: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )

    __table_args__ = (
        CheckConstraint(
            "sex IN ('male', 'female', 'other', 'unknown')",
            name="ck_patients_sex",
        ),
        # Search: last_name-first_name prefix search within a practice
        Index("ix_patients_practice_name", "practice_id", "last_name", "first_name"),
        # List with soft-delete filter
        Index("ix_patients_practice_deleted", "practice_id", "deleted_at"),
    )
