# Module 7: Dental Claims Submission (837D) and ERA Processing (835) — Implementation Guide

## Opt-In Module

This module is **optional and must be explicitly enabled per practice** via the `features.claims_submission` flag. Enabling requires NPI, tax ID, taxonomy code, and clearinghouse credentials. A test claim must pass in sandbox before the module activates for live patients. Practices can use all other modules without it — they continue submitting claims through their existing workflow (Eaglesoft, manual portal entry, etc.) while using this system for everything else.

This module is independent of Modules 5 and 6 — claims can be submitted with manually-entered co-pays without eligibility verification enabled.

---

## Key Decisions Up Front

1. **Generate X12 directly** with a custom `X12Builder` — don't use pyx12 (it validates, doesn't generate)
2. **Stedi uses JSON in dev/staging** — DentalXChange requires raw X12 in production; your `ClearinghouseClient` protocol hides this
3. **Idempotency key is deterministic**, not random — `sha256(appointment_id:patient_id:insurance_id:v{attempt})`. Random UUIDs break re-run safety
4. **ERA parsing: write your own** — simple `~` segment splitting, no library needed for Phase 1
5. **MassHealth:** standard path except `claim_filing_code = "MA"` and DentaQuest provider enrollment ID
6. **Secondary claims:** manual review in Phase 1 — store primary EOB data, surface in UI

---

## 1. 837D Format Fundamentals

The 837D is the HIPAA-standard dental claim (ASC X12N 005010X224A2). Key difference from 837P (medical): uses `SV3` (Dental Service Line) instead of `SV1` (Professional Service Line). SV3 carries CDT procedure codes (D-codes), tooth numbers, and surfaces.

### Transaction Structure

```
ISA/GS    — Interchange envelope
ST*837    — Transaction set
BHT       — Beginning (claim type CH)
NM1*41    — Submitter
NM1*40    — Receiver (clearinghouse/payer)
NM1*85    — Billing provider + N3/N4 address, REF*EI tax ID
SBR       — Subscriber (P=primary, S=secondary)
NM1*IL    — Insured + DMG date of birth/gender
NM1*PR    — Payer name
CLM       — Claim (PCN, total charge, place of service)
DTP*472   — Date of service
NM1*82    — Rendering provider
LX/SV3    — Service line (CDT code, fee, units)
TOO       — Tooth information (situational)
SE/GE/IEA — Trailers
```

### SV3 Segment
```
SV3*AD:D0274*285.00*UN*1***1~
     ^  ^    ^fee   ^unit ^qty ^tooth count
     qualifier:CDT code
```
- `AD` = dental procedure code qualifier (always `AD` for CDT, never `HC`)
- Element 3 is always `UN` (unit) for dental

### TOO Segment (tooth information)
```
TOO*JP*5*1~
    ^area ^surface ^tooth number
```
Area: JP=upper right, JQ=upper left, JR=lower left, JS=lower right

---

## 2. Python X12 Builder

```python
# api/services/claims/x12_builder.py

from dataclasses import dataclass


@dataclass
class Segment:
    tag: str
    elements: list[str]

    def render(self) -> str:
        return "*".join([self.tag] + self.elements) + "~"


class X12Builder:
    """Append-only X12 document builder. Not thread-safe; create one per claim."""

    def __init__(self) -> None:
        self._segments: list[Segment] = []
        self._segment_count = 0

    def add(self, tag: str, *elements: str) -> "X12Builder":
        self._segments.append(Segment(tag=tag, elements=list(elements)))
        if tag not in ("ISA", "GS", "GE", "IEA"):
            self._segment_count += 1
        return self

    def render(self) -> str:
        return "\n".join(s.render() for s in self._segments)

    @property
    def segment_count(self) -> int:
        return self._segment_count
```

