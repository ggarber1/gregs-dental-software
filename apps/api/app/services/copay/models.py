from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class InsuranceCategory(StrEnum):
    DIAGNOSTIC = "diagnostic"
    PREVENTIVE = "preventive"
    BASIC = "basic"
    MAJOR = "major"
    ORTHO = "ortho"
    OTHER = "other"


class PlanType(StrEnum):
    PPO = "ppo"
    PREMIER = "premier"
    MEDICAID = "medicaid"
    INDEMNITY = "indemnity"
    DHMO = "dhmo"


# Procedures are processed in this order so the running deductible/annual-max state is
# applied deterministically: preventive/diagnostic first (usually deductible-waived),
# then basic before major, per industry convention.
CATEGORY_ORDER = ["preventive", "diagnostic", "basic", "major", "ortho", "other"]


@dataclass(frozen=True, kw_only=True)
class ProcedureInput:
    procedure_id: str
    cdt_code: str
    category: str
    provider_fee_cents: int
    allowed_amount_cents: int | None          # None -> fall back to provider_fee
    coinsurance_patient_share: float | None   # None -> needs manual entry
    not_covered: bool = False
    requires_prior_auth: bool = False
    frequency_limit_count: int | None = None
    frequency_used_count: int = 0


@dataclass(frozen=True, kw_only=True)
class EligibilitySnapshot:
    plan_type: PlanType
    network_status: str                        # 'in_network' | 'out_of_network'
    coverage_start_date: date | None
    deductible_remaining_cents: int
    deductible_waived_categories: frozenset[str]
    annual_max_remaining_cents: int | None     # None -> no annual cap returned
    ortho_lifetime_max_remaining_cents: int | None
    waiting_period_months_by_category: dict[str, int]
    has_secondary_insurance: bool = False


@dataclass
class ProcedureResult:
    procedure_id: str
    cdt_code: str
    category: str
    provider_fee_cents: int
    allowed_amount_cents: int
    write_off_cents: int
    deductible_applied_cents: int
    insurance_owes_cents: int
    patient_owes_cents: int
    needs_manual_entry: bool = False
    not_covered: bool = False
    is_frequency_exceeded: bool = False
    is_in_waiting_period: bool = False
    annual_max_cap_applied: bool = False


@dataclass
class PatientResponsibilityBreakdown:
    service_date: date
    plan_type: PlanType
    line_items: list[ProcedureResult] = field(default_factory=list)
    total_provider_fee_cents: int = 0
    total_write_off_cents: int = 0
    total_insurance_owes_cents: int = 0
    total_patient_owes_cents: int = 0
    deductible_remaining_after_cents: int = 0
    annual_max_remaining_after_cents: int | None = None
    has_secondary_insurance: bool = False
