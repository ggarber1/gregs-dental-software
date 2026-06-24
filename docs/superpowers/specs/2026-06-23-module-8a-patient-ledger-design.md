# Module 8a — Patient Ledger Design

**Date:** 2026-06-23
**Status:** Approved — ready for implementation plan
**Depends on:** Module 3.5 (`appointment_procedures` — the charge source), Module 7b
(`claims` payment columns + `era_remittances` — the insurance-resolution source). 7b
explicitly deferred "writing to a patient ledger" to Module 8; this spec is that work.
**Source build plan:** `longterm_build_plan.md` §Phase 3 → Module 8. Module 8 bundles four
deliverables (ledger, statements, aging report, QuickBooks export); this spec is the
**ledger only (8a)**. Statements (8b), aging report, and QuickBooks export each get their
own spec → plan cycle.

## 1. Scope

The patient ledger is the practice's running financial record per patient: every charge,
payment, and adjustment as an immutable signed-cents entry, with a running balance =
"what the patient currently owes."

**In scope (8a):**
- One new append-only table `ledger_entries` (immutable; corrections via reversing
  entries) with four entry types: `charge`, `insurance_payment`, `patient_payment`,
  `adjustment`.
- A `ledger` service: charge posting (from completed-appointment procedures), insurance
  posting (from a matched ERA remittance), patient-payment recording, manual adjustment,
  reversal, and balance/ledger read.
- Integration hooks: post charges when an appointment transitions to `completed` (and
  re-sync when its procedures change afterward); post insurance payment + contractual
  adjustment when an ERA remittance matches a claim.
- API: read a patient's ledger + balance; record a patient payment; add a manual
  adjustment; reverse a manual entry.
- A **Ledger** section on the patient chart: balance badge, entries table, and
  "Record Payment" / "Add Adjustment" actions.

**Out of scope — deferred (see §9):**
- **Stripe card processing.** 8a *records* patient payments only (no money moves through
  our system). A future Stripe integration is documented in §9 as the intended next step.
- Patient-facing statements (email/print) — **Module 8b**.
- Insurance aging report (outstanding claims by carrier + age bucket).
- QuickBooks export.
- Full guarantor/family accounts. 8a is **per-patient**, but the schema carries a nullable
  `guarantor_account_id` so a household-billing layer can be added without a rewrite.

## 2. Key decisions

1. **Charge = gross fee, posted from completed procedures (not from the claim).** A charge
   ledger entry is the gross `fee_cents` of a procedure. Whether insurance "really" covers
   it is *not* decided at charge time — it is reconciled later by negative
   `insurance_payment` + `adjustment` entries from the ERA. This (a) makes self-pay a
   non-special-case (self-pay = a charge with no insurance entries ever arriving) and
   (b) means an imperfect initial charge self-corrects as the insurance side lands.
2. **Charge trigger = appointment `status → completed`** (checkout — the moment the front
   desk confirms what was done and collects payment). Claim *submission* is a billing
   action, not a financial event, and does **not** move the balance.
3. **Append-only / immutable entries.** Money rows are never UPDATEd or hard-DELETEd.
   Corrections post a **reversing entry** (`reverses_entry_id` set, sign flipped). Editing a
   procedure on an already-completed appointment reverses the stale charge and posts a new
   one. This gives a full audit trail for free.
4. **Running balance computed on read** as `SUM(amount_cents)` per patient. No cached
   balance column in 8a — single-practice volume makes drift risk the bigger cost than the
   sum. (A cached column is a clean later optimization if needed.)
5. **Insurance entries are derived from the `claims` row, not re-parsed from the ERA.**
   7b already posts `insurance_paid_cents` + `adjustments` onto the matched claim. 8a's
   insurance posting reads those and emits one `insurance_payment` entry and one summed
   contractual `adjustment` entry, linked to both `claim_id` and `remittance_id`.
6. **Per-patient now, guarantor-ready.** `guarantor_account_id` nullable column reserved;
   all 8a logic keys on `patient_id`.

## 3. Architecture & module layout

