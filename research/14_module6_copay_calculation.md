# Module 6: Co-pay / Patient Responsibility Calculation Engine — Implementation Guide

## Opt-In Module

This module is **optional and must be explicitly enabled per practice** via the `features.copay_estimation` flag. It **requires Module 5 (eligibility verification) to be active** — without eligibility data there is nothing to calculate from. Practices can submit claims (Module 7) with manually-entered co-pays without this module enabled.

---

## Core Principle

Pure function. No I/O. No side effects. All money as `Decimal`, never `float`.

**Accounting identity (assert this in every test):**
```
provider_fee == write_off + patient_owes + insurance_owes
```

---

## 1. The Calculation Pipeline (per procedure)

```
Provider Fee
  → Resolve allowed amount (in-network contracted rate or OON UCR)
  → Write-off (subtracted; never collectible from patient)
  → Gatekeeping: not covered? waiting period? frequency exceeded? annual max gone?
  → Deductible applied (patient pays dollar-for-dollar until met; some categories exempt)
  → Coinsurance split (insurance % vs patient %)
  → Annual maximum cap (limits total insurance payment for the year)
  → Final: Insurance Owes / Patient Owes
```

### Step 1 — UCR/Allowed Amount and Write-offs

- **In-network PPO:** `billable_base = min(provider_fee, allowed_amount)`. Write-off = `provider_fee - allowed_amount`. Write-offs average 30–40% nationally.
- **Out-of-network:** `billable_base = provider_fee`. Write-off = $0. Insurance calculates from UCR; gap between provider fee and insurance payment = balance billing to patient.
- **PPO write-off formula:** `write_off = max(0, provider_fee - allowed_amount)`

### Step 2 — Deductible Application

**Deductible does NOT apply to all categories.** Most plans waive deductible for Diagnostic (D0xxx) and Preventive (D1xxx). Store per-carrier as `deductible_waived_for_categories`.

```python
if category not in deductible_waived_for_categories:
    deductible_applied = min(deductible_remaining, allowed_amount)
amount_after_deductible = allowed_amount - deductible_applied
deductible_remaining -= deductible_applied  # running state across procedures
```

### Step 3 — Coinsurance

```python
insurance_payment = amount_after_deductible * insurance_coinsurance_pct
patient_coinsurance = amount_after_deductible * (1 - insurance_coinsurance_pct)
```

**Always pull coinsurance from eligibility check — never hardcode.**

Typical (reference only):
| Category | Insurance pays | Patient pays |
|----------|---------------|--------------|
| Preventive | 100% | 0% |
| Diagnostic | 100% | 0% |
| Basic | 70–80% | 20–30% |
| Major | 50% | 50% |
| Orthodontics | 50% | 50% |

### Step 4 — Annual Maximum Cap

```python
capped_insurance = min(gross_insurance_payment, annual_max_remaining)
annual_max_remaining -= capped_insurance
# Overflow goes to patient
patient_owes += (gross_insurance_payment - capped_insurance)
```

Orthodontics has a **separate lifetime maximum**, not annual. Track in separate bucket.

### Step 5 — Frequency Limitation Check (short-circuit BEFORE coinsurance)

If frequency limit exceeded → insurance pays $0, patient pays full allowed amount.

Common limits:
| Procedure | CDT | Typical Limit |
|-----------|-----|---------------|
| Prophy (adult) | D1110 | 2x per calendar year |
| Bitewing X-rays | D0272/D0274 | 1x per 12 months |
| Full mouth X-rays | D0210 | 1x per 36–60 months |
| Fluoride | D1206/D1208 | 1x/year adult, 2x/year child |
| Comprehensive exam | D0150 | 1x per 36 months |

**Frequency query rule:** Count completed procedures for same patient + CDT code within lookback window WHERE claim status NOT IN ('denied'). **Exclude current visit from count.**

Calendar year resets Jan 1. Rolling N months counts from date of service.

### Step 6 — Waiting Period Check (short-circuit BEFORE coinsurance)

```python
def in_waiting_period(coverage_effective_date, waiting_period_months, service_date):
    if waiting_period_months == 0:
        return False
    clears = coverage_effective_date + relativedelta(months=waiting_period_months)
    return service_date < clears
```

If `waiting_period_waived = True` (prior continuous coverage), skip all waiting period checks.

---

## 2. Plan Type Variations