### Using the Builder (key segments)
```python
b = X12Builder()
b.add("ISA", "00", "          ", "00", "          ",
      "ZZ", submitter_id.ljust(15), "ZZ", payer_id.ljust(15),
      today.strftime("%y%m%d"), "1200", "^", "00501",
      control_number.zfill(9), "0", "T", ":")  # "T"=test, "P"=production
b.add("GS", "DX", submitter_id, payer_id, now_date, now_time,
      group_control_number, "X", "005010X224A2")
b.add("ST", "837", "0001", "005010X224A2")
b.add("BHT", "0019", "00", patient_control_number[:20], now_date, now_time, "CH")
# ... providers, subscriber, claim, service lines ...
b.add("SE", str(b.segment_count + 2), "0001")
b.add("GE", "1", group_control_number)
b.add("IEA", "1", control_number.zfill(9))
return b.render()
```

---

## 3. Pre-Submission Validation

```python
# api/services/claims/claim_validator.py

import re
from dataclasses import dataclass
from decimal import Decimal

VALID_CDT = re.compile(r"^D\d{4}$")
VALID_NPI = re.compile(r"^\d{10}$")
VALID_TAX_ID = re.compile(r"^\d{9}$")

@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]

def validate_claim(claim) -> ValidationResult:
    errors, warnings = [], []

    if not VALID_NPI.match(claim.billing_provider.npi or ""):
        errors.append(f"Billing NPI invalid: {claim.billing_provider.npi!r}")
    if not VALID_NPI.match(claim.rendering_provider.npi or ""):
        errors.append(f"Rendering NPI invalid: {claim.rendering_provider.npi!r}")
    if not VALID_TAX_ID.match(re.sub(r"[-]", "", claim.billing_provider.tax_id or "")):
        errors.append("Tax ID (EIN) invalid")
    if not claim.procedures:
        errors.append("No procedures on claim")
    for i, proc in enumerate(claim.procedures, 1):
        if not VALID_CDT.match(proc.cdt_code or ""):
            errors.append(f"Line {i}: CDT code {proc.cdt_code!r} must be D + 4 digits")
        if proc.fee <= Decimal("0"):
            errors.append(f"Line {i}: fee must be > 0")
        if proc.fee > Decimal("5000"):
            warnings.append(f"Line {i}: fee {proc.fee} is unusually high — verify")
        # Tooth number required for restorative, endo, perio
        if any(proc.cdt_code.startswith(p) for p in ("D2", "D3", "D4")) and not proc.tooth_number:
            warnings.append(f"Line {i}: {proc.cdt_code} typically requires a tooth number")
    if len(claim.patient_control_number) > 38:
        errors.append("PCN must be ≤ 38 characters")
    # MassHealth-specific
    if claim.payer_id == "CKMA1" and claim.claim_filing_code != "MA":
        errors.append("MassHealth claims require claim_filing_code = 'MA'")

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
```

---

## 4. Idempotency Key Pattern

```python
import hashlib

def generate_claim_idempotency_key(
    appointment_id: str,
    patient_id: str,
    insurance_id: str,
    submission_attempt: int = 1,
) -> str:
    """
    Deterministic. Same inputs always produce same key.
    Increment submission_attempt ONLY for intentional resubmission after denial.
    NEVER increment for network retry of a failed call.
    """
    raw = f"claim:{appointment_id}:{patient_id}:{insurance_id}:v{submission_attempt}"
    return hashlib.sha256(raw.encode()).hexdigest()
```

**The distinction:**
- **Retry** (same key): network timeout, 5xx, worker crash → clearinghouse returns cached result, no duplicate
- **Resubmission** (new key, incremented attempt): claim denied, corrected, re-filed → treated as new claim

---

## 5. Claims Service

```python
# api/services/claims/claims_service.py

from datetime import datetime, timezone
import uuid

class ClaimsService:
    def __init__(self, clearinghouse, db) -> None:
        self._clearinghouse = clearinghouse
        self._db = db

    def submit_claim(self, appointment_id: str, idempotency_key: str) -> str:
        # Idempotency check
        existing = self._db.claims.find_by_idempotency_key(idempotency_key)
        if existing:
            return existing.id

        claim_input = self._build_claim_input(appointment_id)
        validation = validate_claim(claim_input)
        if not validation.valid:
            raise ClaimValidationError(validation.errors)

        claim_id = str(uuid.uuid4())

        # Persist BEFORE network call — if we crash, record exists for retry
        self._db.claims.create(
            id=claim_id,
            appointment_id=appointment_id,
            idempotency_key=idempotency_key,
            status="draft",
            raw_submission=build_837d(claim_input),
            created_at=datetime.now(timezone.utc),
        )

        result = self._clearinghouse.submit_dental_claim(claim_input, idempotency_key)

        self._db.claims.update(
            id=claim_id,
            status="submitted" if result.success else "submission_failed",
            clearinghouse_claim_id=result.clearinghouse_claim_id,
            clearinghouse_status=result.clearinghouse_status,
            raw_response=result.raw_response,
            submitted_at=datetime.now(timezone.utc),
        )

        if not result.success:
            raise ClaimSubmissionError(f"Rejected: {result.errors}")

        return claim_id
```

