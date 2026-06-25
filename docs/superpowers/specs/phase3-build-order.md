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
Module 8 — Billing & Payments  (requires 7)
        8a — Patient Ledger (✅ built); 8b+ — statements, aging, QuickBooks export
```

## Build order

| # | Module | Depends on | Can parallelize with | Spec |
|---|--------|-----------|----------------------|------|
| 1 | **3.5 — Per-Appointment Procedures** | nothing new | 5.2–5.4 | `2026-06-04-module-3.5-appointment-procedures-design.md` (✅ done) |
| 2 | **3.6 — Practice Fee Schedule** | 3.5 (cdt_codes) | 5.2–5.4 | `2026-06-10-module-3.6-fee-schedule-design.md` (✅ done) |
| 3 | **5.2–5.4 — Eligibility Verification** | 5.1 (done) | 3.5 / 3.6 | `2026-06-11-module-5.2-5.4-eligibility-verification-design.md` (✅ sync slice done; async batch deferred) |
| 4 | **6 — Co-pay Calculation** | 3.5, 3.6, 5 | — | `2026-06-16-module-6-copay-calculation-design.md` (✅ **done** — PRs #53–#56: contracted fees, per-CDT coinsurance parser, full CDT catalog, engine+service+endpoints+card. DHMO/downgrade/secondary-COB deferred per §Deferred) |
| 5a | **7a — Claims Submission (837D)** | 3.5 (6 optional) | — | `2026-06-18-module-7a-claims-submission-design.md` (✅ built — Stedi Dental Claims JSON, sync submit slice; async/DentalXChange/MassHealth/secondary deferred per §11) |
| 5b | **7b — ERA Processing (835)** | 7a | — | _tbd (next spec)_ |
| 6 | **8 — Billing & Payments** | 7b | — | `2026-06-23-module-8a-patient-ledger-design.md` (✅ 8a built — append-only ledger, auto-posted charges + ERA insurance payment/write-off, record-only patient payments, adjustments/reversals, feature-gated router + chart tab; statements/aging/QuickBooks-export + Stripe deferred to 8b+) |

3.5, 3.6, and eligibility are independent and may be built in any order or
concurrently. Everything from Module 6 on depends on 3.5 being in place.

**Module 5.2–5.4 status (2026-06-11):** the *sync slice* shipped — `EligibilityProvider`
interface + Stedi adapter + 271 parser, the `eligibility_checks` table (migration 0027
ALTERs the table originally created by 0015: money → integer cents, adds `plan_name`,
relaxes `raw_response`), a synchronous `POST /api/v1/eligibility/check` + retrieval
endpoints (feature-gated via `require_feature`), and the patient-chart benefit-summary
card + verify button. The **deferred follow-ups** (design §9) are *not* a single
"async work" chunk — they split into three buckets with different timing:

- **Folds into Module 6 (do now):** the **per-CDT-code coinsurance model** (§9 item 7).
  Real dental 271s return coinsurance per CDT code under granular service-type codes
  (confirmed via live Stedi sandbox 2026-06-12), not by preventive/basic/major/ortho
  buckets — so the keyword categorizer was removed and `coinsurance_*` fields are `None`,
  with per-code data preserved in `raw_response`. Structuring the CDT-code → patient-share
  map is a **Module 6 design decision** that Module 6's accuracy depends on; design it in
  the Module 6 brainstorm, not as a standalone Module 5 follow-up.
- **Bundle with Staging Checkpoint 5 (after a live sync call is proven):** the SQS
  `eligibility-worker` + EventBridge 3-day pre-appointment batch (§9 item 1), the
  appointment-slot badge (item 2), and the verification-queue page (item 3). The batch
  pipeline can't be exercised locally — it needs the deployed ECS private subnet — and
  Checkpoint 5 is the *first* live outbound Stedi call from that env (sync slice is only
  unit-tested against recorded 271 fixtures so far). Correct sequence: fire one successful
  live sync `/check` call at Checkpoint 5 (proves the Stedi contract + NAT/SSM/IAM), *then*
  build the worker on that proven provider + parser. The badge/queue UI ride along since
  they're empty until the batch populates pre-appointment data. **No downstream module is
  blocked on this** — Module 6 (pure calc) and Module 7 (claims) don't consume the async
  pipeline; its only consumer is the proactive "auto-verify 3 days out" UX, so it's
  value-driven, not schedule-driven.
- **Demand-driven (don't schedule):** the DentalXChange adapter (§9 item 4 — only if prod
  needs a dental-specific fallback; Stedi is prod primary), MassHealth (CKMA1) hardcoded
  frequency reference data (item 5 — when a MassHealth practice onboards), and
  secondary-insurance COB (item 6 — Module 6 territory).

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