### Standard PPO/Premier
Full pipeline as above.

### DHMO (Capitation)
Completely different model — no percentage coinsurance, no deductible, no annual max. Patient pays **fixed dollar copay** from carrier's schedule per CDT code.
```python
patient_owes = dhmo_copay_schedule.lookup(cdt_code)
insurance_owes = Decimal("0")
write_off = provider_fee - dhmo_copay  # practice keeps only the copay
```
If CDT code not in DHMO schedule → flag "contact carrier", never estimate.

### MassHealth (Medicaid)
```python
patient_owes = Decimal("0")  # always zero for covered procedures
insurance_owes = masshealth_allowed_amount
write_off = provider_fee - masshealth_allowed_amount
```
- No deductible, no annual max, no coinsurance
- Frequency limits NOT from 271 — hard-code from 101 CMR 314
- Prior auth required for crowns, posterior root canals, perio surgery, dentures — block claim generation if PA not on file
- Implants (D6010–D6067) NOT covered for adults
- MassHealth is always payer of last resort — bill commercial first if dual coverage

---

## 3. CDT Code Categories

| CDT Range | ADA Name | Default Tier |
|-----------|----------|--------------|
| D0100–D0999 | Diagnostic | diagnostic (100%) |
| D1000–D1999 | Preventive | preventive (100%) |
| D2000–D2999 | Restorative | basic (80%) |
| D3000–D3999 | Endodontics | basic (some carriers: major) |
| D4000–D4999 | Periodontics | basic (D4260+ sometimes major) |
| D5000–D5899 | Removable Prostho | major (50%) |
| D6000–D6199 | Implant Services | major (often excluded) |
| D6200–D6999 | Fixed Prostho | major (50%) |
| D7000–D7999 | Oral Surgery | D7140=basic; D7210+=major |
| D8000–D8999 | Orthodontics | orthodontic (lifetime max) |

**Important:** Store category assignments in `carrier_cdt_overrides` table per carrier. Seed defaults, allow per-carrier overrides. Do not hardcode.

**CDT data source:** Buy the ADA CDT book (~$90/year) for authoritative descriptions. Open Dental's GPL-licensed seed data for bootstrap. MassHealth fee schedule (101 CMR 314) is public domain.

---

## 4. Delta Dental Specifics

**Three fundamentally different plan types:**

| Plan | How it works |
|------|-------------|
| PPO | Contracted fee schedule, write-offs, percentage coinsurance |
| Premier | Higher fee schedule (closer to UCR), same deductible/coinsurance structure |
| DeltaCare USA (DHMO) | Fixed dollar copay per CDT code, no deductible/annual max |

**Delta Dental Gotchas:**
1. Frequency periods reset **calendar year (Jan 1)**, not anniversary date
2. **Alternate benefit (downgrade):** Posterior composite → amalgam rate. Patient pays coinsurance on amalgam rate PLUS the gap between composite and amalgam allowed amounts
3. **Preventive deductible waiver** — store per category, not universal
4. Individual (direct) plans have waiting periods; group (employer) plans typically don't

---

## 5. Alternate Benefit / Downgrade (Most Commonly Misimplemented)

When a carrier downgrades D2394 (posterior composite) to D2161 (amalgam):
- `allowed_amount` = composite allowed (e.g. $260)
- `alternate_benefit_allowed_amount` = amalgam allowed (e.g. $140)
- Write-off = `provider_fee - allowed_amount` = `$300 - $260 = $40`
- Insurance pays 80% of amalgam rate = `$140 * 0.80 = $112`
- Patient pays coinsurance on amalgam = `$140 * 0.20 = $28` PLUS gap `$260 - $140 = $120` → total `$148`
- Accounting check: `$40 + $148 + $112 = $300` ✓

**The gap between actual_allowed and downgraded_allowed is patient responsibility, NOT write-off.**

---

## 6. Data Model

### Additional Tables

