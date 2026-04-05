# Module 5: Real-Time Dental Insurance Eligibility Verification — Implementation Guide

## Opt-In Module

This module is **optional and must be explicitly enabled per practice** via the `features.eligibility_verification` flag. Practices can use scheduling, reminders, and patient records without it. Enabling requires clearinghouse credentials and a passing test eligibility check before activation.

Module 6 (co-pay estimation) cannot be enabled unless this module is active.

---

## ⚠️ Data Staleness Warning

**The 271 eligibility response is a snapshot, not a live ledger.**

Payers batch-update their internal deductible and annual maximum tracking on their own schedule — often daily, sometimes weekly. The 271 response reflects whenever the payer last ran their reconciliation, not what happened this morning.

**What this means in practice:**
- A patient had a filling last week. Their primary care dentist submitted a claim. The payer processed it and reduced their deductible by $30. Your eligibility check today may still return the pre-claim deductible balance.
- Annual maximum remaining has the same staleness problem. A patient near their cap who had work done elsewhere may show more remaining than they actually have.
- During high-volume periods (October–December as patients burn benefits), this lag is worst.

**Reliability by field:**

| Field | Reliability | Notes |
|-------|-------------|-------|
| Active/inactive status | High | Core purpose of 271, updated promptly |
| Coverage dates | High | Static plan data |
| Plan name / coinsurance % | High | Static plan data, rarely changes mid-year |
| Waiting periods | Medium | Static plan data |
| Annual max total | High | Set at plan level |
| Deductible total | High | Set at plan level |
| Deductible remaining | Low–Medium | Batch updated; may lag days or weeks |
| Annual max remaining | Low–Medium | Same staleness issue |
| Frequency limits used | Low | Often not returned; MassHealth never returns it |

