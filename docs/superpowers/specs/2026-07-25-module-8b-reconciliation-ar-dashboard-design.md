# Module 8b — ERA Reconciliation & Practice A/R Dashboard — Design

**Date:** 2026-07-25
**Phase:** 3 — Billing & Insurance Depth
**Module:** 8b (reconciliation + overpayment + billing dashboard)
**Status:** Approved for implementation
**Depends on:** Module 6 (copay estimate), Module 7b (ERA ingest), Module 8a (ledger), PR #61 (insurance A/R worklist), PR #62 (claim recovery)

---

## Purpose

Two gaps closed in this module:

1. **ERA reconciliation** — after Module 7b auto-posts an ERA, staff have no way to see settled claims that were "interesting" (insurance paid more than estimated, payment differed from estimate, or no estimate existed). Overpayments in particular are invisible: the patient may have a negative ledger balance and no one sees it. This module surfaces those cases in a new Reconciled tab on the claims page, with an optional confirm-mode queue.

2. **Practice A/R dashboard** — `/billing` is currently a placeholder. This module replaces it with a real summary: insurance owes $X, patients owe $Y, N claims need attention. It becomes the natural landing page for any billing work.

---

## What is NOT in scope

- Patient statements (email/print) — separate future module
- Automatic patient credit posting for overpayments — see Data Semantics section
- Overpayment refund workflow
- QuickBooks export, guarantor/family accounts, Stripe card processing
- Any change to `post_insurance_remittance` (ledger/posting.py)

---

## Data Semantics

### Overpayment — no auto-credit

When insurance pays more than the Module 6 estimate, **no special ledger entry is posted**. The existing `insurance_payment` entry already captures the full amount paid. The patient's running ledger balance (sum of all entries) naturally reflects the overpayment — if insurance paid more than the patient's total charge, the balance goes negative.

Auto-posting a "credit" entry based on `insurance_paid_cents − estimated_insurance_cents` would be wrong: it assumes the patient paid exactly their estimated co-pay at checkout, which may not be true. The ledger already knows the truth.

Instead, the reconciliation view surfaces the negative-balance signal and staff acts on it at the next visit or manually posts a refund adjustment.

### Reconciliation classification

**Auto mode** shows only "interesting" ERA-settled cases:

| Condition | Label | Note |
|---|---|---|
| `insurance_paid_cents > estimated_insurance_cents` | Overpaid | Patient balance may be negative |
| `0.95 × estimate ≤ paid < estimate` | Within tolerance | Small variance |
| ERA posted, `has_estimate = false` | No estimate | Paid but unverifiable against Module 6 |

Exact-match settlements (`paid === estimate`) are silently Done in auto mode — no variance, nothing to flag.

**Confirm mode** shows ALL ERA-settled claims not already in Underpaid/Problem/Appealing, including exact matches. The point of confirm mode is that a human reviews every settlement, not just the interesting ones. Exact-match rows appear in the queue with a "Matched" label and no variance.

In both modes, underpaid claims (`paid < 0.95 × estimate`) stay in the Underpaid tab — they need an appeal/accept decision, not a reconciliation confirmation. A claim is only eligible for the Reconciled tab if it is not in Underpaid, Problem, or Appealing.

`variance_cents` sign convention: positive = insurance paid more than estimated (overpaid); negative = insurance paid less (within-tolerance shortfall); null = no estimate.

### Confirm mode

Practices can optionally require staff to confirm each ERA settlement. Stored in `practice.automation_config` JSONB as:

```json
{ "era_reconciliation_mode": "auto" }   // default — no queue, history only
{ "era_reconciliation_mode": "confirm" } // unconfirmed claims sit in queue
```

No migration needed — the key is read from the existing JSONB column with a fallback to `"auto"`.

Confirmation is tracked via a new nullable column: `claims.reconciliation_confirmed_at TIMESTAMPTZ`.

### Patient A/R total

