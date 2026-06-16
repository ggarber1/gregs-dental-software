from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from app.services.eligibility.base import (
    EligibilityResult,
    EligibilityStatus,
)


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


_CDT_RE = re.compile(r"D\d{4}")


def _cdt_category(code: str) -> str:
    """ADA D-code range -> coarse insurance category (matches cdt_codes.category)."""
    try:
        n = int(code[1:])
    except (ValueError, IndexError):
        return "other"
    if n < 1000:
        return "diagnostic"
    if n < 2000:
        return "preventive"
    if n < 5000:
        return "basic"        # restorative/endo/perio default; carrier overrides later
    if n < 8000:
        return "major"
    if n < 9000:
        return "ortho"
    return "other"


def _info_parts(entry: dict[str, Any]) -> list[str]:
    """Return the list of additionalInformation description strings for *entry*."""
    info = entry.get("additionalInformation") or []
    if isinstance(info, dict):
        info = [info]
    return [str(a.get("description", "")) for a in info if isinstance(a, dict)]


def _descriptions(entry: dict[str, Any]) -> str:
    """Lowercased text: additionalInformation descriptions + entry name."""
    parts = _info_parts(entry)
    parts.append(str(entry.get("name", "")))
    return " ".join(parts).lower()


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

    for b in benefits:
        code = b.get("code")
        level = b.get("coverageLevelCode")
        tq = b.get("timeQualifierCode")
        text = _descriptions(b)

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
        # Coinsurance (code "A") is handled below after the main loop.

    coinsurance_by_code: dict[str, float] = {}
    for b in benefits:
        if b.get("code") != "A":
            continue
        pct = b.get("benefitPercent")
        if pct is None:
            continue
        try:
            share = float(pct)
        except (TypeError, ValueError):
            continue
        for part in _info_parts(b):
            for code in _CDT_RE.findall(part):
                coinsurance_by_code[code] = share

    # Per-category fallback = average of the per-code rates in that category.
    _by_cat: dict[str, list[float]] = {}
    for code, share in coinsurance_by_code.items():
        _by_cat.setdefault(_cdt_category(code), []).append(share)

    def _cat_avg(cat: str) -> float | None:
        vals = _by_cat.get(cat)
        return round(sum(vals) / len(vals), 4) if vals else None

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
        coinsurance_preventive=_cat_avg("preventive"),
        coinsurance_basic=_cat_avg("basic"),
        coinsurance_major=_cat_avg("major"),
        coinsurance_ortho=_cat_avg("ortho"),
        waiting_period_basic_months=None,
        waiting_period_major_months=None,
        waiting_period_ortho_months=None,
        frequency_limits=None,
        coinsurance_by_code=coinsurance_by_code or None,
    )
