from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True, kw_only=True)
class Address:
    line1: str
    city: str
    state: str
    postal_code: str


@dataclass(frozen=True, kw_only=True)
class ClaimLine:
    procedure_id: str          # appointment_procedure.id -> lineItemControlNumber (835 correlation)
    cdt_code: str              # D####
    fee_cents: int
    tooth_number: str | None
    surface: str | None
    procedure_name: str


@dataclass(frozen=True, kw_only=True)
class DentalClaimInput:
    patient_control_number: str       # CLM01; <= 20 chars for Stedi JSON
    payer_id: str
    usage_indicator: str              # "T" (test) or "P" (production)
    # Billing provider (the practice)
    billing_npi: str
    billing_tax_id: str               # decrypted, digits only
    billing_taxonomy_code: str
    billing_org_name: str
    billing_address: Address
    submitter_id: str
    # Rendering provider
    rendering_npi: str
    rendering_first_name: str
    rendering_last_name: str
    # Subscriber / insured
    subscriber_first_name: str
    subscriber_last_name: str
    subscriber_dob: date
    subscriber_gender: str            # 'M' | 'F' | 'U'
    subscriber_address: Address
    member_id: str
    group_number: str | None
    relationship_to_insured: str      # 'self' | 'spouse' | 'child' | 'other'
    # Patient (used when relationship != self; equals subscriber when self)
    patient_first_name: str
    patient_last_name: str
    patient_dob: date
    patient_gender: str               # 'M' | 'F' | 'U'
    # Claim
    date_of_service: date
    lines: tuple[ClaimLine, ...]
    # Resubmission: "1" = original, "7" = corrected replacement of a prior denied claim.
    claim_frequency_code: str = "1"
    # For corrected claims (frequency_code="7"): the payer's original claim control number
    # from the denial ERA. Included in the Stedi JSON payload for carrier match-back.
    original_claim_reference: str | None = None
    attachment_refs: tuple[AttachmentRef, ...] = ()

    @property
    def total_charge_cents(self) -> int:
        return sum(line.fee_cents for line in self.lines)


@dataclass(frozen=True, kw_only=True)
class AttachmentRef:
    attachment_type: str   # xray | photo | perio_narrative | lab_rx | other
    pwk01_code: str        # B4 | DA | DG | 77 | OB
    stedi_attachment_id: str | None     # set when payer supports 275
    attachment_control_number: str | None  # set in fallback path


@dataclass(frozen=True)
class ClaimResult:
    accepted: bool
    clearinghouse_claim_id: str | None
    clearinghouse_status: str | None
    errors: list[str]
    raw_request: dict[str, Any]
    raw_response: dict[str, Any]
    # Attachment submission outcome (populated when attachments were attempted)
    attachments_sent: int = 0
    attachments_manual: list[str] = field(default_factory=list)
    payer_supports_275: bool = True


class ClaimSubmissionError(Exception):
    """Raised by a clearinghouse client on a transport/server failure.

    `retryable` -> timeout/5xx/transport: the router marks the claim
    'submission_failed' and the same idempotency key may be retried safely.
    """

    def __init__(self, message: str, *, retryable: bool = False, payer_unsupported: bool = False):
        super().__init__(message)
        self.retryable = retryable
        self.payer_unsupported = payer_unsupported


class ClearinghouseClient(ABC):
    @abstractmethod
    async def submit_dental_claim(
        self, claim: DentalClaimInput, idempotency_key: str
    ) -> ClaimResult: ...

    @abstractmethod
    async def upload_claim_attachment(
        self, file_bytes: bytes, content_type: str, file_name: str
    ) -> str:
        """Upload a file to the clearinghouse and return the attachment ID."""
        ...
