from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin

DELIVERY_METHODS = ("email", "download")


class PatientStatement(Base, PHIMixin):
    """One generated billing statement (emailed or downloaded). Append-only.

    No PDF is stored — it is regenerated on demand from the ledger. `aging_snapshot`
    preserves the bucket totals the patient saw at delivery time, keyed like
    ARBuckets: {"b0_30", "b31_60", "b61_90", "b90_plus"}.
    """

    __tablename__ = "patient_statements"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    delivery_method: Mapped[str] = mapped_column(String(20), nullable=False)
    balance_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    aging_snapshot: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # When the send was accepted (SES MessageId, or dev no-send). Null for downloads.
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_by: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "delivery_method IN ('email', 'download')",
            name="ck_patient_statements_delivery_method",
        ),
        Index(
            "ix_patient_statements_patient_generated",
            "practice_id",
            "patient_id",
            "generated_at",
        ),
        Index("ix_patient_statements_practice_generated", "practice_id", "generated_at"),
    )
