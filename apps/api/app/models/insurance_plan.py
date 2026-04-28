from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class InsurancePlan(Base, TimestampMixin):
    __tablename__ = "insurance_plans"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    carrier_name: Mapped[str] = mapped_column(String(255), nullable=False)
    payer_id: Mapped[str] = mapped_column(String(50), nullable=False)
    group_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_in_network: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )

    __table_args__ = (
        Index("ix_insurance_plans_practice_deleted", "practice_id", "deleted_at"),
        Index("ix_insurance_plans_practice_payer", "practice_id", "payer_id"),
    )
