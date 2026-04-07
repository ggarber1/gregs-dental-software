from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.practice import Practice


class User(Base, TimestampMixin):
    __tablename__ = "users"

    # Cognito sub is the stable identity anchor — never changes even if email changes.
    cognito_sub: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    practice_memberships: Mapped[list[PracticeUser]] = relationship(
        "PracticeUser",
        back_populates="user",
        lazy="selectin",
    )


class PracticeUser(Base):
    """
    Junction table — scopes a user to a practice with a specific role.

    A user can belong to multiple practices with different roles at each.
    Composite PK (practice_id, user_id) enforces one membership record per pair.
    """

    __tablename__ = "practice_users"

    practice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("practices.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('admin', 'provider', 'front_desk', 'billing', 'read_only')",
            name="ck_practice_users_role",
        ),
    )

    practice: Mapped[Practice] = relationship("Practice", back_populates="practice_users")
    user: Mapped[User] = relationship("User", back_populates="practice_memberships")
