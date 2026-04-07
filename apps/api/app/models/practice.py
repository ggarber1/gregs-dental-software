from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, String, Text
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.operatory import Operatory
    from app.models.provider import Provider
    from app.models.user import PracticeUser


class Practice(Base, TimestampMixin):
    __tablename__ = "practices"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default="America/New_York",
    )
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address_line1: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_line2: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True)
    zip: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Feature flags — each optional module is gated here.
    # e.g. {"eligibility_verification": true, "copay_estimation": false, "claims_submission": true}
    features: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )

    # Clearinghouse — SSM path only, never store the key directly.
    clearinghouse_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    clearinghouse_submitter_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    clearinghouse_api_key_ssm_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Billing identifiers — tax ID is AES-256 encrypted at the application layer before storage.
    billing_npi: Mapped[str | None] = mapped_column(String(10), nullable=True)
    billing_tax_id_encrypted: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    billing_taxonomy_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    masshealth_provider_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "clearinghouse_provider IN ('stedi', 'dentalxchange')",
            name="ck_practices_clearinghouse_provider",
        ),
    )

    # Relationships (lazy="selectin" deferred — load explicitly when needed)
    practice_users: Mapped[list[PracticeUser]] = relationship(
        "PracticeUser",
        back_populates="practice",
        lazy="selectin",
    )
    providers: Mapped[list[Provider]] = relationship(
        "Provider",
        back_populates="practice",
        lazy="selectin",
    )
    operatories: Mapped[list[Operatory]] = relationship(
        "Operatory",
        back_populates="practice",
        lazy="selectin",
    )
