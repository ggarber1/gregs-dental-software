# Module 8b — Insurance A/R Worklist (Aging + Underpayment) — Design

**Date:** 2026-06-29
**Phase:** 3 — Billing & Insurance Depth
**Module:** 8b (first slice — "insurance work that needs doing")
**Status:** Design in review; ready for implementation plan once approved
**Depends on:** Module 6 (copay estimate), Module 7a/7b (claims + ERA), Module 8a (ledger)

## Purpose

Give the practice one view of **all insurance A/R that needs a human's attention**, read over
the existing `claims` table joined to the Module 6 estimate. Three things need attention:

1. **Awaiting carrier** — claims sent but not yet paid, aged (chase the carrier; oldest first,
   timely-filing risk).
2. **Underpaid** — claims insurance has paid, but **materially below what we estimated** (a
   likely insurance mistake / wrongful partial denial). The practice can **appeal** or
   **accept**.
3. **Problem** — `denied` / `clearinghouse_rejected` / `submission_failed`, with the reason
   (rework / appeal / resubmit).

Two presentations: a **worklist** (the primary working tool — flat, sortable, filterable) and
a **birds-eye summary** (carrier × age-bucket, plus per-carrier underpaid/problem counts).

### Why underpayment detection is core (not a follow-on)

The dentist already estimates by hand what insurance should pay — partly to charge the patient
at checkout, partly to **catch carriers paying too little**. If insurance pays $200 on a claim
we expected $840, that's the single most important claim to see and fight — hiding it just
because "insurance responded" would bury the money most at risk. Module 6 already persisted the
estimate; comparing it to the actual ERA payment is what surfaces the mistake.

### Classify by the numbers, not the status label

Claim status (`paid` / `partially_paid`) is set by 7b from the 835 and **may be wrong or too
crude**. So this report does **not** trust the label to decide "insurance is done." It keys off
the data: *has an ERA posted (`insurance_paid_cents` populated)?* and *how does the actual
compare to our estimate?* A claim labeled `paid` that paid far below estimate is still flagged
underpaid.

This report is the **carrier-follow-up** half of the revenue cycle. The patient-side half
(patient owes after adjudication → statements) is the separate patient-aging sibling — see
"Follow-on."

## Data semantics

All money is integer cents (absolute, per the Phase 3 money convention).

### Estimate source (the expected-insurance number)

`estimated_insurance_cents` for a claim is resolved through its appointment, read-only (never
recomputed — we use what Module 6 stored at checkout):

1. Prefer the latest `copay_calculations` row for `claim.appointment_id`
   (`total_insurance_owes_cents`, honoring any staff `override_*`).
2. Else sum `appointment_procedures.insurance_est_cents` for that appointment.
3. Else **no estimate** (`has_estimate=false`). Such a claim can still be *awaiting-carrier* or
   *problem*, but it can **never** be flagged *underpaid* (nothing to compare against), and it
   is excluded from any "expected" total, with an `unestimated_count` surfaced so a blank
   expected is never read as $0.

### Classification (evaluated in order, per claim)

| # | Condition | Category | Shows |
| - | --- | --- | --- |
| 1 | status == `appealing` | **Appealing** (triage) | billed, estimate, any prior paid |
| 2 | status ∈ `denied`, `clearinghouse_rejected`, `submission_failed` | **Problem** | billed, reason |
| 3 | `insurance_paid_cents` is null (status `submitted`/`acknowledged`/`pending`) | **Awaiting carrier** | billed, estimate |
| 4 | ERA posted AND `has_estimate` AND `insurance_paid_cents < 0.95 × estimated_insurance_cents` AND not yet reviewed | **Underpaid** | billed, estimate, actual paid, shortfall |
| 5 | otherwise (ERA posted, paid ≥ 95% of estimate, or no estimate, or already reviewed) | **Done** (excluded) | — |

`appealing` is evaluated **first** and is its own category — **not** folded into "awaiting
carrier" aging, because (see below) nothing was actually re-submitted to the carrier, so aging
it as if we're waiting on a carrier response would be misleading.

**Auto vs. manual:** only `underpaid` is *computed* (the estimate-vs-actual comparison below).
`appealing` is **never** auto-assigned — it is written solely by the manual "Flag for appeal"
action (you never auto-contest a carrier). The other categories are derived from existing
status/amount data. So classification = automatic *detection* (awaiting / underpaid / problem)
+ one human-set state (`appealing`).

**Underpaid threshold:** flag when the actual insurance payment is **more than 5% below** the
estimate, i.e. `insurance_paid_cents < 0.95 × estimated_insurance_cents`. The 5% tolerance keeps
rounding/minor-variance noise out of the worklist. (Threshold lives as a named constant so it's
trivially tunable.)

