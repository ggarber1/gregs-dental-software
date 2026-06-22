# Module 7b — 835 ERA Ingest + Auto-Post Design

**Date:** 2026-06-22
**Status:** Approved — ready for implementation plan
**Depends on:** Module 7a (claims submission — built, PR #57). The `claims` table, the
`patient_control_number` (PCN) match key, and the reserved `paid/partially_paid/denied`
statuses all come from 7a.
**Source research:** `research/15_module7_claims_submission.md` (covers all of Module 7;
this spec narrows it to the **ERA half** and reconciles it with the codebase + verified
Stedi docs). **Two errors in that doc are corrected here** (see §2).

## 1. Scope

Module 7 is two halves: **(7a)** build + submit an 837D dental claim, **(7b)** ingest the
835 ERA the payer returns and auto-post the payment. This spec is **7b only**.

**In scope (7b):**
- A **synchronous, operator-triggered pull** of 835 ERAs from Stedi as **JSON** (Stedi
  translates the X12 835 → JSON; we never parse raw X12), via Stedi's `Poll Transactions`
  → `835 ERA Report` endpoints.
- A `RemittanceClient` ABC with a single **Stedi** adapter, an ERA **parser**
  (Stedi/CHC-Convert JSON → domain `ERAPayment`), a **match-by-PCN** step, and **auto-post
  onto the `claims` row** (claim-level).
- Two new tables — `era_remittances` (ingest + dedup + provenance) and
  `unmatched_era_payments` (manual-review queue) — plus payment columns on `claims`.
- A thin Remittances worklist + unmatched queue UI, and a payment readout on the existing
  claim panel.
- A **PCN length fix** carried over from 7a (Stedi requires ≤ 17 chars for reliable ERA
  matching; 7a emits 20).

**Out of scope — deferred (see §10):** async/webhook ERA ingestion; secondary/COB
auto-trigger; a queryable `claim_service_lines` table; writing to a patient ledger (that
is **Module 8** — 7b posts onto the claim only); manual re-matching of an unmatched
payment to a chosen claim.

## 2. Key decisions (and where they diverge from the research doc)

1. **Stedi JSON pull, no raw X12 — symmetric with 7a.** Verified against Stedi docs: the
   **835 ERA Report** endpoint (`GET /change/medicalnetwork/reports/v2/{transactionId}/835`)
   returns the ERA as JSON (Stedi uses the Change Healthcare "Convert" JSON shape). The
   `transactionId` comes from the **Poll Transactions** endpoint
   (`GET /pollingTransactions`, cursor-based) filtered to type `835`. So 7b parses Stedi
   JSON, exactly as 7a *sends* Stedi JSON. The research doc's hand-rolled `parse_835()`
   raw-X12 parser is **not built** (it would only be needed for a non-Stedi route — deferred
   with DentalXChange).
   - Refs: Stedi *835 ERA Report*, *Poll Transactions*, *List Transactions* docs.
2. **Auto-post onto the `claims` row, claim-level.** No payments/ledger table — that is
   **Module 8**. 7b writes payment columns onto `claims` and sets the reserved status. The
   research doc's `payments` table and `NUMERIC(10,2)` money are **both rejected**: money is
   **integer cents** (locked-in Phase 3 convention); dollar strings (`"123.45"`) convert to
   cents only at the parse edge. Service-line detail is preserved in `raw_response`; no
   `claim_service_lines` table in 7b.
3. **Synchronous poll-and-process slice; async deferred.** A `POST /era/poll` endpoint
   polls, dedups, fetches, parses, matches, and posts inline — mirroring 7a's sync submit
   slice and eligibility's sync slice. The async/webhook worker is deferred (§10).
4. **⚠️ Corrected CLP02 mapping.** The research doc says `19 = Denied`. That is **wrong**.
   In X12 835, CLP02 (claim status): `1/2/3` = processed (primary/secondary/tertiary),
   `19/20/21` = processed **and forwarded**, **`4` = Denied**, `22` = reversal. 7b uses the
   correct codes (see §6).
5. **Status is never inferred from the paid amount.** Per Stedi's explicit guidance, a $0
   payment can be a valid *accepted* claim. Status is driven by CLP02 + patient
   responsibility, never by `claimPaymentAmount == 0`.
6. **⚠️ PCN ≤ 17 fix (carried from 7a).** Stedi warns that some payers truncate the PCN
   beyond 17 chars in ERAs/acknowledgments, breaking match-back. 7a's `generate_pcn()`
   emits **20**. 7b shortens it to **≤ 17** and the matcher tries **exact, then prefix**.
   No migration: claim submission is still test-key-blocked, so **zero live claims exist**.
7. **Idempotent ingest via `UNIQUE(stedi_transaction_id)`.** A re-poll after a crash skips
   already-ingested ERAs (no second `fetch` call → also a Stedi-cost saving) and never
   double-posts.

## 3. Architecture & module layout

Mirrors the eligibility/claims pattern (provider client ABC + Stedi adapter + parser; pure
service orchestration; feature-gated, practice-scoped, audited router).

```
app/services/era/
  base.py        # RemittanceClient (ABC); ERAPayment, ClaimPayment, LineAdjustment;
                 # ERAFetchError(retryable=…)  — domain models, no Stedi types
  stedi.py       # StediRemittanceClient(RemittanceClient):
                 #   poll_transactions(since) → [transaction_id]  (filter 835, paginated)
                 #   fetch_era(transaction_id) → raw Stedi JSON
  parser.py      # parse_stedi_era(json) → ERAPayment   (CHC-Convert JSON → domain)
  service.py     # poll_and_post_eras(session, practice_id, *, client, user_sub) → summary
app/routers/era.py                 # POST /era/poll + GET/resolve endpoints
app/models/era_remittance.py       # ERARemittance, UnmatchedERAPayment
alembic/versions/00XX_era.py       # new tables + claim payment columns
scripts/stedi_era_smoke.py         # manual sandbox pull (Stedi Test Payer); not in CI
```

`RemittanceClient` is an ABC exactly like `ClearinghouseClient` / `EligibilityProvider`.
`StediRemittanceClient` is the only adapter in 7b. `ERAFetchError` carries `retryable`
(transport/5xx/timeout) so a poll can be safely re-run. Table naming is
**`era_remittances`** (not the research doc's `era_files` — there is no file; it is a JSON
pull).

## 4. Data model

**A. New columns on `claims`** (the auto-post target — money is integer cents):

```sql
ALTER TABLE claims ADD COLUMN insurance_paid_cents         INTEGER;
ALTER TABLE claims ADD COLUMN patient_responsibility_cents INTEGER;
ALTER TABLE claims ADD COLUMN payer_claim_control_number   VARCHAR(50);  -- CLP07 (payer's id)
ALTER TABLE claims ADD COLUMN adjustments                  JSONB;        -- [{group,code,cents}]
ALTER TABLE claims ADD COLUMN denial_codes                 TEXT[];       -- CARC codes when denied
ALTER TABLE claims ADD COLUMN paid_at                      TIMESTAMPTZ;
ALTER TABLE claims ADD COLUMN remittance_id                UUID;         -- → era_remittances (provenance)
```
Status moves to the reserved `paid` / `partially_paid` / `denied` (CheckConstraint already
permits them — no enum migration).

**B. `era_remittances`** — one row per ingested 835 (dedup + provenance):

```sql
CREATE TABLE era_remittances (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    practice_id          UUID NOT NULL,
    stedi_transaction_id VARCHAR(64) NOT NULL,     -- dedup key
    payer_name           VARCHAR(200),
    trace_number         VARCHAR(50),              -- TRN02 (check/EFT #)
    payment_cents        INTEGER,                  -- BPR02 total
    payment_date         DATE,
    claim_count          INTEGER,
    matched_count        INTEGER,
    unmatched_count      INTEGER,
    raw_response         JSONB NOT NULL,           -- full Stedi JSON (nothing lost)
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (stedi_transaction_id)                  -- re-poll never double-posts
);
```

**C. `unmatched_era_payments`** — a CLP with no matching claim → manual review (never
silently dropped):

```sql
CREATE TABLE unmatched_era_payments (
    id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    practice_id                UUID NOT NULL,
    remittance_id              UUID NOT NULL REFERENCES era_remittances(id),
    patient_control_number     VARCHAR(50),
    payer_claim_control_number VARCHAR(50),
    paid_cents                 INTEGER,
    raw_claim_payment          JSONB NOT NULL,
    resolved                   BOOLEAN NOT NULL DEFAULT false,
    resolved_at                TIMESTAMPTZ,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Both new tables use `PHIMixin` (they hold PHI), carry `practice_id` like every other table,
and get indexes on `practice_id`, `stedi_transaction_id` (unique), and `resolved`.

**D. PCN fix:** `generate_pcn()` shortened from 20 → **≤ 17** chars, still deterministic
from the claim UUID and X12-safe. The matcher tries **exact PCN, then prefix**.

## 5. ERA pull — data sources & the Stedi endpoints

| Step | Stedi endpoint | Notes |
|---|---|---|
| List new 835s | `GET /pollingTransactions` (cursor: `startDateTime` + `nextPageToken`) | Filter to type `835`. Cursor-based — **not** a re-`List` of a window (cost). |
| Fetch one ERA | `GET /change/medicalnetwork/reports/v2/{transactionId}/835` | Returns JSON (`meta` + `transactions[]`). |

Parsed `ERAPayment` fields (from the JSON): payer name, `trace_number` (TRN02),
`payment_cents`/`payment_date` (BPR/DTM), and `claim_payments[]`. Each `ClaimPayment` from
`claimPaymentInfo`: `patient_control_number`, `claimStatusCode` (CLP02),
`claimPaymentAmount`, `totalClaimChargeAmount`, `payerClaimControlNumber`,
`patientResponsibilityAmount`, `claimAdjustments[]` (group `CO/PR/OA/PI` + CARC + amount),
and `serviceLines[]` (preserved raw, not posted line-by-line in 7b).

## 6. Parse → match → post flow

`poll_and_post_eras(session, practice_id, *, client, user_sub)` behind `POST /api/v1/era/poll`:

1. **Poll** `client.poll_transactions(since=<recent window>)`, filter type `835` → ids.
2. **Dedup** — drop any `stedi_transaction_id` already in `era_remittances` (skips the
   `fetch` call entirely → Stedi-cost saving).
3. For each new id: `fetch_era(id)` → `parse_stedi_era(json)` → `ERAPayment`.
4. Insert the `era_remittances` row (full `raw_response`).
5. For each `ClaimPayment`, **match by PCN (exact, then prefix), scoped to `practice_id`**:
   - **Match** → post columns from §4 onto the claim, set status (table below), stamp
     `paid_at` + `remittance_id`.
   - **No match** → `unmatched_era_payments` row.
6. Update the remittance's `matched_count` / `unmatched_count`.
7. Return `{polled, new, matched, unmatched, remittance_ids}`.

Each remittance is processed in its own transaction; the `UNIQUE(stedi_transaction_id)`
guard makes the whole endpoint safely re-runnable after a crash with no double-posting.

**Status mapping (CLP02 → claim status):**

| CLP02 | Meaning | Claim status |
|---|---|---|
| `1` / `2` / `3` / `19` / `20` / `21` | Processed (paid / forwarded) | `partially_paid` if `patient_responsibility_cents > 0`, else `paid` |
| `4` | Denied | `denied` (+ `denial_codes` from CARC) |
| `22` | Reversal of prior payment | `denied` (flag for review; rare in Phase 1) |

Status comes from CLP02 + patient responsibility — **never** from `claimPaymentAmount == 0`.
All CAS triplets land in `claims.adjustments`; `PR`-group amounts also drive
`patient_responsibility_cents`. A `clearinghouse_rejected` claim never produces an ERA, so
the matcher does not expect one.

## 7. API

Practice-scoped, write-role, audit-logged, behind the existing `claims_submission` feature
gate (ERA is the back half of the same capability). Schemas added to the **Zod source** and
regenerated via `pnpm generate` (never hand-edit `generated.py`).

- `POST /api/v1/era/poll` — run `poll_and_post_eras`; returns the summary. `403` if the
  feature is disabled.
- `GET  /api/v1/era/remittances?from=&to=` — list ingested remittances (worklist).
- `GET  /api/v1/era/remittances/{id}` — detail incl. matched claims + `raw_response`.
- `GET  /api/v1/era/unmatched?resolved=false` — manual-review queue.
- `POST /api/v1/era/unmatched/{id}/resolve` — mark resolved (operator handled it manually;
  re-matching to a chosen claim is deferred).

## 8. Frontend

Thin, matching the eligibility/claims worklist style:
- The existing **Claim panel** on the appointment gains a payment readout once an ERA has
  posted: status badge (`paid` / `partially_paid` / `denied`), insurance paid, patient
  responsibility, and denial/CARC codes when denied.
- A minimal **Remittances** page: a "Poll for ERAs" button (calls `/era/poll`, shows the
  summary), the remittance list, and the **unmatched queue** with a resolve action. No
  deep EOB-editing UI in 7b.

## 9. Testing

TDD; new exported functions/endpoints ship with happy path + one failure case.

- **Unit:** `parse_stedi_era` against **recorded Stedi-JSON fixtures** (single paid,
  partially-paid with PR adjustment, denied with CLP02=4 + CARC, multi-claim, dollar→cents,
  missing/extra fields) — modeled on `test_eligibility_parser.py`. Status-mapping table
  (incl. the "$0 paid but accepted" case). `StediRemittanceClient` (`poll_transactions`
  filters 835 + paginates; `fetch_era` maps transport/5xx/timeout → `ERAFetchError`),
  httpx mocked like `test_stedi_provider.py`. `generate_pcn` ≤ 17; matcher exact-then-prefix
  incl. a truncated-PCN case.
- **Integration:** `poll_and_post_eras` — dedup (re-poll skips ingested ids, asserts **no
  2nd fetch**), PCN match posts correct cents + status, no-match writes
  `unmatched_era_payments`, crash-safety (re-run double-posts nothing). **Router:**
  `POST /era/poll` happy path, `403` when feature disabled, unmatched-resolve flow.
- **Smoke (not in CI):** `scripts/stedi_era_smoke.py` — one live pull against the **Stedi
  Test Payer**, run manually at **Staging Checkpoint 5** (blocked by the test-key tier until
  then, same as 7a's claim smoke).

## 10. Deferred (roll into `longterm_build_plan.md` §Deferred)

| Item | When |
|---|---|
| Async / webhook ERA ingestion (Poll worker or Stedi webhook → free push) | With the 7a async worker, near Staging Checkpoint 5 |
| Secondary / COB auto-trigger when `patient_responsibility > 0` | After 7b (needs the COB 837D loops, already deferred in 7a) |
| Queryable `claim_service_lines` (line-level payments) | If Module 8 / reporting needs line granularity |
| Writing to the patient ledger (charges/payments/balance) | **Module 8** |
| Manual re-match of an unmatched payment to a chosen claim | Demand-driven (Phase 1 just clears the flag) |
| Raw-X12 `parse_835()` for a non-Stedi route | With DentalXChange (deferred in 7a) |
| **Stedi call-cost efficiency** (cursor poll, transactionId dedup, webhooks over polling) | Cross-cutting — honored in 7b's poll; revisit each Stedi module |

## 11. Cross-references

- Pattern source: `app/services/eligibility/{base,stedi,parser}.py`,
  `app/services/claims/{base,stedi,service}.py`, `app/routers/{eligibility,claims}.py`.
- 7a hooks reused: `claims.patient_control_number` (match key), `claims` reserved statuses,
  the `claims_submission` feature gate, `generate_pcn` (shortened here).
- Stedi cost: poll/fetch calls count toward the monthly allowance and per-call cost — see
  `longterm_build_plan.md` §Deferred "Stedi call-cost efficiency" and
  `research/16_cost_and_scaling_model.md`.
- Stedi docs: 835 ERA Report (`get-healthcare-reports-835`), Poll Transactions
  (`edi-platform/.../get-pollingtransactions`), List Transactions
  (`edi-platform/.../get-list-transactions`).
