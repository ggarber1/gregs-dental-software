import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    """
    Insert-only audit log for all PHI access.

    The app DB user has INSERT-only privileges on this table.
    A Postgres trigger (added in migration 1.6) prevents UPDATE and DELETE.
    Never add update/delete methods to this model.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    practice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    user_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    resource_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    status_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (Index("ix_audit_logs_practice_timestamp", "practice_id", "timestamp"),)