**Overpayment** (insurance paid *more* than estimated) is **not** flagged here — it's not money
we're owed; any resulting patient credit/refund is a ledger/reconciliation concern (deferred).

### Aging clock

Whole days between `submitted_at` and "now" (date-based); fall back to `created_at` if
`submitted_at` is null (defensive). A claim sits in exactly one bucket. Buckets: `0–30`,
`31–60`, `61–90`, `90+`. Aging applies to **awaiting-carrier** claims; underpaid/problem claims
are worklist items, not aged dollars (but still carry `days_out` for sorting).

### Reason source for problem claims

Both reason types originate from **Stedi**, but from two different responses:

- `denied` → **CARC/CAS codes from the 835 ERA** (Stedi's ERA report; Module 7b parsed them).
  Read from `claims.denial_codes` (text[], e.g. CARC `45`) and `claims.adjustments` (JSONB
  CAS group/code/amount).
- `clearinghouse_rejected` / `submission_failed` → from the **claim-submission response**
  (Stedi's synchronous 277CA / acknowledgment at submit time; Module 7a captured it). Read from
  `claims.submission_errors` (text[]) and `claims.clearinghouse_status`.

All fields exist on the `claims` model already.

**Readability caveat:** these are standardized X12 codes, not friendly English. Confirm during
implementation whether Stedi's JSON already includes human-readable descriptions; if not, add a
small static **CARC/CAS code → description lookup** for display (e.g. CARC `45` → "charge
exceeds fee schedule"). v1 may show raw codes; the friendly mapping is a cheap follow-up.

## Resolution actions (this report is lightly stateful)

An **underpaid** claim needs a human decision, so the worklist is actionable — not read-only.
Two actions, and an explicit boundary on what "appeal" means today:

- **Accept** ("the estimate was off; this payment is correct") → set a new
  `claims.insurance_reviewed_at` timestamp. The claim leaves the Underpaid list and is treated
  as **Done**. (One ERA per claim, so a reviewed claim never re-surfaces.)
- **Flag for appeal** → set claim `status = 'appealing'`, moving it to the **Appealing**
  category. **This is a triage marker only — it does NOT submit anything to the carrier.** It
  records "staff is contesting this" so it stops nagging in Underpaid and is visible as
  in-progress. The actual appeal (a corrected-claim resubmission and/or appeal documentation /
  275 attachment) is **not built** — see the gap note below. Module 8b is the first code to
  ever write the `appealing` status.

> **No claim-recovery machinery exists.** There is no resubmission path (the
> `submission_attempt` counter is never incremented; no fix-and-resend endpoint), no real
> appeal workflow, and no 275 attachment support. So for **Problem** claims (denied / rejected
> / failed) and **Appealing** claims, Module 8b provides **visibility + triage only** — it
> surfaces them with reasons and lets staff flag intent; the actual correction/resubmission/
> appeal is done manually/externally for now. This whole capability is captured as a deferred
> roadmap item ("Claim recovery & appeals") in `longterm_build_plan.md`. **Open discrepancy to
> resolve there:** whether a `denied` claim posts a contractual write-off to the ledger (8a
> memory says yes; the 7b ERA-posting code only writes off alongside an insurance payment).

**Migration (0036):** add nullable `claims.insurance_reviewed_at TIMESTAMPTZ`. This is the only
schema change; everything else reads existing columns.

## Carrier grouping

No payers/carriers table — `claim.payer_id` (String) is the grouping key. Resolve a friendly
display name best-effort via `InsurancePlan.payer_id → carrier_name`, falling back to the raw
`payer_id`. Grouping is always by `payer_id`, so display-name ambiguity never affects the math.

## Backend

### Service — `app/services/reports/insurance_ar.py`

Pure functions over a claims query (joined to the Module 6 estimate), fully unit-testable:

- Build **per-claim rows** (shared by both endpoints): resolve estimate, classify per the table
  above, and compute billed / estimated / actual-paid / shortfall / days_out / bucket / status /
  reason / category. Apply the worklist filters (carrier / category / bucket / status) and sort
  server-side.
- Derive the **birds-eye summary** by aggregating the awaiting-carrier rows: per `payer_id`,
  four billed buckets + `total_billed_cents` + `expected_cents` (estimated awaiting-carrier
  only) + `claim_count` + `unestimated_count`; plus per-carrier **`underpaid_count`** and
  **`problem_count`**; then a TOTAL row. Aggregating from the same rows keeps summary and
  worklist reconcilable by construction.

The 5% threshold is a module-level named constant.

### Endpoints — new `reports` router (`/api/v1`), gated on `claims_submission`

Reuse the `claims_submission` feature flag (decision: option A — a view over claims, not a
separable capability). Gate via the existing `require_feature(session, practice_id,
"claims_submission")` pattern from `claims.py` / `era.py`.

- `GET /reports/insurance-ar/claims` → **worklist**. Query params (all optional): `category`
  (`awaiting` | `underpaid` | `problem` | `appealing`), `payer_id`, `bucket` (`0-30|31-60|61-90|90+`),
  `status`, `sort` (default `oldest` = `days_out` desc). Each row: `{ claim_id, claim_number,
  patient_name, payer_id, carrier_name, category, billed_cents, estimated_insurance_cents,
  insurance_paid_cents, shortfall_cents, has_estimate, days_out, bucket, status, reason }`.
- `GET /reports/insurance-ar/summary` → **birds-eye**: `{ carriers: [{ payer_id, carrier_name,
  claim_count, buckets:{b0_30,b31_60,b61_90,b90_plus}, total_billed_cents, expected_cents,
  unestimated_count, underpaid_count, problem_count }], totals: {…same shape…} }`.
- `POST /reports/insurance-ar/claims/{claim_id}/appeal` → set `status='appealing'`; returns the
  updated row.
- `POST /reports/insurance-ar/claims/{claim_id}/accept` → set `insurance_reviewed_at=now()`;
  returns the updated row.

Both write endpoints validate the claim belongs to the practice and is currently in the
Underpaid category (reject otherwise).

## Frontend

New page `app/(app)/billing/insurance-ar/page.tsx`, following the claims / remittances worklist
pattern (Next.js App Router, `"use client"`, TanStack Query, shadcn Table/Badge, `centsToUsd`):

- **Worklist (primary):** flat table — columns `Claim # | Patient | Carrier | Billed |
  Est. ins. | Paid | Days | Status/Category`. Empty Est./Paid render "—".
  - **Category tabs/filter:** Awaiting carrier · Underpaid · Problem · Appealing (plus carrier /
    age / status filters; oldest-first default sort).
  - **Underpaid rows** show estimate vs. actual and the shortfall (e.g. "est $840 · paid $200 ·
    −$640") with **Accept** / **Flag for appeal** buttons inline (mutations → invalidate the
    list). The appeal button's tooltip notes it's a triage flag, not a carrier submission.
  - **Problem rows** show the status badge + reason inline (e.g. "denied · D9 not covered").
  - Rows link to the claim panel.
- **Summary (birds-eye):** carrier rows × 4 billed buckets + `Total` + `Expected` columns + a
  TOTAL footer; plus small `Underpaid` / `Denied` count columns so a chronically-underpaying
  carrier is visible at a glance. Un-estimated count surfaced where present.
- New hooks in `lib/api/reports.ts` (`reportsKeys` namespace).

## Testing

- **Service unit tests:** classification order (a `denied` claim never lands in Underpaid even
  with a shortfall; `appealing` is Awaiting even with a prior payment; null `insurance_paid` →
  Awaiting); **underpaid threshold boundary** — paid at exactly 95% of estimate is *not*
  flagged, just under *is*, a large shortfall *is*; a claim **mislabeled `paid` but paid <95%
  of estimate is still flagged** (robust to status code); no-estimate claim is never Underpaid
  and never in `expected_cents`; reviewed claim (`insurance_reviewed_at` set) drops to Done;
  bucket boundaries (29/30/31/60/61/90/91 days); summary aggregation reconciles with the
  worklist (carrier buckets sum to TOTAL; underpaid/problem counts correct).
- **Action tests:** `appeal` moves a claim Underpaid → Appealing (status `appealing`, its own
  category, not aged as awaiting-carrier); `accept` sets `insurance_reviewed_at` and moves it to
  Done; both reject a claim not in Underpaid and a claim from another practice.
- **Endpoint tests:** worklist happy path + a category filter + sort; summary happy path with
  TOTAL row; all endpoints feature-gate-off (`claims_submission` disabled) rejected.

## Out of scope (later 8b+)

Patient-facing statements, QuickBooks export, full guarantor/family accounts, Stripe card
processing, the dad-gated checkout/payment UX, and driving an *alert* off aged/underpaid claims
(that's the separate observability story).

### Follow-on sibling reports (noted, not built here)

This report folds in **underpayment** detection (the high-value half of reconciliation). What
remains:

1. **Full reconciliation / overpayment + refunds.** Overpayments (insurance paid more than
   estimated) and the resulting patient credits/refunds are a ledger concern, not insurance A/R
   — deferred.
2. **Patient aging + statements.** When a patient doesn't pay their post-adjudication balance at
   checkout, that patient A/R (in the Module 8a ledger) needs a patient-grouped aging report →
   statements. Above both, a practice dashboard can total *insurance owes $X / patients owe $Y*.
