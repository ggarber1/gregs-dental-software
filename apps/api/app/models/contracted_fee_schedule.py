from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ContractedFeeSchedule(Base, TimestampMixin):
    """Per-carrier contracted allowed amount for a CDT code. Source of truth for
    the engine's allowed_amount; the engine falls back to the billed fee when no
    active row exists. Keyed (practice_id, payer_id, cdt_code_id). Soft-deletable."""

    __tablename__ = "contracted_fee_schedule"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payer_id: Mapped[str] = mapped_column(String(50), nullable=False)
    cdt_code_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cdt_codes.id", name="fk_contracted_fee_schedule_cdt_code"),
        nullable=False,
    )
    allowed_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    not_covered: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    requires_prior_auth: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    __table_args__ = (
        Index("ix_contracted_fee_schedule_lookup", "practice_id", "payer_id"),
    )