```sql
-- CDT code catalog
CREATE TABLE cdt_codes (
    id UUID PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    ada_category TEXT NOT NULL,
    default_insurance_category TEXT NOT NULL,  -- 'preventive', 'basic', 'major', etc.
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Carrier-specific overrides
CREATE TABLE carrier_cdt_overrides (
    id UUID PRIMARY KEY,
    insurance_plan_id UUID NOT NULL,
    cdt_code TEXT NOT NULL,
    insurance_category TEXT NOT NULL,
    allowed_amount NUMERIC(10,2),
    alternate_benefit_code TEXT,
    alternate_benefit_allowed_amount NUMERIC(10,2),
    not_covered BOOLEAN DEFAULT false,
    requires_prior_auth BOOLEAN DEFAULT false,
    UNIQUE(insurance_plan_id, cdt_code)
);

-- Calculation results (audit trail)
CREATE TABLE copay_calculations (
    id UUID PRIMARY KEY,
    appointment_id UUID NOT NULL,
    eligibility_check_id UUID NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL,
    total_provider_fee NUMERIC(10,2) NOT NULL,
    total_write_off NUMERIC(10,2) NOT NULL,
    total_insurance_owes NUMERIC(10,2) NOT NULL,
    total_patient_owes NUMERIC(10,2) NOT NULL,
    override_patient_amount NUMERIC(10,2),
    override_note TEXT,
    overridden_by UUID,
    line_items JSONB NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### `eligibility_checks` additional fields needed for Module 6:

```sql
ALTER TABLE eligibility_checks ADD COLUMN plan_type TEXT NOT NULL DEFAULT 'ppo'
    CHECK (plan_type IN ('ppo', 'premier', 'dhmo', 'medicaid', 'indemnity'));
ALTER TABLE eligibility_checks ADD COLUMN network_status TEXT NOT NULL DEFAULT 'in_network';
ALTER TABLE eligibility_checks ADD COLUMN deductible_waived_diagnostic BOOLEAN DEFAULT false;
ALTER TABLE eligibility_checks ADD COLUMN deductible_waived_preventive BOOLEAN DEFAULT true;
ALTER TABLE eligibility_checks ADD COLUMN deductible_waived_orthodontic BOOLEAN DEFAULT false;
ALTER TABLE eligibility_checks ADD COLUMN waiting_period_waived BOOLEAN DEFAULT false;
ALTER TABLE eligibility_checks ADD COLUMN coverage_effective_date DATE;
ALTER TABLE eligibility_checks ADD COLUMN ortho_lifetime_max NUMERIC(10,2);
ALTER TABLE eligibility_checks ADD COLUMN ortho_lifetime_max_used NUMERIC(10,2);
-- frequency_limitations already in schema as JSONB
-- e.g. {"D1110": {"count": 2, "period": "calendar_year"},
--       "D0272": {"count": 1, "period": "rolling_12_months"}}
```

---

## 7. Python Function Signatures

```python
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional


class InsuranceCategory(str, Enum):
    DIAGNOSTIC = "diagnostic"
    PREVENTIVE = "preventive"
    BASIC = "basic"
    MAJOR = "major"
    ORTHODONTIC = "orthodontic"
    NOT_COVERED = "not_covered"


class PlanType(str, Enum):
    PPO = "ppo"
    PREMIER = "premier"
    DHMO = "dhmo"
    MEDICAID = "medicaid"
    INDEMNITY = "indemnity"


class FrequencyPeriod(str, Enum):
    CALENDAR_YEAR = "calendar_year"
    ROLLING_6_MONTHS = "rolling_6_months"
    ROLLING_12_MONTHS = "rolling_12_months"
    ROLLING_36_MONTHS = "rolling_36_months"
    LIFETIME = "lifetime"


@dataclass(frozen=True)
class ProcedureInput:
    procedure_id: str
    cdt_code: str
    provider_fee: Decimal
    insurance_category: InsuranceCategory
    allowed_amount: Optional[Decimal]           # None = OON, use provider_fee
    alternate_benefit_code: Optional[str]
    alternate_benefit_allowed_amount: Optional[Decimal]
    is_not_covered: bool = False
    frequency_limit_count: Optional[int] = None
    frequency_limit_period: Optional[FrequencyPeriod] = None
    frequency_used_count: int = 0               # times already used this period
    dhmo_copay: Optional[Decimal] = None        # DHMO only


@dataclass(frozen=True)
class EligibilitySnapshot:
    plan_type: PlanType
    network_status: str                         # 'in_network' | 'out_of_network'
    coverage_effective_date: Optional[date]
    deductible_remaining: Decimal
    deductible_waived_for_categories: frozenset[InsuranceCategory]
    annual_max_remaining: Decimal
    ortho_lifetime_max_remaining: Optional[Decimal]
    coinsurance_by_category: dict[InsuranceCategory, Decimal]
    waiting_period_months_by_category: dict[InsuranceCategory, int]
    waiting_period_waived: bool
    has_secondary_insurance: bool