```
app/
  models/
    ledger_entry.py            # new: LedgerEntry (PHIMixin)
  services/
    ledger/
      __init__.py
      posting.py               # reconcile_charges_for_appointment, post_insurance_remittance,
                               #   record_patient_payment, add_manual_adjustment, reverse_entry
      balance.py               # get_patient_balance, get_ledger (entries + running balance)
  routers/
    ledger.py                  # GET ledger, POST payment, POST adjustment, POST reverse
  schemas/
    ledger.py                  # request/response (generated-types pipeline if applicable)
```

Integration touch-points (no new modules, just calls into existing flows):
- `app/routers/appointments.py::update_appointment` — on `→ completed` and on procedure
  edits to a completed appointment.
- `app/services/era/` match step — on a remittance matching a claim.

## 4. Data model

New table `ledger_entries` — `PHIMixin` (holds financial PHI), integer cents throughout.

| Column | Type | Notes |
|---|---|---|
| `practice_id` | uuid not null | scope |
| `patient_id` | uuid not null | indexed; the account the entry belongs to |
| `guarantor_account_id` | uuid nullable | reserved for future family billing |
| `entry_type` | str not null | `charge` \| `insurance_payment` \| `patient_payment` \| `adjustment` (check constraint) |
| `amount_cents` | int not null | **signed**: `charge` +, `insurance_payment`/`patient_payment`/`adjustment` −; reversal flips the original's sign |
| `appointment_id` | uuid nullable | source link (charge) |
| `appointment_procedure_id` | uuid nullable | source link (charge); the per-procedure dedup key |
| `claim_id` | uuid nullable | source link (insurance entries) |
| `remittance_id` | uuid nullable | source link (insurance entries) |
| `reverses_entry_id` | uuid nullable | the entry this one reverses; null for originals |
| `payment_method` | str nullable | `cash`\|`check`\|`card`\|`external_terminal`\|`other` — `patient_payment` only (check constraint) |
| `memo` | text nullable | free-text reason/description (required for manual `adjustment`) |
| `posted_by` | str not null | user id, or `system` for auto-posts |
| `posted_at` | timestamptz not null | default `now()` |

Plus `PHIMixin` columns (`id`, `created_at`, `updated_at`, `deleted_at`, `last_accessed_*`).

**Constraints & indexes:**
- `ck_ledger_entries_entry_type` — entry_type in the four values.
- `ck_ledger_entries_payment_method` — `payment_method IS NULL OR entry_type = 'patient_payment'` and value in the allowed set.
- **Charge idempotency — service-level, not a DB unique.** A "live charge" for a procedure
  is a `charge` entry that no reversing entry points at. A DB partial-unique on
  `appointment_procedure_id` cannot express this (a reversed original keeps
  `reverses_entry_id IS NULL`, so it would still occupy the slot and block the repost), so
  `reconcile_charges_for_appointment` enforces it: it computes live charges via
  `NOT EXISTS (a reversal referencing the entry)` and only posts/reverses on a real diff.
  `ix_ledger_entries_proc_charge` on `appointment_procedure_id` (partial, `entry_type='charge'`)
  supports that lookup but is **not** unique.
- **Insurance idempotency:** unique `(claim_id, remittance_id, entry_type)` — insurance
  entries are never reversed in 8a, so a plain unique works and re-polling an ERA never
  double-posts.
- `ix_ledger_entries_patient_posted` on `(patient_id, posted_at)` for ledger read + balance.
- `ix_ledger_entries_practice_deleted` on `(practice_id, deleted_at)`.

Migration: new alembic revision after 0033 (`ledger_entries` table only — no ALTERs).

## 5. Posting flows

**Charges (`reconcile_charges_for_appointment`).** Given a `completed` appointment: load its
procedures and its live charge entries. For each procedure with no live charge → post one
(`amount_cents = +fee_cents`). For each procedure whose `fee_cents` differs from its live
charge → reverse the stale charge and post a new one. For a live charge whose procedure was
deleted → reverse it. Idempotent: re-running with no changes posts nothing. Called when an
appointment transitions to `completed`, and when procedures change on an
already-`completed` appointment.

**Insurance (`post_insurance_remittance`).** Given a claim matched to a remittance (7b's
match step): post one `insurance_payment` entry (`−insurance_paid_cents`) and, if the
claim's contractual adjustments sum to non-zero, one `adjustment` entry (`−sum`), both
linked to `claim_id` + `remittance_id`. Guarded by the insurance-idempotency constraint.