---

## 6. Clearinghouse Clients

### Stedi (Dev/Staging) — JSON API

```python
class StediClient:
    BASE_URL = "https://healthcare.us.stedi.com/2024-04-01/change/medicalnetwork"

    def submit_dental_claim(self, claim_input, idempotency_key: str):
        payload = _build_stedi_json_payload(claim_input)  # maps DentalClaimInput → Stedi JSON format
        resp = self._http.post(
            f"{self.BASE_URL}/dental/v1",
            json=payload,
            headers={"Idempotency-Key": idempotency_key},
        )
        # 200 = accepted, 400 = validation failure
        ...

    def poll_eras(self, since_iso: str) -> list[dict]:
        resp = self._http.get(f"{self.BASE_URL}/transactions",
                              params={"startDateTime": since_iso, "transactionType": "835"})
        return resp.json().get("transactions", [])

    def get_era(self, transaction_id: str) -> dict:
        resp = self._http.get(f"{self.BASE_URL}/transactions/{transaction_id}")
        return resp.json()
```

**Stedi JSON submission:** `usageIndicator: "T"` for test, `"P"` for production.

### DentalXChange (Production) — Raw X12

```python
class DentalXChangeClient:
    TOKEN_URL = "https://api.dentalxchange.com/oauth/token"
    BASE_URL = "https://api.dentalxchange.com/xconnect/v1"

    def submit_dental_claim(self, claim_input, idempotency_key: str):
        raw_x12 = build_837d(claim_input)
        token = self._get_token()  # OAuth2 client credentials, cache + refresh
        resp = self._http.post(
            f"{self.BASE_URL}/claims",
            content=raw_x12.encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "text/plain",
                "X-Idempotency-Key": idempotency_key,
            },
        )
        # DUPLICATE status = idempotent, treat as success with original claim ID
        ...
```

**ERA delivery from DentalXChange:** SFTP drop to S3 bucket you configure with them, or webhook. Use the S3 → SQS → ERA worker pattern.

---

## 7. ERA Processing (835)

### 835 Key Segments

```
BPR    — Payment amount, EFT/check info
TRN    — Trace number (check/EFT number)
DTM*405 — Payment date
N1*PR  — Payer name
N1*PE  — Payee (practice) NPI
CLP    — Claim payment (PCN, status, charged, paid, patient responsibility)
SVC    — Service line payment (CDT code, billed, paid)
CAS    — Claim adjustment (group code + CARC reason code + amount)
AMT    — Allowed amount
```

**CLP02 claim status codes:**
- `1` = Processed
- `2` = Reversed
- `19` = Denied
- `4` = Reversal

**CAS group codes:**
- `CO` = Contractual Obligation (provider write-off)
- `PR` = Patient Responsibility (patient owes)
- `OA` = Other Adjustment
- `PI` = Payer Initiated

**Key CARC codes:**
- `45` = Charge exceeds fee schedule (contractual adjustment)
- `1` = Deductible
- `2` = Coinsurance
- `3` = Co-payment
- `96` = Non-covered
- `97` = Bundled into another service
- `29` = Timely filing exceeded

### 835 Parser

