from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.practice import Practice
    from app.models.user import User


class Provider(Base, TimestampMixin):
    """
    Clinical staff who appear on the schedule and/or on dental claims.

    NPI convention (Module 3.4.1):
    `npi` is NOT NULL for every `provider_type`. For `provider_type = 'hygienist'`,
    the row carries the **supervising dentist's** 10-digit NPI by convention — there
    is no separate hygienist NPI on 837D claims for the typical solo/small practice.
    `provider_type` still differentiates scheduling and display; billing (Module 7
    837D generation) reads `provider.npi` directly, with no lookup through a
    supervisor relationship. Exceptions (a hygienist with their own NPI) are allowed
    — the column is not constrained to match any other row.
    """

    __tablename__ = "providers"

    practice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("practices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable — not all providers have system logins (e.g., associates, part-time hygienists).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 10-digit NPI — required for 837D claims generation (Module 7).
    npi: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    provider_type: Mapped[str] = mapped_column(String(20), nullable=False)
    license_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    specialty: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Hex color used on the calendar view.
    color: Mapped[str] = mapped_column(
        String(7),
        nullable=False,
        server_default="#4F86C6",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        CheckConstraint(
            "provider_type IN ('dentist', 'hygienist', 'specialist', 'other')",
            name="ck_providers_provider_type",
        ),
        # Composite index for scheduling queries: available providers for a practice.
        Index("ix_providers_practice_is_active", "practice_id", "is_active"),
    )

    practice: Mapped[Practice] = relationship("Practice", back_populates="providers")
    user: Mapped[User | None] = relationship("User")
