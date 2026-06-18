# Module 7a — Claims Submission (837D) Design

**Date:** 2026-06-18
**Status:** Approved — ready for implementation plan
**Depends on:** Module 3.5 (appointment procedures). Module 6 (co-pay) optional — the
837D sends *charges*, not the patient-responsibility breakdown.
**Source research:** `research/15_module7_claims_submission.md` (covers all of Module 7;
this spec narrows it to the **claims-submission half** and reconciles it with the codebase).

## 1. Scope

Module 7 from the long-term plan is two halves: **(7a) build + submit an 837D dental
claim** and **(7b) ingest an 835 ERA and auto-post the payment**. This spec is **7a only**.
7b gets its own spec + plan immediately after.

**In scope (7a):**
- Standard commercial **primary** claim, **one claim = one appointment's procedures**,
  billed to the patient's primary `patient_insurance`.
- A `ClearinghouseClient` ABC with a single **Stedi** adapter using Stedi's **Dental
  Claims (837D) JSON** endpoint (Stedi translates JSON → X12 837D and forwards to the payer).
- `DentalClaimInput` domain model, claim builder, pre-submission validator, deterministic
  idempotency key, a **synchronous** submit endpoint, `claims` table, and a thin claim
  panel + claims worklist UI.

**Out of scope — deferred (see §10):** async submit worker; DentalXChange production
raw-X12 client + `X12Builder`; 277CA webhook and 276/277 status-polling worker;
MassHealth/Medicaid; secondary/COB claims; multiple rendering providers per appointment;
a queryable per-service-line table; claim attachments (275).

## 2. Key decisions (and where they diverge from the research doc)

1. **Stedi JSON endpoint, no raw X12 in 7a.** Stedi's Dental Claims (837D) JSON endpoint
   accepts a structured JSON claim and generates the X12 itself; its response synchronously
   includes a **277CA** acknowledgment indicating whether the claim passed Stedi's claim
   edits. We therefore build `DentalClaimInput` → **Stedi JSON** and do **not** build raw
   X12. The research doc's `X12Builder`/`build_837d()` is only needed for DentalXChange
   (deferred). The doc was internally inconsistent (it both built X12 and submitted JSON);
   this spec resolves that in favor of JSON.
   - Refs: Stedi *Dental Claims (837D) JSON* and *Submit dental claims* docs.
2. **Synchronous submit, async deferred.** The endpoint builds + validates + persists +
   calls Stedi inline and returns the result. No SQS/worker — mirrors the eligibility
   *sync slice*, which deferred its async batch to Staging Checkpoint 5. The builder /
   validator / client / persistence are identical if we later lift the call into a worker.
3. **Minimal status lifecycle.** 7a writes only statuses provable from the synchronous
   call: `draft → submitted` (277CA accepted) / `clearinghouse_rejected` (277CA edit
   failure) / `submission_failed` (transport/5xx). The **full** enum is defined in the
   column so 7b and the polling worker never migrate; they own `acknowledged / pending /
   paid / partially_paid / denied / appealing`.
4. **Money is integer cents.** `total_charge_cents` is an integer (the locked-in Phase 3
   convention); the research doc's `NUMERIC(10,2)` is rejected. Cents → dollar strings
   (`28500 → "285.00"`) happen only at the Stedi-payload edge.
5. **Deterministic idempotency key.** `sha256("claim:{appointment_id}:{patient_id}:{insurance_id}:v{attempt}")`.
   Same inputs → same key (network-retry safe). `attempt` increments **only** for an
   intentional resubmission after denial, **never** for a network retry. Enforced by a
   `UNIQUE` constraint, plus a `UNIQUE (patient_control_number, payer_id)` duplicate guard.