```python
def parse_835(raw_x12: str) -> ERAPayment:
    """
    Fail hard on malformed input — never silently swallow parse errors.
    """
    segments = [s.strip() for s in raw_x12.split("~") if s.strip()]
    era = ERAPayment(...)
    current_claim = None
    current_service = None

    for seg in segments:
        parts = seg.split("*")
        tag = parts[0]

        if tag == "BPR":
            era.payment_amount = Decimal(parts[2])
        elif tag == "TRN":
            era.trace_number = parts[2]
        elif tag == "DTM" and parts[1] == "405":
            era.payment_date = parts[2]
        elif tag == "N1" and parts[1] == "PR":
            era.payer_name = parts[2]
        elif tag == "CLP":
            # flush previous claim
            current_claim = ClaimPayment(
                patient_control_number=parts[1],
                claim_status_code=parts[2],
                charged_amount=Decimal(parts[3]),
                paid_amount=Decimal(parts[4]),
                patient_responsibility=Decimal(parts[5]),
                ...
            )
            era.claim_payments.append(current_claim)
        elif tag == "SVC" and current_claim:
            # SVC01 = "AD:D0274" composite
            cdt_code = parts[1].split(":")[1] if ":" in parts[1] else parts[1]
            current_service = ServiceLinePayment(cdt_code=cdt_code, ...)
            current_claim.service_lines.append(current_service)
        elif tag == "CAS":
            # Up to 3 group/reason/amount triplets per CAS segment
            target = current_service or current_claim
            group = parts[1]
            i = 2
            while i + 1 < len(parts):
                target.adjustments.append(ServiceLineAdjustment(
                    group_code=group,
                    reason_code=parts[i],
                    amount=Decimal(parts[i+1]),
                ))
                i += 3

    return era
```

### ERA Processor (idempotent)

```python
class ERAProcessor:
    def process_era_file(self, s3_key: str, raw_x12: str) -> None:
        """Idempotent via s3_key. Crash-only — exception leaves ERA unprocessed for retry."""
        if self._db.era_files.exists(s3_key=s3_key):
            return  # already processed

        era_file_id = self._db.era_files.create(s3_key=s3_key, status="processing")
        era = parse_835(raw_x12)

        for claim_payment in era.claim_payments:
            claim = self._db.claims.find_by_pcn(claim_payment.patient_control_number)
            if not claim:
                # Flag for manual review — never silently skip
                self._db.unmatched_payments.create(era_file_id=era_file_id, ...)
                continue

            if claim_payment.is_denied:
                self._db.claims.update(claim.id, status="denied", denial_codes=[...])
                continue

            self._db.payments.create(
                claim_id=claim.id,
                payment_type="insurance_era",
                amount=claim_payment.paid_amount,
                ...
            )
            self._db.claims.update(claim.id, status="paid", insurance_paid=claim_payment.paid_amount)

        self._db.era_files.update(era_file_id, status="processed")
```

---

## 8. MassHealth (CKMA1) Requirements

1. **`claim_filing_code = "MA"`** in SBR segment — not `"CI"` (commercial)
2. **DentaQuest provider enrollment** — rendering provider must be enrolled in MassHealth. Store `providers.masshealth_provider_id`. Block claim generation if missing.
3. **Payer ID `CKMA1`** routes through clearinghouse like any other payer
4. **No secondary billing to MassHealth** — they are payer of last resort. Bill commercial first, then MassHealth with commercial EOB attached
5. ERA delivery: standard 835 via clearinghouse

Add `payer_type: Literal["commercial", "medicaid", "medicare"]` to `insurance_plans`. Builder auto-uses `"MA"` when `payer_type == "medicaid"`.

---

## 9. Claim Status Tracking

**Status lifecycle:**
1. Submission → `submitted`
2. 277CA webhook (seconds/minutes) → `acknowledged` or `clearinghouse_rejected`
3. After 7+ days, no ERA → poll 276/277 → `pending` or `paid`/`denied`
4. 835 ERA arrival → final: `paid`, `denied`, `partially_paid`

ERA is authoritative. 276/277 polling is for exceptions when ERA doesn't arrive.

**Stedi 276 check:**
```
POST https://healthcare.us.stedi.com/2024-04-01/change/medicalnetwork/claimstatus/v3
```
Wait ≥ 7 days post-submission before polling.

---

## 10. Common Clearinghouse Rejection Reasons

