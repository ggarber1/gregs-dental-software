from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PatientInsurance(Base, TimestampMixin):
    __tablename__ = "patient_insurances"

    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    priority: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default="primary",
    )
    carrier: Mapped[str] = mapped_column(String(255), nullable=False)
    member_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    group_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    relationship_to_insured: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default="self",
    )
    insured_first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    insured_last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    insured_date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    insurance_plan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )

    __table_args__ = (
        CheckConstraint(
            "priority IN ('primary', 'secondary')",
            name="ck_patient_insurances_priority",
        ),
        CheckConstraint(
            "relationship_to_insured IN ('self', 'spouse', 'child', 'other')",
            name="ck_patient_insurances_relationship",
        ),
        Index("ix_patient_insurances_patient_id", "patient_id"),
        Index("ix_patient_insurances_practice_patient", "practice_id", "patient_id"),
    )
