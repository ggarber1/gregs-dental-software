# Module 6 — Co-pay / Patient-Responsibility Calculation Engine: Design

**Status:** designed (brainstorm complete) · **Date:** 2026-06-16
**Research source of truth:** `research/14_module6_copay_calculation.md`
**Prerequisites (all merged to `main`):** 3.5 per-appointment procedures (#50), 3.6
practice fee schedule (#51), 5.2–5.4 eligibility verification sync slice (#52).

Module 6 turns captured procedures + eligibility data into an estimate of what the
patient owes vs. what insurance pays. It is the calculation layer that Module 3.5
deliberately deferred ("3.5 captures data; it does not calculate"). It is a
per-practice opt-in module and requires Module 5 eligibility to be active.

---

## 1. Scope

### In this spec (v1)
- A **pure calculation engine** (no I/O) for three plan worlds:
  - **PPO / Premier** — full pipeline: allowed-amount/write-off → gatekeeping
    (not-covered / waiting period / frequency / annual-max) → deductible →
    coinsurance → annual-max cap.
  - **MassHealth / Medicaid** — patient owes $0 on covered procedures; insurance
    pays the allowed amount; some codes not covered; PA flag surfaced.
  - **Out-of-network (OON) balance billing** — a branch inside the standard
    pipeline keyed on `network_status` (write-off $0; patient pays coinsurance on
    the allowed/UCR amount **plus** the fee−allowed gap as balance bill).
- **Coinsurance** sourced as a **per-CDT-code map parsed from the 271**, with a
  per-category fallback and a "needs manual entry" flag when neither is known.
- **Contracted-fee table** as the authoritative source of allowed amounts, with a
  billed-fee fallback (write-off $0) for codes not yet entered.
- **Frequency** and **waiting-period** gatekeeping built into the engine.
- Results persisted **both** onto `appointment_procedures` rows and into a
  `copay_calculations` snapshot (with manual-override support).
- Full **CDT catalog seed** (code + description + category).
- API endpoints, the two frontend surfaces, and a **calculation-algorithm
  reference doc**.

### Deferred (documented follow-ups — do NOT build here)
- **DHMO (capitation) plans.** Need a per-plan fixed-copay schedule (a new data
  source the 271 does not provide). `plan_type='dhmo'` is accepted by the schema
  but every line is flagged "not calculable, enter manually" until built.
- **Alternate-benefit / downgrade** (e.g. posterior composite → amalgam rate).
  Needs per-carrier downgrade mappings (code → downgraded code + allowed). The
  research calls this "the most commonly misimplemented" calculation; build it as
  its own slice with dedicated tests.
- **Secondary-insurance COB auto-calculation.** v1 flags a secondary plan and
  notes "submit manually after primary EOB"; it does not coordinate benefits.
- **MassHealth frequency reference data (101 CMR 314).** v1 uses 271/​procedure
  history; the hardcoded Medicaid frequency tables are a later add (shared with
  the Module 5 MassHealth follow-up).
- **Plan-level (vs. payer-level) contracted-fee granularity** — see §4.3.

### Decisions locked during brainstorming
1. **Plan-type scope:** PPO/Premier + MassHealth + OON. DHMO + downgrade deferred.
2. **Persistence:** estimates written onto `appointment_procedures` rows **and** a
   `copay_calculations` snapshot per run. On-demand trigger; recompute on change.
3. **Coinsurance source:** per-CDT-code map from the 271 → category fallback →
   `needs_manual_entry`. Requires extending the Module 5 parser.
4. **Frequency:** engine supports it; the service computes `used_count` from
   completed `appointment_procedures` history (claims history does not exist until
   Module 7/8 — documented limitation, surfaced in the UI as an estimate).
   Waiting-period checking is included (self-contained from existing fields).
5. **CDT catalog:** Module 6 owns seeding the full D-code list with categories.
6. **Allowed amount:** a contracted-fee table is the source of truth (option B),
   with a billed-fee fallback for codes not yet entered.
7. **Money:** integer cents at every input/output boundary (project convention).
   `Decimal` is used **only** internally for the percentage math, rounding to whole
   cents exactly once per line item.

---

## 2. Architecture

A **pure calculation function** with zero I/O is the heart. A thin service layer
does all the DB work around it. This mirrors how Module 5 separated its pure 271
parser from its router, and isolates the subtle math for exhaustive unit testing.

```
Router:  POST/GET/PATCH /api/v1/appointments/{id}/copay-estimate
         (feature-gated: copay_estimation AND eligibility_verification)
   │
   ▼
CopayService  (the only layer that does I/O)
   • loads the appointment's procedures (3.5)
   • loads the latest verified eligibility_check (5)
   • resolves contracted allowed amounts (new table) + billed-fee fallback
   • resolves coinsurance: per-code map → category fallback → manual flag
   • counts frequency usage from completed appointment_procedures history
   • builds EligibilitySnapshot + [ProcedureInput]
   • calls the pure engine
   • writes results → appointment_procedures rows + copay_calculations snapshot
   │  pure data in / pure data out
   ▼
copay engine  (apps/api/app/services/copay/, NO I/O)
   calculate_patient_responsibility(snapshot, procedures)
       → PatientResponsibilityBreakdown
   dispatches by plan_type; OON is a branch on network_status
   asserts  fee == write_off + patient_owes + insurance_owes  on every line
```

**Money handling:** inputs and outputs are integer cents. The engine uses `Decimal`
only for coinsurance-fraction math and rounds to whole cents once, at final per-line
assignment — never at intermediate steps, so the accounting identity holds exactly.

---

## 3. The calculation engine

Location: `apps/api/app/services/copay/` (pure, no I/O).

### 3.1 Dispatch

```
calculate_patient_responsibility(snapshot, procedures) -> PatientResponsibilityBreakdown
  ├─ medicaid               → _calculate_medicaid(...)
  ├─ ppo / premier / indem  → _calculate_standard(...)   # OON branch inside, on network_status
  └─ dhmo / unknown         → every line flagged "not calculable, enter manually"
```

### 3.2 Inputs (all money integer cents)

`ProcedureInput` (built by the service): `procedure_id`, `cdt_code`, `category`,
`provider_fee_cents`, `allowed_amount_cents` (contracted row, else `None` → fall
back to fee), `coinsurance_patient_share` (per-code → category → `None`),
`not_covered`, `requires_prior_auth`, `frequency_limit_count`,
`frequency_limit_period`, `frequency_used_count`.

`EligibilitySnapshot` (built by the service): `plan_type`, `network_status`,
`coverage_start_date`, `deductible_remaining`, `deductible_waived_categories`,
`annual_max_remaining`, `ortho_lifetime_max_remaining`,
`waiting_period_months_by_category`, `has_secondary_insurance`.

### 3.3 Standard pipeline (per procedure, after sorting)

1. **Allowed + write-off.** In-network: `allowed = min(fee, allowed_amount or fee)`,
   `write_off = max(0, fee − allowed)`. OON: `write_off = 0`; insurance computes on
   the UCR/allowed, and the `fee − allowed` gap is patient **balance-bill** (not
   write-off).
2. **Short-circuit gates** (before any coinsurance — insurance pays $0, patient owes
   the allowed amount, line flagged):
   - `not_covered`; **waiting period** active
     (`coverage_start_date + months > service_date`); **frequency exceeded**
     (`used_count ≥ limit_count`). A waiting period of `0`/null months means no
     wait — this is also how "waived for prior continuous coverage" is represented
     (the parser sets the category's months to `0` when the 271 indicates a
     waiver), so the engine needs no separate `waived` flag.
   - **Coinsurance unknown** (no per-code, no category) → flag `needs_manual_entry`;
     do **not** guess.
3. **Deductible.** If `category` not in the waived set:
   `applied = min(deductible_remaining, amount)`; decrement running
   `deductible_remaining`.
4. **Coinsurance split.** `insurance = after_deductible × (1 − patient_share)`,
   `patient_coins = after_deductible × patient_share` (`Decimal` math).
5. **Annual-max cap.** `capped = min(gross_insurance, annual_max_remaining)`;
   overflow → patient; decrement running `annual_max_remaining`. Ortho draws the
   separate `ortho_lifetime_max` bucket, not the annual max.
6. **Total.** `patient_owes = deductible_applied + patient_coins +
   annual_max_overflow + oon_balance_bill`. Round to cents **here only**.

### 3.4 Medicaid pipeline

`patient_owes = 0`, `insurance = allowed`, `write_off = fee − allowed`. `not_covered`
codes (e.g. adult implants) → patient owes allowed, line flagged. `requires_prior_auth`
surfaces a flag for Module 7 to gate claim generation on later.

### 3.5 Ordering & running state (explicit correctness rules)

- **Procedure ordering:** sort `preventive → diagnostic → basic → major → ortho`
  before running so the deductible lands on the lowest-coinsurance procedures first
  (best for the patient). Documented in the engine.
- **Running state:** `deductible_remaining` and `annual_max_remaining` are threaded
  across the sorted line items, so multi-procedure visits split the deductible and
  exhaust the annual max correctly mid-visit.

### 3.6 Secondary insurance

Detected → `has_secondary_insurance=True` + a note ("submit manually after primary
EOB"). Not auto-coordinated (deferred).

### 3.7 The invariant

Every line asserts `provider_fee == write_off + patient_owes + insurance_owes`, and
the totals re-assert it. Because rounding happens exactly once per line, any
violation is a real bug, not rounding drift.

---

## 4. Data model

All money is integer cents.

### 4.1 Extend `eligibility_checks` (migration)

Add the fields Module 6 needs that do not exist yet:
- `plan_type` — `CHECK IN ('ppo','premier','medicaid','indemnity','dhmo')`, default
  `'ppo'`. The v1 engine handles all but `dhmo`.
- `network_status` — `'in_network' | 'out_of_network'`, default `'in_network'`.
- `coinsurance_by_code` **JSONB** — per-CDT-code patient-share map
  (`{"D2740": 0.50, ...}`).
- `deductible_waived_diagnostic` / `_preventive` / `_orthodontic` booleans
  (preventive default `true`).
- `ortho_lifetime_max` / `ortho_lifetime_max_used` (cents, nullable).

Reuse what already exists: `coverage_start_date`, `waiting_period_*_months`,
`frequency_limits` (JSONB), and the per-category `coinsurance_*` fields (now actually
populated, as the category fallback).

### 4.2 Extend the Module 5 parser

`apps/api/app/services/eligibility/parser.py` + the `EligibilityResult` dataclass +
the router's `_apply_result`: build `coinsurance_by_code` from the per-code 271
segments, derive the per-category fallback rates from that same data, and detect
`plan_type` / `network_status` where the 271 exposes them. Tested against recorded
271 fixtures (extending Module 5's fixture suite, including the Cigna sandbox
response that drove the per-code finding).

### 4.3 New table `contracted_fee_schedule`

The authoritative source of allowed amounts.
- Columns: `id`, `practice_id`, `payer_id` (the same payer identity eligibility
  uses), `cdt_code_id` FK, `allowed_amount_cents`, `not_covered` bool,
  `requires_prior_auth` bool, timestamps, soft delete.
- Unique `(practice_id, payer_id, cdt_code_id)` where `deleted_at IS NULL`.
- Resolution at calc time: contracted row → else **billed fee** (write-off $0).
- **Open detail / future refinement:** keyed on `payer_id` because contracts are
  practice↔carrier. Plan-level granularity (different rates per plan under one
  payer) is a deferred refinement.

### 4.4 New table `copay_calculations`

The audit snapshot.
- `id`, `practice_id`, `patient_id`, `appointment_id`, `eligibility_check_id`,
  `calculated_at`, `plan_type`.
- Totals (cents): `total_provider_fee_cents`, `total_write_off_cents`,
  `total_insurance_owes_cents`, `total_patient_owes_cents`,
  `deductible_remaining_after_cents`, `annual_max_remaining_after_cents`.
- Manual override: `override_patient_cents` (nullable), `override_note`,
  `overridden_by`.
- `line_items` **JSONB** (per-procedure breakdown), `idempotency_key` (unique),
  `has_secondary_insurance`, soft delete, PHI audit columns (`last_accessed_by/at`).

### 4.5 Full CDT catalog seed (migration)

Expand the 20-code seed to the full D-code list, each with `code`, `description`, and
`category`, from a redistributable (Open Dental GPL) source. `default_fee_cents` stays
null (practices set fees via Module 3.6).

### 4.6 `appointment_procedures` — no schema change

The service writes results into the existing `insurance_est_cents` /
`patient_est_cents` with `estimate_source='eligibility'`.

**Net:** 3 migrations (eligibility ALTER + CDT seed expansion;
`contracted_fee_schedule`; `copay_calculations`) plus the parser extension.

---

## 5. API, feature flags & frontend

### 5.1 Feature flag

`copay_estimation`, enforced via the existing `require_feature` dependency. It **also
requires `eligibility_verification`**; the router checks both and 403s if either is
off.

### 5.2 Endpoints (practice-scoped, audited, idempotency-key per middleware)

- `POST /api/v1/appointments/{id}/copay-estimate` — runs the engine (loads
  procedures + latest verified eligibility check, resolves contracted allowed
  amounts + frequency counts, calculates), writes estimates onto the procedure rows,
  persists a `copay_calculations` snapshot, returns the breakdown. Recompute
  overwrites the procedure estimates and writes a fresh snapshot.
- `GET /api/v1/appointments/{id}/copay-estimate` — returns the latest snapshot with
  line items.
- `PATCH /api/v1/appointments/{id}/copay-estimate` — sets the manual override
  (`override_patient_cents` + `override_note` + `overridden_by`).
- `GET /api/v1/contracted-fees?payerId=…` — the carrier's contracted rates joined
  against the CDT catalog.
- `PUT /api/v1/contracted-fees/{cdtCodeId}` and `DELETE …` — set/clear a contracted
  allowed amount, `not_covered`, `requires_prior_auth`. Practice-scoped + write-role
  + audit.

### 5.3 Schemas / types

Pydantic request/response in the generated pipeline; matching Zod types in
`packages/shared-types` (manually authored, per repo convention). Money is integer
cents across the wire; the frontend converts cents↔dollars at the edges.

### 5.4 Frontend

- **Estimate card on the appointment view** — per-procedure breakdown
  (fee / write-off / insurance / patient), the visit total, deductible & annual-max
  remaining-after, a "Calculate estimate" / "Recalculate" action, the manual-override
  editor, and clear flags for `needs_manual_entry`, frequency-exceeded,
  waiting-period, and not-covered, plus the **"estimate, not a guarantee of payment"**
  caveat (reinforced by the frequency-from-procedures limitation).
- **Settings → Contracted Fees** — a searchable CDT table (reusing the Module 3.6
  fee-schedule UI pattern) with editable allowed-amount, not-covered, and prior-auth
  fields per carrier.

---

## 6. Calculation-algorithm reference doc

Deliverable: `docs/billing/copay-calculation-algorithm.md`. A canonical written
explanation of the math, independent of the code:
- the full pipeline and the plan-type variations (PPO/Premier, MassHealth, OON);
- the procedure-ordering rule and why it favors the patient;
- the deductible / annual-max running-state threading;
- the OON balance-bill case and the deferred alternate-benefit case;
- the accounting identity;
- the worked numeric examples from `research/14`.

The engine module's docstring links to this doc.

---

## 7. Testing

Testing concentrates on the **pure engine**, which is isolated precisely so it can be
tested exhaustively without a database.

- **Core suite — the 14 scenarios from `research/14`:** preventive-only ($0), fresh
  vs. met deductible, annual-max exhausted mid-visit (overflow to patient), frequency
  exceeded, waiting period (active + waived), deductible split across two procedures,
  MassHealth ($0 + not-covered implant), OON balance billing, secondary-insurance
  flagged, and the multi-procedure ordering case.
- **The accounting identity** (`fee == write_off + patient_owes + insurance_owes`) is
  asserted on every line item in every test — the primary correctness backstop.
- **Edge cases:** negative write-off clamp, annual-max exactly zero, calendar-year
  boundary, denied-claim exclusion from frequency counts.
- **Service layer:** contracted-fee → billed-fee fallback; coinsurance per-code →
  category → `needs_manual_entry`; frequency `used_count` from completed
  `appointment_procedures` (current-visit excluded); write-back onto procedure rows
  with `estimate_source='eligibility'`; snapshot idempotency; recompute overwrite.
- **Parser extension:** `coinsurance_by_code` extraction against recorded 271
  fixtures.
- **Router** (per repo rule — new endpoint → happy + failure test): feature-gate
  403s (both flags), idempotency replay, the override `PATCH`, contracted-fees CRUD.
- **Frontend:** estimate-card state rendering (flag states + caveat) and the Settings
  contracted-fees table.

---

## 8. Deliverables summary

- 3 migrations (`eligibility_checks` ALTER + full CDT seed; `contracted_fee_schedule`;
  `copay_calculations`) + the Module 5 parser extension.
- The pure engine (`apps/api/app/services/copay/`).
- `CopayService` (the I/O layer).
- 4 endpoint groups: copay-estimate POST/GET/PATCH + contracted-fees CRUD.
- Two frontend surfaces: the appointment estimate card + Settings contracted-fees.
- The calculation-algorithm reference doc (`docs/billing/copay-calculation-algorithm.md`).
- The test suites above.
