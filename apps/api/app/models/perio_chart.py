from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin, UUIDMixin


class PerioChart(Base, PHIMixin):
    __tablename__ = "perio_charts"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chart_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_perio_charts_patient_date", "patient_id", "chart_date"),
        Index("ix_perio_charts_practice", "practice_id"),
    )


class PerioReading(Base, UUIDMixin):
    __tablename__ = "perio_readings"

    perio_chart_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tooth_number: Mapped[str] = mapped_column(Text, nullable=False)
    site: Mapped[str] = mapped_column(Text, nullable=False)
    probing_depth_mm: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    recession_mm: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    bleeding: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    suppuration: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    furcation: Mapped[str | None] = mapped_column(Text, nullable=True)
    mobility: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "site IN ('db', 'b', 'mb', 'dl', 'l', 'ml')", name="ck_perio_readings_site"
        ),
        CheckConstraint("probing_depth_mm BETWEEN 0 AND 20", name="ck_perio_readings_depth"),
        CheckConstraint("recession_mm BETWEEN 0 AND 15", name="ck_perio_readings_recession"),
        CheckConstraint(
            "furcation IS NULL OR furcation IN ('I', 'II', 'III')",
            name="ck_perio_readings_furcation",
        ),
        CheckConstraint(
            "mobility IS NULL OR mobility BETWEEN 0 AND 3",
            name="ck_perio_readings_mobility",
        ),
        UniqueConstraint(
            "perio_chart_id", "tooth_number", "site", name="uq_perio_readings_chart_tooth_site"
        ),
        Index("ix_perio_readings_chart_id", "perio_chart_id"),
    )
