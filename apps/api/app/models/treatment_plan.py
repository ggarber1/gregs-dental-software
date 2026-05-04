from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, Index, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin


class TreatmentPlan(Base, PHIMixin):
    __tablename__ = "treatment_plans"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    name: Mapped[str] = mapped_column(Text, nullable=False, server_default="Treatment Plan")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="proposed")

    presented_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    accepted_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'accepted', 'in_progress', "
            "'completed', 'refused', 'superseded')",
            name="ck_treatment_plans_status",
        ),
        Index("ix_treatment_plans_patient_status", "patient_id", "status"),
        Index("ix_treatment_plans_practice_status", "practice_id", "status"),
        Index("ix_treatment_plans_patient_created_at", "patient_id", "created_at"),
    )


class TreatmentPlanItem(Base, PHIMixin):
    __tablename__ = "treatment_plan_items"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    treatment_plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    tooth_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    procedure_code: Mapped[str] = mapped_column(Text, nullable=False)
    procedure_name: Mapped[str] = mapped_column(Text, nullable=False)
    surface: Mapped[str | None] = mapped_column(Text, nullable=True)
    fee_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    insurance_est_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    patient_est_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="proposed")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    completed_appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('proposed', 'accepted', 'scheduled', 'completed', 'refused')",
            name="ck_treatment_plan_items_status",
        ),
        Index("ix_treatment_plan_items_plan_id", "treatment_plan_id"),
        Index("ix_treatment_plan_items_patient_status", "patient_id", "status"),
        Index("ix_treatment_plan_items_appointment_id", "appointment_id"),
    )
