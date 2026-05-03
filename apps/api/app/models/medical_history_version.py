from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin


class MedicalHistoryVersion(Base, PHIMixin):
    __tablename__ = "medical_history_versions"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    allergies: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="'[]'::jsonb")
    medications: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="'[]'::jsonb")
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="'[]'::jsonb")

    flag_blood_thinners: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    flag_bisphosphonates: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    flag_heart_condition: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    flag_diabetes: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    flag_pacemaker: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    flag_latex_allergy: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    additional_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "patient_id",
            "version_number",
            name="uq_medical_history_versions_patient_version",
        ),
        Index("ix_medical_history_versions_patient_id", "patient_id"),
        Index("ix_medical_history_versions_practice_patient", "practice_id", "patient_id"),
    )
