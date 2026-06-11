from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class EligibilityStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


class BenefitCategory(str, Enum):
    PREVENTIVE = "preventive"
    BASIC = "basic"
    MAJOR = "major"
    ORTHODONTIA = "orthodontia"


@dataclass(frozen=True)
class EligibilityRequest:
    payer_id: str
    subscriber_id: str
    group_number: str | None
    subscriber_dob: date
    subscriber_first_name: str
    subscriber_last_name: str
    provider_npi: str
    submitter_id: str | None
    date_of_service: date
    control_number: str


@dataclass(frozen=True)
class EligibilityResult:
    raw_response: dict
    payer_name: str | None
    plan_name: str | None
    status: EligibilityStatus
    coverage_start_date: date | None
    coverage_end_date: date | None
    # Money — integer cents, None = payer did not return it (never default to 0)
    deductible_individual: int | None
    deductible_individual_met: int | None
    deductible_family: int | None
    deductible_family_met: int | None
    oop_max_individual: int | None
    oop_max_individual_met: int | None
    annual_max_individual: int | None
    annual_max_individual_used: int | None
    annual_max_individual_remaining: int | None
    # Coinsurance — patient's share as a fraction (0.20 = patient pays 20%)
    coinsurance_preventive: float | None
    coinsurance_basic: float | None
    coinsurance_major: float | None
    coinsurance_ortho: float | None
    waiting_period_basic_months: int | None
    waiting_period_major_months: int | None
    waiting_period_ortho_months: int | None
    frequency_limits: dict | None = field(default=None)


class EligibilityProviderError(Exception):
    """Raised by a provider. `retryable` → transport/5xx/timeout (router marks 'failed').
    `not_supported` → payer not found / AAA rejection (router marks 'not_supported')."""

    def __init__(self, message: str, *, retryable: bool = False, not_supported: bool = False):
        super().__init__(message)
        self.retryable = retryable
        self.not_supported = not_supported


class EligibilityProvider(ABC):
    @abstractmethod
    async def check_eligibility(self, request: EligibilityRequest) -> EligibilityResult: ...