@dataclass
class ProcedureResult:
    procedure_id: str
    cdt_code: str
    insurance_category: InsuranceCategory
    provider_fee: Decimal
    allowed_amount: Decimal
    write_off: Decimal
    deductible_applied: Decimal
    insurance_payment: Decimal
    total_patient_owes: Decimal
    total_insurance_owes: Decimal
    not_covered_reason: Optional[str] = None
    is_frequency_exceeded: bool = False
    is_in_waiting_period: bool = False
    is_not_covered: bool = False
    annual_max_cap_applied: bool = False
    is_downgraded: bool = False
    downgrade_code: Optional[str] = None


@dataclass
class PatientResponsibilityBreakdown:
    appointment_id: str
    service_date: date
    plan_type: PlanType
    line_items: list[ProcedureResult]
    total_provider_fee: Decimal
    total_write_off: Decimal
    total_insurance_owes: Decimal
    total_patient_owes: Decimal
    deductible_remaining_after: Decimal
    annual_max_remaining_after: Decimal
    has_secondary_insurance: bool = False
    secondary_insurance_note: str = "Secondary insurance: submit manually after primary EOB"
    eligibility_check_id: str = ""


def calculate_patient_responsibility(
    appointment_id: str,
    service_date: date,
    eligibility: EligibilitySnapshot,
    procedures: list[ProcedureInput],
    eligibility_check_id: str = "",
) -> PatientResponsibilityBreakdown:
    """
    Pure function. No I/O. No side effects.
    Dispatches to plan-type-specific calculator.
    """
    if eligibility.plan_type == PlanType.DHMO:
        return _calculate_dhmo(appointment_id, service_date, eligibility, procedures, eligibility_check_id)
    if eligibility.plan_type == PlanType.MEDICAID:
        return _calculate_medicaid(appointment_id, service_date, eligibility, procedures, eligibility_check_id)
    return _calculate_standard(appointment_id, service_date, eligibility, procedures, eligibility_check_id)
```

---

## 8. Critical Implementation Notes

**Rounding:** Round to cents (`CENT = Decimal("0.01")`) only at final assignment to `ProcedureResult` fields. Never round at intermediate steps — accumulated rounding error across procedures causes accounting identity failures.

**Procedure ordering:** Sort by category (preventive → diagnostic → basic → major → ortho) before calculating. This applies deductible where it hurts least for the patient. Make the ordering explicit and documented.

**Idempotency:** Persist result in `copay_calculations` with `idempotency_key = sha256(appointment_id + eligibility_check_id + sorted_procedure_ids)`. Only recalculate if procedures or eligibility change.

**Frequency query:** Filter `appointment.scheduled_at < :service_date` AND `claim.status NOT IN ('denied')`. Denied claims don't count toward frequency limits.

**MassHealth prior auth:** `requires_prior_auth` flag on `carrier_cdt_overrides`. Block claim generation in Module 7 if PA required and not on file.

---

## 9. Test Cases

```python
# All fees/amounts as Decimal

# Scenario 1: Preventive-only — patient owes $0
# D0120 + D1110, deductible waived, 100% coverage
assert result.total_patient_owes == Decimal("0.00")
assert result.deductible_remaining_after == Decimal("50.00")  # not consumed

# Scenario 2: Basic filling with fresh deductible
# D2392: fee=$200, allowed=$180, deductible=$50, coinsurance=80/20
# write_off=$20, deductible=$50, remaining=$130, insurance=$104, patient=$76
assert li.write_off == Decimal("20.00")
assert li.deductible_applied == Decimal("50.00")
assert li.insurance_payment == Decimal("104.00")
assert li.total_patient_owes == Decimal("76.00")
# identity: 20 + 76 + 104 = 200 ✓

# Scenario 3: Deductible already met
# Same procedure, deductible_remaining=$0
assert li.deductible_applied == Decimal("0.00")
assert li.total_patient_owes == Decimal("36.00")   # 180*20%
assert li.insurance_payment == Decimal("144.00")   # 180*80%

