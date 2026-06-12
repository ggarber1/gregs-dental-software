from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.services.eligibility.base import (
    BenefitCategory,
    EligibilityResult,
    EligibilityStatus,
)

_INSURANCE_KEYWORDS = ("insurance", "plan pays", "carrier")


def _money_to_cents(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _info_parts(entry: dict[str, Any]) -> list[str]:
    """Return the list of additionalInformation description strings for *entry*."""
    info = entry.get("additionalInformation") or []
    if isinstance(info, dict):
        info = [info]
    return [str(a.get("description", "")) for a in info if isinstance(a, dict)]


def _additional_info_text(entry: dict[str, Any]) -> str:
    """Concatenate additionalInformation descriptions only (no entry name)."""
    return " ".join(_info_parts(entry)).lower()


def _descriptions(entry: dict[str, Any]) -> str:
    """Full text: additionalInformation descriptions + entry name (for categorization)."""
    parts = _info_parts(entry)
    parts.append(str(entry.get("name", "")))
    return " ".join(parts).lower()


def _categorize(text: str) -> BenefitCategory:
    if "ortho" in text:
        return BenefitCategory.ORTHODONTIA
    if any(k in text for k in ("preventive", "diagnostic", "routine")):
        return BenefitCategory.PREVENTIVE
    if any(k in text for k in ("major", "crown", "prosthodontic", "prosthetic")):
        return BenefitCategory.MAJOR
    return BenefitCategory.BASIC


def _patient_share(pct: float, additional_text: str) -> float:
    """Detect insurance-share convention from additionalInformation descriptions only.

    The entry name (e.g. "Co-Insurance") contains "insurance" as a substring,
    so we must NOT include it in the insurance-share detection — only the
    additionalInformation descriptions should be checked.
    """
    if any(k in additional_text for k in _INSURANCE_KEYWORDS):
        return round(1.0 - pct, 4)
    return round(pct, 4)


def parse_stedi_response(raw: dict[str, Any]) -> EligibilityResult:
    benefits = raw.get("benefitsInformation", []) or []

    status = EligibilityStatus.UNKNOWN
    for b in benefits:
        if b.get("code") == "1":
            status = EligibilityStatus.ACTIVE
            break
        if b.get("code") == "6":
            status = EligibilityStatus.INACTIVE
            break

    deductible_ind = deductible_fam = None
    annual_max = annual_max_remaining = annual_max_used = None
    oop_ind = None
    coins: dict[BenefitCategory, float] = {}

    for b in benefits:
        code = b.get("code")
        level = b.get("coverageLevelCode")
        tq = b.get("timeQualifierCode")
        text = _descriptions(b)  # full text (name + additionalInformation) for categorization
        # additionalInformation only — for insurance-share detection
        additional_text = _additional_info_text(b)

        if code == "C":
            amt = _money_to_cents(b.get("benefitAmount"))
            if level == "FAM":
                # First-wins: keep existing value if already set
                if deductible_fam is None:
                    deductible_fam = amt
            else:
                # First-wins: keep existing value if already set
                if deductible_ind is None:
                    deductible_ind = amt
        elif code == "F":
            amt = _money_to_cents(b.get("benefitAmount"))
            if tq == "29":
                # First-wins
                if annual_max_remaining is None:
                    annual_max_remaining = amt
            elif "used" in text:
                # First-wins
                if annual_max_used is None:
                    annual_max_used = amt
            else:
                # First-wins
                if annual_max is None:
                    annual_max = amt
        elif code == "G" and level != "FAM":
            amt = _money_to_cents(b.get("benefitAmount"))
            # First-wins
            if oop_ind is None:
                oop_ind = amt
        elif code == "A":
            pct_raw = b.get("benefitPercent")
            if pct_raw not in (None, ""):
                try:
                    pct = float(pct_raw)
                except ValueError:
                    continue
                # Normalize whole-number percent (e.g. "80" means 80%, not 8000%)
                if pct > 1.0:
                    pct = pct / 100.0
                share = _patient_share(pct, additional_text)
                # First-wins: first coinsurance value for a category sticks;
                # real 271s break BASIC out by procedure so deterministic ordering matters.
                coins.setdefault(_categorize(text), share)

    # Real payers populate different plan-name fields: Cigna uses
    # planNetworkIdDescription (e.g. "TOTAL CIGNA DPPO"); others use planDescription.
    plan_name = None
    plan_info = raw.get("planInformation") or {}
    for key in ("planDescription", "planNetworkIdDescription", "groupDescription"):
        if plan_info.get(key):
            plan_name = str(plan_info[key])
            break

    dates = raw.get("planDateInformation") or {}

    return EligibilityResult(
        raw_response=raw,
        payer_name=(raw.get("payer") or {}).get("name"),
        plan_name=plan_name,
        status=status,
        coverage_start_date=_parse_date(dates.get("planBegin")),
        coverage_end_date=_parse_date(dates.get("planEnd")),
        deductible_individual=deductible_ind,
        deductible_individual_met=None,
        deductible_family=deductible_fam,
        deductible_family_met=None,
        oop_max_individual=oop_ind,
        oop_max_individual_met=None,
        annual_max_individual=annual_max,
        annual_max_individual_used=annual_max_used,
        annual_max_individual_remaining=annual_max_remaining,
        coinsurance_preventive=coins.get(BenefitCategory.PREVENTIVE),
        coinsurance_basic=coins.get(BenefitCategory.BASIC),
        coinsurance_major=coins.get(BenefitCategory.MAJOR),
        coinsurance_ortho=coins.get(BenefitCategory.ORTHODONTIA),
        waiting_period_basic_months=None,
        waiting_period_major_months=None,
        waiting_period_ortho_months=None,
        frequency_limits=None,
    )
