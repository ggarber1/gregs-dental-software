from __future__ import annotations

from datetime import date, datetime

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


def _additional_info_text(entry: dict) -> str:
    """Concatenate additionalInformation descriptions only (no entry name)."""
    parts = [str(a.get("description", "")) for a in entry.get("additionalInformation", [])]
    return " ".join(parts).lower()


def _descriptions(entry: dict) -> str:
    """Full text: additionalInformation descriptions + entry name (for categorization)."""
    parts = [str(a.get("description", "")) for a in entry.get("additionalInformation", [])]
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


def parse_stedi_response(raw: dict) -> EligibilityResult:
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
        additional_text = _additional_info_text(b)  # additionalInformation only for insurance-share detection

        if code == "C":
            amt = _money_to_cents(b.get("benefitAmount"))
            if level == "FAM":
                deductible_fam = deductible_fam if amt is None else amt
            else:
                deductible_ind = deductible_ind if amt is None else amt
        elif code == "F":
            amt = _money_to_cents(b.get("benefitAmount"))
            if tq == "29":
                annual_max_remaining = annual_max_remaining if amt is None else amt
            elif "used" in text:
                annual_max_used = annual_max_used if amt is None else amt
            else:
                annual_max = annual_max if amt is None else amt
        elif code == "G" and level != "FAM":
            amt = _money_to_cents(b.get("benefitAmount"))
            oop_ind = oop_ind if amt is None else amt
        elif code == "A":
            pct_raw = b.get("benefitPercent")
            if pct_raw not in (None, ""):
                try:
                    share = _patient_share(float(pct_raw), additional_text)
                except ValueError:
                    continue
                coins[_categorize(text)] = share

    plan_name = None
    plan_info = raw.get("planInformation") or {}
    if plan_info.get("planDescription"):
        plan_name = str(plan_info["planDescription"])

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