`patient_ar_total_cents` is the sum of **positive** patient ledger balances across all patients (negative balances — credits — are excluded from the "owed" total and surfaced separately in the reconciliation view). Computed by summing `ledger_entries.amount_cents` per `patient_id` and filtering to those with `balance > 0`.

---

## UI Structure

### Before this module

```
Sidebar → Billing → /billing  (placeholder "Coming in Module 1.6")
                  → /billing/claims
                  → /billing/remittances
                  → /billing/insurance-ar  (4 tabs: Awaiting / Underpaid / Problem / Appealing)
```

### After this module

```
Sidebar → Billing → /billing              (Practice A/R Dashboard — replaces placeholder)
                  → /billing/claims       (unified claims hub — 6 tabs, see below)
                  → /billing/remittances  (unchanged)
```

`/billing/insurance-ar` is **merged into** `/billing/claims`. The standalone insurance-ar route can redirect to `/billing/claims` for backwards compatibility.

### `/billing/claims` tab structure

| Tab | Content | Actionable? |
|---|---|---|
| All | Every claim for this practice, newest first | No (reference) |
| Awaiting | Submitted, no ERA yet | No |
| Underpaid | ERA posted, paid >5% below estimate | Yes — Accept / Flag for appeal |
| Problem | Denied / clearinghouse-rejected / submission-failed | Yes — Resubmit / Write off |
| Appealing | Flagged by staff for appeal | Yes — Resubmit / Write off |
| Reconciled | ERA-settled interesting cases (see classification above) | Yes in confirm mode — Confirm button |

The **Reconciled tab** shows a count badge when `era_reconciliation_mode = "confirm"` and unconfirmed items exist: "Reconciled (3)". Badge disappears when the queue is empty.

In auto mode, the Reconciled tab is a plain history log with no badge.

---

## `/billing` — Practice A/R Dashboard

Replaces the "Coming in Module 1.6" placeholder.

### Summary cards

| Card | Data | Link |
|---|---|---|
| Insurance A/R | Total billed awaiting carrier + underpaid shortfall (dollars) | → `/billing/claims?tab=awaiting` |
| Claims Needing Attention | Count of problem + appealing claims | → `/billing/claims?tab=problem` |
| Patient A/R | Sum of positive patient balances (from ledger) | → future statements page ("Coming soon") |
| Reconciliation Pending | Count of unconfirmed reconciliation items | → `/billing/claims?tab=reconciled` — only renders in confirm mode when count > 0 |

Data from a single `GET /reports/ar-summary` endpoint.

---

## Backend

### Migration 0037

```sql
ALTER TABLE claims
  ADD COLUMN reconciliation_confirmed_at TIMESTAMPTZ;
```

No index needed — queries filter on `reconciliation_confirmed_at IS NULL` only within the reconciliation service, which already filters to a small subset of claims.

### Service — `app/services/reports/reconciliation.py`

Pure functions, fully unit-testable (same pattern as `insurance_ar.py`):

**`classify_reconciliation_claims(claims, copay_map, ledger_balance_map)`**
- Filters to ERA-settled claims not already in Underpaid/Problem/Appealing
- Applies the three-condition classification above
- Returns per-claim rows: `{ claim_id, patient_name, payer_id, carrier_name, category, billed_cents, estimated_insurance_cents, insurance_paid_cents, variance_cents, has_estimate, patient_balance_cents, days_since_era, reconciliation_confirmed_at }`

**`get_ar_summary(session, practice_id)`**
- Returns `{ insurance_ar_total_cents, patient_ar_total_cents, claims_needing_attention, reconciliation_pending_count }`
- `insurance_ar_total_cents` = sum of `estimated_insurance_cents` for awaiting-carrier claims + sum of `shortfall_cents` for underpaid claims
- `patient_ar_total_cents` = sum of positive patient balances from ledger
- `reconciliation_pending_count` = count of interesting ERA-settled claims with `reconciliation_confirmed_at IS NULL`

