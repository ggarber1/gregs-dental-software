from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin


class EligibilityCheck(Base, PHIMixin):
    """Real-time insurance eligibility verification result.

    Holds PHI (patient benefit data) -> PHIMixin. The table was created in
    migration 0015; migration 0027 converts money columns to integer cents,
    adds plan_name, relaxes raw_response to nullable, and constrains
    clearinghouse values. Money is integer cents; coinsurance is a patient-share
    fraction (Numeric(5,4)).
    """

    __tablename__ = "eligibility_checks"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_insurance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    trigger: Mapped[str] = mapped_column(String(30), nullable=False)
    clearinghouse: Mapped[str] = mapped_column(String(20), nullable=False)
    payer_id_used: Mapped[str] = mapped_column(String(50), nullable=False)
    payer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    plan_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    coverage_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    coverage_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    coverage_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Money — integer cents, NULL = not returned
    deductible_individual: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deductible_individual_met: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deductible_family: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deductible_family_met: Mapped[int | None] = mapped_column(Integer, nullable=True)
    oop_max_individual: Mapped[int | None] = mapped_column(Integer, nullable=True)
    oop_max_individual_met: Mapped[int | None] = mapped_column(Integer, nullable=True)
    annual_max_individual: Mapped[int | None] = mapped_column(Integer, nullable=True)
    annual_max_individual_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    annual_max_individual_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Coinsurance — patient share fraction
    coinsurance_preventive: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    coinsurance_basic: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    coinsurance_major: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    coinsurance_ortho: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)

    waiting_period_basic_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    waiting_period_major_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    waiting_period_ortho_months: Mapped[int | None] = mapped_column(Integer, nullable=True)

    frequency_limits: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    plan_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ppo")
    network_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="in_network"
    )
    coinsurance_by_code: Mapped[dict[str, float] | None] = mapped_column(JSONB, nullable=True)
    deductible_waived_diagnostic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    deductible_waived_preventive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    deductible_waived_orthodontic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    ortho_lifetime_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ortho_lifetime_max_used: Mapped[int | None] = mapped_column(Integer, nullable=True)

    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'verified', 'failed', 'not_supported')",
            name="ck_eligibility_checks_status",
        ),
        CheckConstraint(
            "trigger IN ('manual', 'pre_appointment_batch')",
            name="ck_eligibility_checks_trigger",
        ),
        CheckConstraint(
            "coverage_status IN ('active', 'inactive', 'unknown') OR coverage_status IS NULL",
            name="ck_eligibility_checks_coverage_status",
        ),
        CheckConstraint(
            "clearinghouse IN ('stedi', 'dentalxchange', 'manual')",
            name="ck_eligibility_checks_clearinghouse",
        ),
        CheckConstraint(
            "plan_type IN ('ppo', 'premier', 'medicaid', 'indemnity', 'dhmo')",
            name="ck_eligibility_checks_plan_type",
        ),
        CheckConstraint(
            "network_status IN ('in_network', 'out_of_network')",
            name="ck_eligibility_checks_network_status",
        ),
        Index("ix_eligibility_checks_idempotency_key", "idempotency_key", unique=True),
        Index("ix_eligibility_checks_patient_id", "patient_id"),
        Index("ix_eligibility_checks_appointment_id", "appointment_id"),
        Index("ix_eligibility_checks_practice_patient", "practice_id", "patient_id"),
        Index("ix_eligibility_checks_practice_deleted", "practice_id", "deleted_at"),
    )
