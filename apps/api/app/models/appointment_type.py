from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.practice import Practice


class AppointmentType(Base, TimestampMixin):
    __tablename__ = "appointment_types"

    practice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("practices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    # Hex color for calendar display.
    color: Mapped[str] = mapped_column(
        String(7),
        nullable=False,
        server_default="#5B8DEF",
    )
    # Default CDT codes to pre-fill when this type is selected (e.g. ["D0150", "D1110"]).
    default_cdt_codes: Mapped[list[str]] = mapped_column(
        ARRAY(Text()),
        nullable=False,
        server_default="{}",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        Index("ix_appointment_types_practice_is_active", "practice_id", "is_active"),
    )

    practice: Mapped[Practice] = relationship("Practice", back_populates="appointment_types")