### Endpoints — additions to `app/routers/reports.py`

All gated on `require_feature(session, practice_id, "claims_submission")`.

**`GET /api/v1/reports/reconciliation/claims`**
Query params: `confirmed` (`true` | `false`, optional — omit for all).
Response: list of per-claim rows as above.

**`POST /api/v1/reports/reconciliation/claims/{claim_id}/confirm`**
Sets `reconciliation_confirmed_at = now()`.
Validates: claim belongs to practice; `reconciliation_confirmed_at` is currently null (reject if already confirmed). Returns the updated row.

**`GET /api/v1/reports/ar-summary`**
Returns the AR summary shape above.

---

## Frontend

### `apps/web/app/(app)/billing/page.tsx`

Replace the placeholder with a grid of summary cards. Each card: title, dollar amount or count, subtitle, and a link. The Reconciliation Pending card only renders when `reconciliation_pending_count > 0` and practice is in confirm mode. Uses `useARSummary` hook.

### `apps/web/app/(app)/billing/claims/page.tsx`

Extend the existing claims page to add the Reconciled tab alongside the four existing tabs (Awaiting / Underpaid / Problem / Appealing). Keep the existing All tab.

The Reconciled tab:

- **Auto mode:** flat table, newest ERA first. Columns: Patient / Carrier / Billed / Est. ins. / Paid / Variance / Patient balance. Overpaid rows show a green "Overpaid" badge on the variance column. Negative patient balance rows show a yellow "Credit balance" badge.
- **Confirm mode:** same table split into two sections — "Needs review" (unconfirmed rows, each with a Confirm button) and "Recent" (confirmed rows below a divider). Tab label shows count badge when unconfirmed items exist.

The `/billing/insurance-ar` route redirects to `/billing/claims` (with appropriate tab query param) for any bookmarked links.

### `apps/web/lib/api/reports.ts`

Add to the existing `reportsKeys` namespace:
- `useReconciliationWorklist(confirmed?: boolean)`
- `useConfirmReconciliation(claimId)` — mutation
- `useARSummary()`

---

## Testing

### Service unit tests (`reconciliation.py`)

- Overpaid claim appears; underpaid claim does NOT (classification boundary)
- Within-tolerance claim appears in both modes; exact-match (`paid === estimate`) appears only in confirm mode with a "Matched" label and `variance_cents = 0`
- No-estimate claim appears with `has_estimate = false`, no variance computed
- Confirmed claim (`reconciliation_confirmed_at` set) excluded from unconfirmed list
- Patient balance computed correctly: charge − insurance payment − patient payment
- Negative patient balance triggers "Credit balance" flag
- `patient_ar_total_cents` excludes negative (credit) balances

### AR summary tests

- `insurance_ar_total_cents` sums awaiting expected + underpaid shortfall correctly
- `patient_ar_total_cents` excludes patients with negative balance
- `reconciliation_pending_count` counts only unconfirmed interesting ERA-settled claims

### Endpoint tests

- Confirm action sets `reconciliation_confirmed_at`; claim leaves `?confirmed=false` list
- Confirm rejects a claim from another practice (403)
- Confirm rejects an already-confirmed claim (409)
- `?confirmed=true` filter returns only confirmed claims
- All three endpoints reject when `claims_submission` feature flag is off

### Frontend

No automated tests — validate manually:
- Dashboard cards render correct totals
- Reconciled tab badge appears and clears as items are confirmed
- Reconciliation Pending dashboard card only shows in confirm mode with pending items
- Overpaid / Credit balance badges render on correct rows
- Redirect from `/billing/insurance-ar` lands on the right tab

---

## Deferred

- Patient aging + statements (separate spec)
- Overpayment refund workflow (post a manual adjustment from the reconciliation row — demand-driven)
- Practice-level confirm mode toggle in the Settings UI (for now, set via `automation_config` directly or a future config panel per longterm_build_plan.md §4.3.1)