6. **One rendering provider per claim.** Sourced from `appointment.provider_id → provider.npi`
   (per the documented NPI convention: hygienists carry the supervising dentist's NPI).
   Multiple providers per appointment is deferred.

## 3. Architecture & module layout

Mirrors the established eligibility/copay pattern (provider ABC + Stedi adapter + parser;
feature-gated, practice-scoped, audited router; pure service orchestration).

```
app/services/claims/
  base.py        # ClearinghouseClient (ABC), DentalClaimInput, ClaimLine, ClaimResult,
                 # ClaimSubmissionError(retryable=…, rejected=…)
  stedi.py       # StediClaimsClient(ClearinghouseClient): DentalClaimInput → Stedi JSON,
                 # POST, parse 277CA accept/reject from the response
  builder.py     # build_claim_input(appointment, procedures, patient, insurance,
                 #   insurance_plan, practice, provider) → DentalClaimInput
  validator.py   # validate_claim(DentalClaimInput) → ValidationResult(valid, errors, warnings)
  idempotency.py # generate_claim_idempotency_key(appointment_id, patient_id, insurance_id, attempt)
  service.py     # submit_claim_for_appointment(...) — orchestration (mirrors copay/service.py)
app/routers/claims.py
app/models/claim.py
alembic/versions/00XX_claims.py
scripts/stedi_claim_smoke.py            # manual sandbox smoke (not in CI)
```

`ClearinghouseClient` is an ABC exactly like `EligibilityProvider`. `StediClaimsClient` is
the only adapter in 7a. `ClaimSubmissionError` carries `retryable` (transport/5xx/timeout →
status `submission_failed`) vs `rejected` (277CA edit failure → `clearinghouse_rejected`,
errors stored), mirroring `EligibilityProviderError`.

## 4. Data model

One new table, `claims`. (`era_files` / `unmatched_era_payments` belong to 7b.)

```sql
CREATE TABLE claims (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    practice_id              UUID NOT NULL,                       -- practice scoping
    appointment_id           UUID NOT NULL REFERENCES appointments(id),
    patient_id               UUID NOT NULL REFERENCES patients(id),
    insurance_id             UUID NOT NULL REFERENCES patient_insurance(id),  -- primary
    provider_id              UUID NOT NULL REFERENCES providers(id),          -- rendering
    idempotency_key          VARCHAR(64) NOT NULL,
    submission_attempt       INTEGER NOT NULL DEFAULT 1,
    patient_control_number   VARCHAR(38) NOT NULL,                -- CLM01; 7b ERA matches on this
    payer_id                 VARCHAR(20) NOT NULL,
    status                   VARCHAR(32) NOT NULL DEFAULT 'draft',
        -- 7a writes: draft | submitted | clearinghouse_rejected | submission_failed
        -- reserved for 7b/worker: acknowledged | pending | paid | partially_paid | denied | appealing
    total_charge_cents       INTEGER NOT NULL,                    -- Σ service-line fee_cents (computed in builder)
    clearinghouse_claim_id   VARCHAR(64),                         -- Stedi's id from the response
    clearinghouse_status     VARCHAR(50),
    submission_errors        TEXT[],                              -- 277CA edit failures / validation errors
    raw_submission           JSONB,                               -- Stedi JSON request we sent
    raw_response             JSONB,                               -- Stedi JSON response incl. 277CA
    submitted_at             TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (idempotency_key),
    UNIQUE (patient_control_number, payer_id)
);
CREATE INDEX idx_claims_appointment ON claims(appointment_id);
CREATE INDEX idx_claims_status      ON claims(status);
CREATE INDEX idx_claims_pcn         ON claims(patient_control_number);
```

Model follows the codebase conventions (`PHIMixin`/`TimestampMixin` as appropriate;
`practice_id` on the row like every other table).

**Service lines:** not a separate table in 7a. Lines are derived from
`appointment_procedures` at build time and stored inside `raw_submission`. Each line sets
`lineItemControlNumber = appointment_procedure.id` so 7b's ERA can correlate paid lines
back without a join table. If 7b needs queryable line-level payments it adds
`claim_service_lines` then — not now.

**Patient Control Number (PCN):** deterministic, ≤ 38 chars, unique per payer, stored (not
recomputed). Scheme: Crockford base32 of the claim `id` (no delimiter chars `~ * : ^`,
which Stedi reserves), truncated to ≤ 38. Generated once at `draft` insert.

**Provider config sourced (no new columns — already on `practices`):** `billing_npi`,
`billing_tax_id_encrypted` (decrypt at build), `billing_taxonomy_code`,
`clearinghouse_submitter_id`, `clearinghouse_provider`, `clearinghouse_api_key_ssm_path`.

## 5. Claim build — data sources

| 837D element | Source |
|---|---|
| Billing provider NPI / tax id / taxonomy | `practices.billing_npi` / `billing_tax_id_encrypted` (decrypt) / `billing_taxonomy_code` |
| Submitter id | `practices.clearinghouse_submitter_id` |
| Rendering provider NPI | `appointment.provider_id → providers.npi` |
| Payer id | primary `patient_insurance.insurance_plan_id → insurance_plans.payer_id` |
| Subscriber / insured | `patient_insurance.relationship_to_insured`: `self` → patient demographics; otherwise `insured_first_name/last_name/date_of_birth` |
| Member id / group | `patient_insurance.member_id` / `group_number` |
| Service lines | the appointment's `appointment_procedures`: `procedure_code` (CDT), `fee_cents`, `tooth_number`, `surface`, `procedure_name` |
| Total charge | Σ `appointment_procedures.fee_cents` (computed; never trust UI) |
| Date of service | `appointment.start_time` (date) |
| usageIndicator | `"T"` in dev/staging, `"P"` in production (env/practice-driven) |

Tooth area mapping for the per-line tooth data (JP/JQ/JR/JS) is derived from tooth number,
per research §1.

## 6. Submission flow

`submit_claim_for_appointment(session, practice_id, appointment_id, idempotency_key, attempt=1)`:

1. **Feature gate** `claims_submission` (router, via `require_feature`).
2. **Idempotency check** — existing claim for this key → return it unchanged (no 2nd Stedi call).
3. **Build** `DentalClaimInput` (sources in §5).
4. **Validate** (`validate_claim`) — see §7. Hard errors → `422` before any network call;
   nothing persisted.
5. **Persist `draft`** — PCN generated, `total_charge_cents` set, `raw_submission` = Stedi
   JSON — **before** the network call, so a crash leaves a retryable record.
6. **Call Stedi**, inspect the 277CA in the response:
   - accepted → `submitted` (+ `clearinghouse_claim_id`, `submitted_at`, `raw_response`)
   - 277CA edit rejection → `clearinghouse_rejected` (+ `submission_errors`)
   - `ClaimSubmissionError(retryable=True)` (transport/5xx/timeout) → `submission_failed`;
     safe to retry with the **same** idempotency key
7. Return the claim row.

`attempt` increments only for an intentional resubmission after denial (new key); never
for a network retry.

## 7. Validation (`validate_claim` → ValidationResult)

**Hard errors (block submission, return 422):**
- Billing NPI / rendering NPI not 10 digits.
- Tax id not 9 digits (after stripping `-`).
- Billing taxonomy code missing.
- No procedures on the claim.
- Any line CDT code not `^D\d{4}$`.
- Any line fee ≤ 0.
- PCN > 38 chars.
- `appointment.provider_id` missing, or practice clearinghouse creds
  (`clearinghouse_submitter_id` / `clearinghouse_api_key_ssm_path`) missing.

**Warnings (allowed, surfaced in UI):**
- Line fee > $5000 ("verify").
- D2/D3/D4 line without a tooth number ("typically requires a tooth number").

## 8. API

Practice-scoped, write-role, audit-logged, `Idempotency-Key` header — identical
conventions to the copay/eligibility routers. Schemas added to the **Zod source** and
regenerated via `pnpm generate` (never hand-edit `generated.py`).

- `POST /api/v1/appointments/{appointment_id}/claim` — submit; `201` with the claim.
  `422` with the error list on validation failure. `403` if the feature is disabled.
- `GET  /api/v1/appointments/{appointment_id}/claim` — the appointment's claim(s).
- `GET  /api/v1/claims/{id}` — detail (status, errors, raw response for debugging).
- `GET  /api/v1/claims?status=&patient_id=` — list for the worklist view.

## 9. Frontend

Thin, matching the eligibility/copay cards:
- A **Claim** panel on the appointment: status badge + "Submit Claim" button. The button is
  disabled with an explanatory tooltip when preflight data is missing (no NPI / taxonomy /
  clearinghouse creds / no procedures). On submit, show `submitted` / `clearinghouse_rejected`
  with any `submission_errors`, plus validator warnings.
- A minimal **Claims** worklist page with a status filter. No deep claim-editing UI in 7a.

## 10. Testing

TDD; new exported functions/endpoints ship with tests (happy path + one failure).

- **Unit:** `validator` (each error/warning branch); `idempotency` (determinism + attempt
  bump); `builder` (self vs. non-self subscriber, charge summing, tooth/area mapping);
  Stedi payload mapper (cents→dollar strings, `usageIndicator`); 277CA response parsing
  (accept vs edit-reject) against **recorded fixtures** — as in `test_stedi_provider.py` /
  `test_eligibility_parser.py`.
- **Integration:** `service` idempotency (second call returns same row, no 2nd network
  call); persist-before-network ordering; status transitions. **Router** happy path + a
  validation-failure (422) case.
- **Smoke (not in CI):** `scripts/stedi_claim_smoke.py` — one live sandbox test claim
  (`usageIndicator: "T"`), run manually at **Staging Checkpoint 5**.

## 11. Deferred (roll into `longterm_build_plan.md` §Deferred)

| Item | When |
|---|---|
| **7b — 835 ERA ingest + auto-post** | Immediate next spec/plan after 7a |
| Async submit worker (SQS/ECS) | If submission volume demands it; provable only on AWS (bundle near Staging Checkpoint 5) |
| DentalXChange production client + `X12Builder` (raw X12) | When a prod practice needs a non-Stedi route |
| 277CA webhook + 276/277 status-polling worker | With the async worker; ERA (7b) is the authoritative paid/denied source |
| MassHealth/Medicaid (`payer_type`, `claim_filing_code="MA"`, DentaQuest enrollment) | When a MassHealth practice onboards |
| Secondary / COB claims | After 7b (needs primary EOB data from an ERA) |
| Multiple rendering providers per appointment | Demand-driven |
| Queryable `claim_service_lines` table | If 7b needs line-level payment queries |
| Claim attachments (275) | Demand-driven (some dental payers require them) |

## 12. Cross-references

- Pattern source: `app/services/eligibility/{base,stedi,parser}.py`, `app/services/copay/service.py`,
  `app/routers/{eligibility,copay}.py`.
- Provider config already on `practices` (clearinghouse_* + billing_*); `providers.npi`
  NOT NULL; `appointment_procedures` carries CDT/fee/tooth/surface.
- Clearinghouse usage tracking (250-call allowance) and overage policy — see
  `longterm_build_plan.md` Phase 3 note and `research/16_cost_and_scaling_model.md`.
  Claim submissions count toward the same monthly allowance as eligibility checks; usage
  tracking is a Phase-3-wide concern, not built in 7a.
