from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.practice import Practice


class Operatory(Base, TimestampMixin):
    __tablename__ = "operatories"

    practice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("practices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Human-readable name shown on the room-view calendar (e.g. "Operatory 1", "Room A").
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Hex color used on the calendar view.
    color: Mapped[str] = mapped_column(
        String(7),
        nullable=False,
        server_default="#7BC67E",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        # Composite index for scheduling queries: available rooms for a practice.
        Index("ix_operatories_practice_is_active", "practice_id", "is_active"),
    )

    practice: Mapped[Practice] = relationship("Practice", back_populates="operatories")
