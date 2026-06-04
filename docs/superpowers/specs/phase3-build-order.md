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
Module 5.2–5.4 — Eligibility Verification  ← 5.1 (plan/patient_insurance CRUD) already done
        │
        ├──────────────┐
        ▼              ▼
Module 6 — Co-pay Calculation  (requires 3.5 procedures + 5 eligibility data)
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
| 1 | **3.5 — Per-Appointment Procedures** | nothing new | 5.2–5.4 | `2026-06-04-module-3.5-appointment-procedures-design.md` |
| 2 | **5.2–5.4 — Eligibility Verification** | 5.1 (done) | 3.5 | _tbd_ |
| 3 | **6 — Co-pay Calculation** | 3.5, 5 | — | _tbd_ |
| 4 | **7 — Claims Submission + ERA** | 3.5 (6 optional) | — | _tbd_ |
| 5 | **8 — Billing & Payments** | 7 | — | _tbd_ |

Modules 1 and 2 (3.5 and eligibility) are independent and may be built in either
order or concurrently. Everything after depends on 3.5 being in place.

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
