from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class PracticeFeeSchedule(Base, TimestampMixin):
    """Per-practice fee override for a CDT code. Resolution order at read time is
    practice fee -> cdt_codes.default_fee_cents -> blank. Soft-deletable (revert)."""

    __tablename__ = "practice_fee_schedule"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    cdt_code_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cdt_codes.id", name="fk_practice_fee_schedule_cdt_code"),
        nullable=False,
    )
    fee_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index("ix_practice_fee_schedule_practice_id", "practice_id"),
        Index("ix_practice_fee_schedule_cdt_code_id", "cdt_code_id"),
    )
