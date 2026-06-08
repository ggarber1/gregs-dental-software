# Phase 3 — Billing & Insurance Depth: Build Order

Close the revenue cycle loop so the practice doesn't need a separate billing tool.
Phase 3 is decomposed into five sub-projects. Each gets its own design spec and
implementation plan; this document fixes the order and the dependencies between them.

The detailed research/implementation guides already exist:
- `research/13_module5_insurance_verification.md`
- `research/14_module6_copay_calculation.md`
- `research/15_module7_claims_submission.md`

Those are the source of truth for the deep design of Modules 5–7. Each module's
spec in `docs/superpowers/specs/` narrows that research into a buildable plan and
reconciles it with what already exists in the codebase.

## Dependency graph

```
Module 3.5 — Per-Appointment Procedures   ← prerequisite for 6 + 7
Module 3.6 — Practice Fee Schedule         ← enhances 3.5 (fee auto-fill); feeds 6
Module 5.2–5.4 — Eligibility Verification  ← 5.1 (plan/patient_insurance CRUD) already done
        │
        ├──────────────┐
        ▼              ▼
Module 6 — Co-pay Calculation  (requires 3.5 procedures + 3.6 fees + 5 eligibility data)
        │
        ▼ (soft — 7 can ship before 6 using manually-entered co-pays)
Module 7 — Claims Submission (837D) + ERA Processing (835)  (requires 3.5)
        │
        ▼
Module 8 — Billing & Payments (ledger, statements, aging, QuickBooks export)  (requires 7)
```

## Build order

| # | Module | Depends on | Can parallelize with | Spec |
|---|--------|-----------|----------------------|------|
| 1 | **3.5 — Per-Appointment Procedures** | nothing new | 5.2–5.4 | `2026-06-04-module-3.5-appointment-procedures-design.md` (✅ done) |
| 2 | **3.6 — Practice Fee Schedule** | 3.5 (cdt_codes) | 5.2–5.4 | _separate PR — see below_ |
| 3 | **5.2–5.4 — Eligibility Verification** | 5.1 (done) | 3.5 / 3.6 | _tbd_ |
| 4 | **6 — Co-pay Calculation** | 3.5, 3.6, 5 | — | _tbd_ |
| 5 | **7 — Claims Submission + ERA** | 3.5 (6 optional) | — | _tbd_ |
| 6 | **8 — Billing & Payments** | 7 | — | _tbd_ |

3.5, 3.6, and eligibility are independent and may be built in any order or
concurrently. Everything from Module 6 on depends on 3.5 being in place.

## Module 3.6 — Practice Fee Schedule (planned, separate PR)

**Goal:** let each practice set its own fee per CDT code in Settings, instead of
typing the fee on every procedure. This is the "Practice Fee Schedule" item from the
longterm plan (Phase 2) and the per-practice override hinted at by
`cdt_codes.default_fee_cents` (currently global/null).

**Why it matters:**
- **3.5 today** makes staff type the fee on every procedure row. With a fee schedule,
  selecting a CDT code auto-fills the practice's fee (the `ProceduresSection` already
  prefills from a code's default fee when the field is blank — this just gives those
  defaults real per-practice values). Same hook would prefill treatment-plan items.
- **Module 6 (co-pay) needs it.** The calculation is `(fee − write-off) × coinsurance …`;
  the provider fee is the starting number. Per-practice fees are a prerequisite for
  accurate estimates, not a nicety.

**Data model (sketch — finalize during its own brainstorm):**
- New table `practice_fee_schedule`: `practice_id` FK, `cdt_code_id` FK (or `code`),
  `fee_cents` (integer cents, per the money convention), timestamps, soft delete.
  Unique on `(practice_id, cdt_code_id)`.
- Keep `cdt_codes.default_fee_cents` as the platform-wide fallback; the practice row
  overrides it. Resolution order at fee lookup: practice fee → cdt default → blank
  (staff types it).

**API (sketch):**
- `GET /api/v1/fee-schedule` — practice's fees (joined with the CDT catalog so the UI
  can show every code with its current/blank fee).
- `PUT /api/v1/fee-schedule/{cdtCodeId}` — set/replace a fee (idempotency-key required).
- `DELETE /api/v1/fee-schedule/{cdtCodeId}` — revert to the default.
- Practice-scoped + write-role + audit, same as every other mutating endpoint.

**Frontend (sketch):**
- A "Fee Schedule" section in Settings: searchable table of CDT codes (reuse the
  `/cdt-codes` typeahead) with an editable dollar field per row; dollars→cents on save.
- Wire `ProceduresSection` (and later treatment-plan item entry) to prefill the fee from
  the resolved practice fee on CDT selection.

**Dependencies / sequencing:** depends only on 3.5's `cdt_codes` table; independent of
eligibility. Build it before or alongside Module 6 (6 consumes these fees). Ships as its
own PR with its own design spec + plan.

**Open questions for its brainstorm:** full CDT catalog vs. the 20-code seed (a real fee
schedule likely wants the complete D-code list — that overlaps Module 6.2's catalog
seeding, so decide whether 3.6 or 6.2 owns seeding the full catalog); bulk import of an
existing fee schedule (CSV) so a practice isn't hand-entering hundreds of codes.

## Cross-module decisions locked in during brainstorming

- **Money is absolute cents everywhere.** Procedure rows, treatment-plan items,
  co-pay line items, claims, and ERA all store integer cents. The only place a
  *percentage* lives is the eligibility coinsurance rate (Module 5), which the
  Module 6 engine consumes as an input and converts to cents. Procedure rows do
  **not** store a coverage percentage.
- **Appointment procedures and treatment-plan items stay shape-compatible.**
  `appointment_procedures` mirrors `treatment_plan_items` field-for-field where it
  can (`tooth_number`, `procedure_code`, `procedure_name`, `surface`, `fee_cents`,
  `insurance_est_cents`, `patient_est_cents`) so a future "complete this plan item →
  create the procedure" link is a nullable FK with no reshaping.
- **3.5 captures data; it does not calculate.** Patient responsibility is entered
  manually (with a `estimate_source` provenance flag) until Module 6's pure
  calculation engine lands and consumes these rows verbatim.
- **Opt-in feature flags (already designed in `phase1_build_plan.md`).** Modules 5,
  6, 7 are per-practice opt-in via `practices.features`. Module 6 requires Module 5.
  Module 7 is independent of 5/6. 3.5 is not flagged — it is core scheduling data.
- **Clearinghouse:** Stedi for dev/staging, production primary per
  `research/17_clearinghouse_comparison.md`. Track monthly call usage per practice
  (250-call allowance on the $249/mo plan); overage policy still TBD.