# Scenario 4: Annual max exhausted mid-visit
# annual_max_remaining=$200, major, allowed=$800, deductible met, 50/50
# gross_insurance=$400, capped=$200, overflow=$200 to patient
assert li.annual_max_cap_applied is True
assert li.insurance_payment == Decimal("200.00")
assert li.total_patient_owes == Decimal("600.00")  # 400 coinsurance + 200 overflow

# Scenario 5: Frequency limit exceeded
# D1110, frequency_used_count=2, limit=2/calendar_year
assert li.is_frequency_exceeded is True
assert li.insurance_payment == Decimal("0.00")
assert li.total_patient_owes == li.allowed_amount  # patient pays full allowed

# Scenario 6: Waiting period blocks coverage
# Major procedure, coverage started 3 months ago, 12-month wait
assert li.is_in_waiting_period is True
assert li.insurance_payment == Decimal("0.00")

# Scenario 6b: Waiting period waived (prior continuous coverage)
assert li.is_in_waiting_period is False
assert li.insurance_payment > Decimal("0.00")

# Scenario 7: Deductible splits across two procedures
# deductible=$50, proc1 allowed=$30, proc2 allowed=$200
assert li1.deductible_applied == Decimal("30.00")
assert li2.deductible_applied == Decimal("20.00")
assert result.deductible_remaining_after == Decimal("0.00")

# Scenario 8: MassHealth — patient always $0
assert result.total_patient_owes == Decimal("0.00")
assert result.total_write_off + result.total_insurance_owes == result.total_provider_fee

# Scenario 9: MassHealth implant not covered
assert li.is_not_covered is True
assert li.insurance_payment == Decimal("0.00")
assert li.total_patient_owes == li.allowed_amount

# Scenario 10: DHMO fixed copay
# D2750, dhmo_copay=$350
assert result.total_patient_owes == Decimal("350.00")
assert result.total_insurance_owes == Decimal("0.00")

# Scenario 11: Accounting identity holds for ALL procedures
for li in result.line_items:
    assert li.write_off + li.total_patient_owes + li.total_insurance_owes == li.provider_fee

# Scenario 12: OON balance billing
# fee=$1400, UCR=$900, major 50%, deductible met
# write_off=$0, insurance=$450, patient=$950 ($450 coinsurance + $500 balance bill)
assert li.write_off == Decimal("0.00")
assert li.insurance_payment == Decimal("450.00")
assert li.total_patient_owes == Decimal("950.00")

# Scenario 13: Secondary insurance flagged, not calculated
assert result.has_secondary_insurance is True
assert "secondary" in result.secondary_insurance_note.lower()

# Scenario 14: Alternate benefit downgrade
# D2394 fee=$300, allowed=$260, downgraded to D2161 allowed=$140, basic 80/20, deductible met
# write_off=$40 (300-260), insurance=$112 (140*80%), patient=$148 ($28 coinsurance + $120 gap)
assert li.is_downgraded is True
assert li.write_off == Decimal("40.00")
assert li.insurance_payment == Decimal("112.00")
assert li.total_patient_owes == Decimal("148.00")
# identity: 40 + 148 + 112 = 300 ✓
```

---

## 10. Edge Cases

| Edge Case | Risk | Handling |
|-----------|------|---------|
| Deductible split across multi-procedure visit | Undercharge patient | Apply sequentially, carry running state |
| Annual max exhausted mid-visit | Insurance overpaid | Cap per-procedure, overflow to patient |
| Frequency exceeded for one code in multi-code visit | Wrong coverage on that code | Check per CDT code independently |
| Alternate benefit gap | Most commonly misimplemented | Gap = patient responsibility, NOT write-off |
| OON balance billing | Patient shock | write_off=$0; patient=coinsurance + balance bill |
| DHMO code not in schedule | No copay to look up | Flag "contact carrier", never estimate |
| MassHealth PA required | Claim denied | `requires_prior_auth` flag, block claim generation |
| Ortho lifetime max vs annual max | Wrong bucket | Separate tracking |
| Waiting period waived | Incorrectly blocks coverage | `waiting_period_waived` flag from eligibility |
| Denied claim → frequency | Over-counts | Only count non-denied claims |
| `provider_fee < allowed_amount` | Negative write-off | `write_off = max(0, fee - allowed)` |
| D1110 Dec + Jan | Calendar year reset | Jan 1 boundary for `calendar_year` period |
| Annual max exactly zero | Off-by-one | Check `<= ZERO` not `== ZERO` |