**How to handle this in the UI:**
- Always show a "verified as of [timestamp]" label on eligibility data
- Display remaining deductible/annual max as estimates: `~$20 remaining*`
- Include a disclaimer: `* As of last payer update. May not reflect claims processed in the last 1–7 days.`
- Never present a calculated co-pay as exact without a human review step (dad's override)
- The co-pay calculator (Module 6) must treat these fields as estimates, not facts

**Why this matters for Module 6:**
Module 6's accuracy ceiling is Module 5's data quality. A $30 deductible discrepancy on a basic filling translates directly to a $30 mis-collection — either from the patient (refund situation) or absorbed by the practice. Build Module 6 as an estimator with mandatory staff confirmation, not an automated collector.

---

## Clearinghouse Strategy

- **Dev/staging:** Stedi — REST/JSON, free tier, immediate access, no raw EDI needed
- **Production:** DentalXChange Enhanced Eligibility API — AI-normalized benefit breakdowns, dental-specific

---

## 1. Stedi Eligibility API

**Endpoint:** `POST https://healthcare.us.stedi.com/2024-04-01/change/medicalnetwork/eligibility/v3`

**Auth:** `Authorization: ApiKey <key>` header

### Request Payload
```json
{
  "controlNumber": "000000001",
  "tradingPartnerServiceId": "CDELT",
  "provider": {
    "organizationName": "Downtown Family Dental",
    "npi": "1234567890",
    "serviceProviderNumber": "your-submitter-id"
  },
  "subscriber": {
    "memberId": "XYZ123456789",
    "firstName": "John",
    "lastName": "Smith",
    "dateOfBirth": "19800101",
    "groupNumber": "GRP001"
  },
  "encounter": {
    "dateOfService": "20260410",
    "serviceTypeCodes": ["35", "27", "F3", "AJ"]
  }
}
```

**Key points:**
- `tradingPartnerServiceId` = clearinghouse payer ID (use Search Payers API: `GET /payers/search?query=delta+dental&coverageTypes=dental`)
- Always send multiple `serviceTypeCodes` for dental: `"35"` (Dental Care), `"27"` (Dental Specialty), `"F3"` (Dental Accident), `"AJ"` (Preventive)
- `controlNumber` must be unique per request — UUID or sequential, 9 digits max
- `dateOfBirth` format: `YYYYMMDD`

### Response: `benefitsInformation` Array

Iterate by `code` + `serviceTypeCodes` + `coverageLevelCode` + `timeQualifierCode`:

| `code` | Meaning |
|--------|---------|
| `1` | Active Coverage |
| `6` | Inactive |
| `A` | Co-Insurance |
| `C` | Deductible |
| `F` | Limitations (annual max, frequency) |
| `G` | Out-of-Pocket max |

| `coverageLevelCode` | Meaning |
|---------------------|---------|
| `IND` | Individual |
| `FAM` | Family |

| `timeQualifierCode` | Meaning |
|---------------------|---------|
| `23` | Calendar Year total |
| `29` | Remaining |
| `26` | Lifetime |

---

## 2. DentalXChange Enhanced Eligibility API (Production)

**What "Enhanced" means:** AI layer normalizes 271 into structured JSON (deductibles, coinsurance %, annual max, frequency limits, waiting periods) — no payer-specific X12 parsing needed.

**Auth:** OAuth 2.0 client credentials → bearer token

**Request:**
```http
POST https://api.dentalxchange.com/xconnect/v2/enhanced-eligibility
Authorization: Bearer <token>
Content-Type: application/json

{
  "payerId": "CDELT",
  "subscriberId": "XYZ123456789",
  "groupNumber": "GRP001",
  "subscriberDateOfBirth": "1980-01-01",
  "subscriberFirstName": "John",
  "subscriberLastName": "Smith",
  "providerNpi": "1234567890",
  "dateOfService": "2026-04-10"
}
```

**Response:** Structured JSON with `eligibilityStatus`, `deductible.individual.{total,met}`, `annualMaximum.individual.{total,used,remaining}`, `benefitsByCategory` array (preventive/basic/major/ortho coinsurance %), `frequencyLimitations`, `waitingPeriods`, `rawResponse`.

---

## 3. X12 271 Parsing Gotchas

**Don't write a raw X12 parser for Phase 1** — both Stedi and DentalXChange Enhanced return JSON. Isolate raw parsing behind the `EligibilityProvider` interface for fallback.

### Common Payer Quirks

1. **Coinsurance convention is inconsistent** — some payers return `0.20` (patient pays 20%), others return `0.80` (insurance pays 80%). Detect by reading `additionalInformation.description` text.

2. **Missing remaining deductible** — many payers return the calendar year total but omit the remaining segment. Store `null`, never default to zero.

3. **Annual max in multiple places** — `EB01=F, timeQualifierCode=23` is total; `=29` is remaining. Some payers use `EB01=MC` for used amount. Correlate all F segments.

4. **Ortho has no dedicated service type code** — returns under STC `35` with plan description containing "ORTHO". Scan EB05 and MSG segments case-insensitively.

5. **MassHealth (CKMA1) is sparse** — active/inactive and basic deductible info only. Frequency limits NOT returned in 271 for CKMA1. Hard-code from MassHealth published fee schedule and store as reference data.

6. **Contradictory active/inactive** — always take status from first `EB01=1` in Loop 2110C, ignore dependent loop.

---

## 4. Python EligibilityProvider Interface

```python
# apps/api/services/eligibility/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional


class EligibilityStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


class BenefitCategory(str, Enum):
    PREVENTIVE = "preventive"
    BASIC = "basic"
    MAJOR = "major"
    ORTHODONTIA = "orthodontia"
    GENERAL = "general"


@dataclass(frozen=True)
class CategoryBenefit:
    category: BenefitCategory
    coinsurance_pct: Optional[Decimal]          # 0.80 = insurance pays 80%
    annual_max: Optional[Decimal]
    annual_max_used: Optional[Decimal]
    annual_max_remaining: Optional[Decimal]
    frequency_limit_description: Optional[str]
    waiting_period_months: Optional[int]


@dataclass(frozen=True)
class EligibilityResult:
    raw_response: dict
    payer_name: Optional[str]
    plan_name: Optional[str]
    status: EligibilityStatus
    coverage_start_date: Optional[date]
    coverage_end_date: Optional[date]
    deductible_individual: Optional[Decimal]
    deductible_individual_met: Optional[Decimal]
    deductible_family: Optional[Decimal]
    deductible_family_met: Optional[Decimal]
    oop_max_individual: Optional[Decimal]
    oop_max_individual_met: Optional[Decimal]
    annual_max_individual: Optional[Decimal]
    annual_max_individual_used: Optional[Decimal]
    annual_max_individual_remaining: Optional[Decimal]
    benefits_by_category: dict[BenefitCategory, CategoryBenefit]
    clearinghouse: str
    payer_id_used: str
    request_id: str


@dataclass(frozen=True)
class EligibilityRequest:
    payer_id: str
    subscriber_id: str
    group_number: Optional[str]
    subscriber_dob: date
    subscriber_first_name: str
    subscriber_last_name: str
    provider_npi: str
    date_of_service: date
    idempotency_key: str


class EligibilityProvider(ABC):
    @abstractmethod
    async def check_eligibility(self, request: EligibilityRequest) -> EligibilityResult: ...

    @abstractmethod
    async def search_payer(self, query: str) -> list[dict]: ...


class EligibilityProviderError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable
```

---

## 5. Async Architecture

| Scenario | Approach |
|----------|----------|
| Front desk triggers check from UI | Synchronous with 30s timeout; 202+poll if slow |
| Pre-appointment batch (3 days before) | Async via SQS |
| Patient checks in (day-of re-verify) | Async, push notification when done |
| New insurance added | Async, fire-and-forget |

### Pre-Appointment Batch Flow

```
EventBridge Scheduler (cron: 0 2 * * *)
  → Lambda: eligibility_scheduler
      Queries appointments WHERE appt_date = NOW() + 3 days
      AND no recent verified check
      For each: PUT message on SQS eligibility-queue
                idempotency_key = "{appointment_id}_3day_precheck_{date}"
  → SQS: dental-eligibility-queue
      Standard queue, DLQ after 3 attempts, visibility timeout 60s
  → ECS Fargate: eligibility-worker (long-poll)
      1. Check DB for idempotency key — if verified, delete message, skip
      2. INSERT eligibility_checks row status='pending'
      3. Call clearinghouse API
      4. Parse response → structured benefits
      5. UPDATE eligibility_checks status='verified'
      6. DELETE SQS message
      On non-retryable error: mark 'failed', alert staff via SES, delete message
      On retryable error: do NOT delete — SQS redelivers
      After DLQ: staff alert, never silently skip
```

### SQS Message Format
```json
{
  "appointment_id": "uuid",
  "patient_id": "uuid",
  "insurance_id": "uuid",
  "payer_id": "CDELT",
  "subscriber_id": "XYZ123456789",
  "group_number": "GRP001",
  "subscriber_dob": "1980-01-01",
  "subscriber_first_name": "John",
  "subscriber_last_name": "Smith",
  "provider_npi": "1234567890",
  "date_of_service": "2026-04-10",
  "idempotency_key": "appt_uuid_3day_precheck_20260407",
  "trigger": "pre_appointment_batch",
  "enqueued_at": "2026-04-07T02:00:00Z"
}
```

---

## 6. Payer Coverage Gaps — Fallback Strategy

1. Try clearinghouse (Stedi dev / DentalXChange prod)
2. If payer not found or returns AAA rejection: mark check as `not_supported`, alert staff with payer portal URL
3. Staff verifies manually via payer portal or phone
4. Staff enters benefit data via structured form in UI → populates `eligibility_checks` with `clearinghouse='manual'`

**Never silently skip.** `not_supported` is a first-class status, not an error.

---

## 7. MassHealth (CKMA1) Specifics

- Supports real-time 270/271 via approved clearinghouses — no special portal needed
- Payer ID: `CKMA1` (DentaQuest TPA as of Feb 1, 2026)
- 271 returns: active/inactive, coverage dates, deductible (usually zero), annual max
- 271 does NOT return: frequency limits, waiting periods
- **Frequency limits must be hard-coded** from MassHealth published fee schedule as `payer_id_overrides` reference data
- No waiting periods for active MassHealth members

---

## 8. Database Schema: `eligibility_checks`

```sql
CREATE TABLE eligibility_checks (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    practice_id                     UUID NOT NULL REFERENCES practices(id),
    patient_id                      UUID NOT NULL REFERENCES patients(id),
    patient_insurance_id            UUID NOT NULL REFERENCES patient_insurance(id),
    appointment_id                  UUID REFERENCES appointments(id),
    idempotency_key                 TEXT NOT NULL UNIQUE,
    status                          TEXT NOT NULL DEFAULT 'pending'
                                        CHECK (status IN ('pending','verified','failed','not_supported')),
    trigger                         TEXT NOT NULL
                                        CHECK (trigger IN ('pre_appointment_batch','manual','on_checkin','new_insurance')),
    requested_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at                     TIMESTAMPTZ,
    failed_at                       TIMESTAMPTZ,
    failure_reason                  TEXT,
    clearinghouse                   TEXT NOT NULL CHECK (clearinghouse IN ('stedi','dentalxchange','manual')),
    payer_id_used                   TEXT NOT NULL,
    payer_name                      TEXT,
    plan_name                       TEXT,
    coverage_status                 TEXT CHECK (coverage_status IN ('active','inactive','unknown')),
    coverage_start_date             DATE,
    coverage_end_date               DATE,
    -- Deductible (NULL = payer did not return)
    deductible_individual           NUMERIC(10,2),
    deductible_individual_met       NUMERIC(10,2),
    deductible_family               NUMERIC(10,2),
    deductible_family_met           NUMERIC(10,2),
    oop_max_individual              NUMERIC(10,2),
    oop_max_individual_met          NUMERIC(10,2),
    annual_max_individual           NUMERIC(10,2),
    annual_max_individual_used      NUMERIC(10,2),
    annual_max_individual_remaining NUMERIC(10,2),
    -- Coinsurance (0.80 = insurance pays 80%, NULL = not returned)
    coinsurance_preventive          NUMERIC(5,4),
    coinsurance_basic               NUMERIC(5,4),
    coinsurance_major               NUMERIC(5,4),
    coinsurance_ortho               NUMERIC(5,4),
    frequency_limits_json           JSONB,
    waiting_period_basic_months     INTEGER,
    waiting_period_major_months     INTEGER,
    waiting_period_ortho_months     INTEGER,
    raw_response                    JSONB NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_eligibility_checks_patient     ON eligibility_checks(patient_id);
CREATE INDEX idx_eligibility_checks_appointment ON eligibility_checks(appointment_id);
CREATE INDEX idx_eligibility_checks_idempotency ON eligibility_checks(idempotency_key);
CREATE INDEX idx_eligibility_checks_status      ON eligibility_checks(status) WHERE status = 'pending';
```

---

## 9. Key Implementation Decisions

| Decision | Choice |
|----------|--------|
| Dev clearinghouse | Stedi — sign up Day 1, free, immediate |
| Production clearinghouse | DentalXChange Enhanced — apply for sandbox immediately (2–4 week queue) |
| Raw X12 parsing | Not needed in Phase 1 — both return JSON |
| Null handling | Never default null benefit fields to zero |
| MassHealth frequency limits | Hard-code from published fee schedule |
| Payer not found | `not_supported` status + staff alert, never silently skip |
| Secondary insurance | Flag for manual review — no COB auto-calculation in Phase 1 |
| Idempotency key | `{appointment_id}_{trigger}_{date}` — deduplicated at worker and DB level |