**Patient payment (`record_patient_payment`).** Insert a `patient_payment` entry
(`−amount_cents`, `payment_method`, `memo`, `posted_by`). Amount must be > 0.

**Manual adjustment (`add_manual_adjustment`).** Insert an `adjustment` entry; sign per
caller (credit `−`, debit `+`); `memo` required.

**Reversal (`reverse_entry`).** Post a mirror entry (`−amount_cents`, `reverses_entry_id`
set). Reject if the target is itself a reversal or already reversed. Manual entries only in
8a (auto-posted charges are corrected through `reconcile_charges_for_appointment`).

## 6. Balance & read

`get_patient_balance(patient_id) → int` = `SUM(amount_cents)` over live entries. Positive =
patient owes; negative = credit balance (overpayment) — both valid.
`get_ledger(patient_id) → list` returns entries chronologically (`posted_at`) each annotated
with a running balance, plus the current balance. Reversed and reversing entries both
appear (the audit trail is visible).

## 7. API (`app/routers/ledger.py`, feature-gated)

- `GET /api/v1/patients/{patient_id}/ledger` → `{ entries: [...with running_balance], balance_cents }`
- `POST /api/v1/patients/{patient_id}/payments` → `{ amount_cents, payment_method, memo? }` → created entry
- `POST /api/v1/patients/{patient_id}/adjustments` → `{ amount_cents (signed), memo }` → created entry
- `POST /api/v1/ledger/entries/{entry_id}/reverse` → `{ memo? }` → reversing entry

Feature flag: a dedicated `billing_ledger` flag (sibling to `claims_submission`) so the
ledger can be enabled independently. Write endpoints require the write role (mirror
`appointments.py::_require_write_role`).

## 8. Frontend

A **Ledger** section on the patient chart (`apps/web/app/(app)/patients/[patientId]`):
- Current-balance badge (owes vs. credit, color-coded).
- Entries table: date, description (derived from entry_type + source), charge column,
  credit column, running balance. Reversed entries shown struck/greyed.
- "Record Payment" action (amount, method, memo) and "Add Adjustment" action (amount,
  memo). Both call the API and refresh.
- Reuses billing-area styling (`apps/web/app/(app)/billing`).

## 9. Deferred (roll into `longterm_build_plan.md` §Deferred)

- **Stripe card processing — documented next step.** 8a records payments only. The intended
  integration: a `POST /patients/{id}/payments` variant that creates a Stripe PaymentIntent,
  charges the card, and on success records the `patient_payment` entry with
  `payment_method='card'` and a `stripe_payment_intent_id` provenance column. Refunds become
  reversing entries tied to a Stripe refund. PCI handled via Stripe Elements (no card data
  touches our servers). Depends on the Phase 1 Stripe subscription billing being live.
- **Module 8b — patient-facing statements** (email/print); first real consumer of
  guarantor/family accounts.
- **Insurance aging report** (outstanding claims by carrier + age bucket).
- **QuickBooks export.**
- **Full guarantor/family accounts** (household balance aggregation).
- **Cached balance column** if read volume ever warrants it.

## 10. Testing

Per CLAUDE.md (new exported fn / endpoint → happy + one failure; run non-integration myself):
- **Unit (`services/ledger`)**: charge post for a new procedure; reverse+repost on
  `fee_cents` change; reverse on procedure delete; charge idempotency (re-run = no-op);
  insurance remittance posting (payment + summed adjustment) + idempotency; patient payment
  (happy + reject ≤ 0); manual adjustment (memo required); reversal (happy + reject
  double-reverse); `get_patient_balance` incl. credit balance; running-balance ordering.
- **API**: ledger GET; payment POST (happy + negative-amount 422); adjustment POST (happy +
  missing-memo 422); reverse POST.
- **Integration**: appointment `→ completed` posts charges; editing a procedure on a
  completed appointment re-syncs; ERA match posts insurance entries (ask before running —
  integration).

## 11. Cross-references

- `2026-06-22-module-7b-era-ingest-design.md` — §1 defers the ledger to Module 8; 8a reads
  the claim payment columns 7b populates.
- `2026-06-04-module-3.5-appointment-procedures-design.md` — the `appointment_procedures`
  charge source.
- `phase3-build-order.md` — Module 8 is the final Phase 3 node (requires 7).