| Error | Root Cause | Prevention |
|-------|-----------|------------|
| Invalid NPI | Typo or inactive | Validate against NPPES API at provider creation |
| Missing/wrong taxonomy | Not on NPI registration | Match against NUCC taxonomy list |
| Invalid payer ID | Wrong clearinghouse routing ID | Seed payer table with verified IDs |
| Member ID mismatch | Insurance card error | Run eligibility check before claim |
| Duplicate claim | Same PCN submitted twice | Idempotency key + UNIQUE constraint on PCN per payer |
| Missing tooth number | Restorative/endo without tooth | Validator: CDT category → tooth required |
| Charges don't add up | Sum of SV3 fees ≠ CLM02 | Calculate total in builder, never trust UI input |
| Missing rendering provider | No Loop 2310B NM1*82 | Always include rendering provider |
| Wrong claim filing code | `CI` for Medicaid | Check `payer_type` and set accordingly |

---

## 11. Secondary Claims (Phase 1: Manual Review)

After primary ERA arrives:
1. ERA processor detects `patient_responsibility > 0` on claim with secondary insurance on file
2. Creates `secondary_claim_pending` task record with primary EOB data
3. Staff reviews and clicks "Submit Secondary" in UI
4. Secondary claim builder reads from `primary_era_data` stored on claim record

Secondary requires additional 837D data: second SBR loop (`S` = secondary), COB amounts in Loop 2320 (`AMT*D` = primary paid, `AMT*A8` = patient responsibility), primary payer info in Loop 2330A.

---

## 12. Database Schema

```sql
CREATE TABLE claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appointment_id UUID NOT NULL REFERENCES appointments(id),
    patient_id UUID NOT NULL REFERENCES patients(id),
    insurance_id UUID NOT NULL REFERENCES patient_insurance(id),
    idempotency_key VARCHAR(64) UNIQUE NOT NULL,
    submission_attempt INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
        -- draft | submitted | clearinghouse_rejected | acknowledged |
        -- pending | paid | partially_paid | denied | appealing
    patient_control_number VARCHAR(38) UNIQUE NOT NULL,
    payer_id VARCHAR(20) NOT NULL,
    payer_claim_id VARCHAR(50),
    clearinghouse_status VARCHAR(50),
    raw_submission TEXT,
    raw_response JSONB,
    submission_errors TEXT[],
    insurance_paid NUMERIC(10,2),
    patient_responsibility NUMERIC(10,2),
    denial_codes TEXT[],
    submitted_at TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE era_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    s3_key VARCHAR(500) UNIQUE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
        -- pending | processing | processed | failed
    payer_name VARCHAR(200),
    trace_number VARCHAR(50),
    payment_amount NUMERIC(10,2),
    payment_date DATE,
    raw_x12 TEXT,
    claim_count INTEGER,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE unmatched_era_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    era_file_id UUID NOT NULL REFERENCES era_files(id),
    patient_control_number VARCHAR(38),
    paid_amount NUMERIC(10,2),
    raw_clp TEXT,
    resolved BOOLEAN NOT NULL DEFAULT false,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_claims_appointment ON claims(appointment_id);
CREATE INDEX idx_claims_status ON claims(status);
CREATE INDEX idx_claims_pcn ON claims(patient_control_number);
CREATE INDEX idx_claims_payer_claim_id ON claims(payer_claim_id) WHERE payer_claim_id IS NOT NULL;
```

---

## 13. Module 7 File Layout

```
api/
  services/
    claims/
      x12_builder.py             # X12Builder, Segment
      dental_claim_builder.py    # DentalClaimInput, build_837d()
      claim_validator.py         # validate_claim() → ValidationResult
      claims_service.py          # ClaimsService (orchestration)
      idempotency.py             # generate_claim_idempotency_key()
    clearinghouse/
      base.py                    # ClearinghouseClient Protocol
      stedi_client.py            # StediClient (JSON API)
      dentalxchange_client.py    # DentalXChangeClient (raw X12)
    era/
      era_parser.py              # parse_835() → ERAPayment
      era_processor.py           # ERAProcessor.process_era_file()
      carc_codes.py              # CARC/RARC constants
  workers/
    era_worker.py                # SQS consumer → ERAProcessor
    claim_status_worker.py       # Periodic 276/277 polling
  routers/
    claims.py                    # POST /api/v1/claims, GET /api/v1/claims/{id}
```
