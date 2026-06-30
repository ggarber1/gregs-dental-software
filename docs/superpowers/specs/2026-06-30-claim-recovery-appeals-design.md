# Claim Recovery & Appeals — Design

**Date:** 2026-06-30
**Phase:** 3 — Billing & Insurance Depth
**Status:** Approved — ready for implementation plan
**Depends on:** Module 7a (claims submission), Module 7b (ERA ingest), Module 8a (ledger),
Module 8b (insurance A/R worklist — surfaces the problem claims this feature resolves)

## 1. Scope

Today there is no recovery path for a claim that rejects, fails, or is denied. This spec
closes that gap with three deliverables:

1. **Resubmission** — a single `POST /claims/{id}/resubmit` endpoint that handles all
   problem states (`clearinghouse_rejected`, `submission_failed`, `denied`, `appealing`),
   increments the attempt counter, and re-sends a corrected 837D to the clearinghouse.
2. **Write-off** — a `POST /claims/{id}/write-off` endpoint that posts a ledger
   adjustment zeroing the patient's remaining balance and marks the claim resolved.
3. **Patient Claims tab** — a new tab on the patient page showing all claims for that
   patient with status, reason, and inline actions.

Across all three surfaces the reason a claim failed is displayed in plain English
(decoded CARC descriptions interpolated with CDT codes and carrier name) so staff
know exactly what to fix before resubmitting.

**Also resolves in this spec:** the open discrepancy about whether a denied claim posts
a contractual write-off to the ledger — see §2.

**Out of scope (deferred):**
- 275 claim attachments / appeal documentation
- Automated denial contestation
- Full submission-attempt audit trail with raw payload replay (the `submission_history`
  JSONB snapshot covers the display use case)
- Secondary / COB claim resubmission

## 2. Denial write-off discrepancy — resolved

The 8b spec note ("7b ERA-posting code only posts write-offs alongside an insurance
payment") was incorrect. `post_insurance_remittance` in `app/services/ledger/posting.py`
has **two independent `if` blocks**:

```python
if paid and not await _insurance_entry_exists(..., "insurance_payment"):
    session.add(...)   # posts only if paid > 0

if writeoff and not await _insurance_entry_exists(..., "adjustment"):
    session.add(...)   # posts if writeoff > 0 — NO dependency on paid
```

**The intended and actual behaviour:**
- A denial ERA that includes CO/OA CAS adjustments → those adjustments are
  written off automatically when the ERA is polled. This is correct: the carrier
  is communicating the provider's contractual obligation via CAS codes.
- A denial ERA with no CO/OA adjustments (e.g. "missing auth", CARC 97) → no
  write-off is posted; the patient balance stays at the gross charge. Also correct —
  the practice may resubmit after obtaining auth; the charge should remain.

**No code change needed.** The discrepancy was a documentation misread. This spec
documents the correct behaviour so the ambiguity does not persist.

**Interaction with resubmission:** if a denial ERA auto-posted CO/OA write-offs and
the practice then chooses to resubmit (contesting the denial), the resubmission service
reverses those write-offs before re-sending the claim — see §4.

## 3. Data model — one migration (0037)

Two new columns on `claims`. No new tables.

```sql
-- Append-only JSON array; one entry pushed before each resubmission.
-- Preserves "why was it denied before" context for the UI without a separate table.
ALTER TABLE claims ADD COLUMN submission_history JSONB;

-- '1' = original claim (default); '7' = corrected replacement of a prior denied claim.
-- Drives the claim frequency code in the 837D builder.
ALTER TABLE claims ADD COLUMN claim_frequency_code VARCHAR(2) NOT NULL DEFAULT '1';
```

`submission_history` schema (append-only array; never mutated in place):
```json
[
  {
    "attempt": 1,
    "status": "denied",
    "denial_codes": ["96"],
    "payer_ccn": "CCN123456",
    "submitted_at": "2026-06-15T10:00:00Z"
  }
]
```

`claim_frequency_code` values:
- `"1"` — original (clearinghouse_rejected / submission_failed resubmissions, because
  the carrier never received the original)
- `"7"` — corrected replacement (denied / appealing resubmissions; triggers the
  corrected-claim reference in the 837D using `payer_claim_control_number`)

## 4. Resubmission service

**Entry point:** `resubmit_claim(session, practice_id, claim_id, *, client, usage_indicator, user_sub)`
in `app/services/claims/service.py` alongside the existing `submit_claim_for_appointment`.

**Pre-condition:** claim must be in `{clearinghouse_rejected, submission_failed, denied, appealing}`.
Any other status raises `ClaimSubmissionPrereqError("CLAIM_NOT_RESUBMITTABLE", ...)` → 422.

**Flow:**

1. **Snapshot** — append current `{attempt, status, denial_codes, payer_ccn, submitted_at}`
   to `submission_history` before overwriting anything.

2. **Ledger reversal** (`denied` / `appealing` only, only if `billing_ledger` feature enabled
   and `claim.remittance_id` is set) — reverse every ledger entry where
   `claim_id = claim.id AND remittance_id = claim.remittance_id`. Uses the existing
   `reverse_entry` path. Rationale: the practice is contesting the denial, so any
   CO/OA write-offs auto-posted from the denial ERA are premature and must be unwound.

3. **Reset ERA columns** — clear `remittance_id`, `insurance_paid_cents`,
   `patient_responsibility_cents`, `denial_codes`, `paid_at`. Keep `adjustments`
   (retained in `submission_history` snapshot; kept on row for reference but the remittance
   link is severed). Clearing `remittance_id` is what allows the new ERA to match —
   `_match_claim` requires `remittance_id IS NULL`.

4. **Increment attempt and set frequency code:**
   - `claim.submission_attempt += 1`
   - `clearinghouse_rejected` / `submission_failed` → `claim_frequency_code = "1"` (carrier
     never received the original; resubmit as a new original)
   - `denied` / `appealing` → `claim_frequency_code = "7"` (corrected replacement;
     builder will include `payer_claim_control_number` as the original claim reference)

5. **New PCN + idempotency key** — `generate_pcn(str(claim_id), attempt=new_attempt)` and
   `generate_claim_idempotency_key(appt_id, patient_id, insurance_id, new_attempt)`. The
   attempt suffix in the PCN ensures the new ERA matches back to this resubmission, not
   the original.

6. **Re-read current data and build payload** — same `build_claim_input` path as the
   original submission, re-loading the current appointment / patient / insurance / procedure
   rows from the DB. Staff corrects the underlying data (NPI in Settings, procedure code on
   the appointment) *before* clicking Resubmit; the endpoint picks up whatever is current.
   Pass `claim_frequency_code` and (for `"7"`) `original_claim_reference = payer_claim_control_number`
   to the builder.

7. **Builder extension** — `build_claim_input` accepts two new optional kwargs:
   `claim_frequency_code: str = "1"` and `original_claim_reference: str | None = None`.
   These set the appropriate field in the Stedi JSON payload. All other builder logic
   is unchanged.

8. **Submit + update status** — same `client.submit_dental_claim` path as the original.
   On success: `status = "submitted"`, `submitted_at = now()`. On failure:
   `status = "clearinghouse_rejected"` or `"submission_failed"` with `submission_errors`.
   Commit once.

## 5. Write-off service

**Entry point:** `write_off_claim(session, practice_id, claim_id, *, memo, user_sub)`
in `app/services/claims/service.py`.

**Pre-condition:** claim must be in `{denied, appealing}`. Raises
`ClaimSubmissionPrereqError("CLAIM_NOT_WRITABLE", ...)` → 422 otherwise.
Raises `ClaimSubmissionPrereqError("ALREADY_RESOLVED", ...)` → 422 if
`insurance_reviewed_at` is already set.

**Flow:**

1. **Compute remaining balance** — `SUM(amount_cents)` over live ledger entries
   where `claim_id = claim.id`. Positive = patient still owes; zero or negative = already
   covered by prior insurance entries.

2. **Post adjustment** — if remaining balance > 0, insert a `LedgerEntry` of type
   `adjustment` with `amount_cents = -remaining_balance`, `claim_id` linked,
   `memo = memo or "insurance denial write-off"`, `posted_by = user_sub`. Uses the
   existing ledger entry model; no new ledger function needed.

3. **Mark reviewed** — set `claim.insurance_reviewed_at = now()`. This moves the claim
   to **Done** in the 8b A/R worklist classification (row 5: "already reviewed").
   `claim.status` stays `denied` — the denial is a historical fact; the write-off is
   the financial resolution.

**Returns:** `{claim: Claim, ledger_entry: LedgerEntry | None}` — `None` when balance
was already zero (no entry posted, but `insurance_reviewed_at` is still set).

## 6. API

Both endpoints on the existing `claims` router (`app/routers/claims.py`), feature-gated
on `claims_submission`, write-role required. Schemas added to the Zod source and
regenerated via `pnpm generate`.

### `POST /api/v1/claims/{claim_id}/resubmit`
- Request body: none
- Response: `Claim` (updated row)
- `404` claim not found in practice scope
- `422 CLAIM_NOT_RESUBMITTABLE` if wrong status
- `422 MISSING_CLEARINGHOUSE` if API key unavailable
- `403` if feature disabled

### `POST /api/v1/claims/{claim_id}/write-off`
- Request body: `{ memo?: string }`
- Response: `{ claim: Claim, ledgerEntry: LedgerEntry | null }`
- `404` claim not found
- `422 CLAIM_NOT_WRITABLE` if wrong status
- `422 ALREADY_RESOLVED` if already reviewed
- `403` if feature disabled

### `GET /api/v1/claims` — extended
Add optional `patient_id` query param (one-liner filter on the existing endpoint) to
support the patient Claims tab. Scoped to `practice_id` as always.

### Schema additions
- `Claim` gains `submissionHistory` (array | null) and `claimFrequencyCode` (string)
- New `ClaimWriteOffResponse` with `claim: Claim` + `ledgerEntry: LedgerEntry | null`

## 7. CARC reason display

**`apps/web/lib/carc-codes.ts`** — static lookup covering the ~30 most common dental
denial codes. Each entry: `{ description: string, hint: string }`.

Selected entries:
| Code | Description | Hint |
|---|---|---|
| 4 | Service requires prior authorization | Obtain auth from carrier, then resubmit |
| 16 | Claim missing required information | Check submission errors for the specific field |
| 45 | Charge exceeds contracted fee schedule | Contractual adjustment — verify fee schedule |
| 96 | Non-covered charge | Verify this CDT code is covered under this plan |
| 97 | Included in payment for another procedure | Check for bundling — may need to remove duplicate |
| 167 | Not covered — patient not eligible on date of service | Verify patient eligibility for date of service |

The claim panel composes a plain-English sentence by interpolating `{carrier, CDT codes,
amount}` into the lookup entry. Example output:

> "Delta Dental denied D9330 (Crown, resin-based composite) as non-covered under this
> plan (CARC 96). Verify crown coverage before resubmitting."

Unknown codes fall back to: `"Denied — code {X} from {carrier}. See explanation from
carrier for details."`

Clearinghouse rejections use a separate `submission-error-hints.ts` map keyed on
common 277CA error patterns (NPI, DOB, payer ID) with "Fix in: Settings → Practice"
style hints.

## 8. Frontend

Three surfaces share the same two mutation hooks:
- `useResubmitClaim(claimId)` → `POST /claims/{id}/resubmit`
- `useWriteOffClaim(claimId)` → `POST /claims/{id}/write-off`

Both live in `apps/web/lib/api/claims.ts`. On success both invalidate
`claimsKeys.forAppointment(apptId)`, `claimsKeys.forPatient(patientId)`, and the
insurance A/R worklist query.

### 8a. Claim panel (extended — existing component on appointment view)

For claims in `denied | appealing | clearinghouse_rejected | submission_failed`,
add a **reason block** above the action buttons:

```
⚠ Denied by carrier
  Delta Dental denied D9330 (Crown) as non-covered (CARC 96).
  Verify crown coverage under this plan before resubmitting.

  Prior attempts: 1  (collapsed — expand to see CARC 96 on attempt 1)

  [Resubmit]  [Write off]   ← Write off only for denied / appealing
```

`submission_history` drives the "Prior attempts" row — shows attempt count and whether
the denial reason has changed between attempts.

### 8b. Insurance A/R worklist (extended — 8b page)

Problem tab rows and Appealing tab rows gain inline **Resubmit** and **Write off**
buttons alongside the existing reason display. No new tabs. Tooltip on Resubmit:
`"Correct the issue shown, then resubmit to send a new claim to the carrier."`

### 8c. Patient Claims tab (new)

`apps/web/app/(app)/patients/[patientId]/claims/page.tsx`

New tab on the patient page (alongside existing Ledger tab). Uses
`usePatientClaims(patientId)` → `GET /claims?patient_id={id}`.

Table columns: `Date | CDT codes | Carrier | Billed | Ins. paid | Status | Reason`

- Status badge reuses existing `ClaimStatus` color scheme.
- Reason column: plain-English CARC sentence (one line; tooltip for overflow). `—` for
  resolved/paid claims.
- `submission_attempt > 1` shows a small `Attempt {N}` chip.
- **Resubmit** / **Write off** buttons on eligible rows, same conditions as the claim
  panel.
- CDT codes column links to the appointment so staff can navigate to fix procedure data.

## 9. Testing

Per CLAUDE.md: new exported function or endpoint → happy path + one failure case.
Run non-integration tests independently; ask before running integration tests.

### Unit (`tests/services/`)

**`resubmit_claim`:**
- `clearinghouse_rejected` → snapshot added, `submission_attempt` incremented,
  `claim_frequency_code = "1"`, new PCN generated, claim submitted → `status = submitted`
- `denied` with prior ledger write-offs → snapshot added, write-offs reversed,
  ERA columns cleared, `claim_frequency_code = "7"`, resubmitted
- Wrong status (e.g. `paid`) → raises `CLAIM_NOT_RESUBMITTABLE`
- Re-click on already-`submitted` claim → raises `CLAIM_NOT_RESUBMITTABLE`

**`write_off_claim`:**
- Denied claim with positive balance → adjustment entry posted, `insurance_reviewed_at` set
- Denied claim with zero balance → no entry posted, `insurance_reviewed_at` still set
- Already-reviewed → raises `ALREADY_RESOLVED`
- Wrong status (e.g. `paid`) → raises `CLAIM_NOT_WRITABLE`

**CARC lookup:**
- Known code returns interpolated sentence with CDT codes and carrier
- Unknown code returns fallback string

### Integration (ask before running)

- Resubmit a denied claim that has CO write-offs → confirm reversals in ledger,
  `remittance_id` cleared on claim, new ERA can match (no hit to unmatched queue)
- Write-off → confirm `SUM(ledger_entries WHERE claim_id)` reaches zero

### Endpoint tests

- `POST /claims/{id}/resubmit`: happy path, wrong-status 422, feature-gate 403
- `POST /claims/{id}/write-off`: happy path, already-resolved 422, wrong-status 422,
  feature-gate 403
- `GET /claims?patient_id={id}`: returns only that patient's claims within practice scope;
  claims from another practice not returned

## 10. Cross-references

- `2026-06-18-module-7a-claims-submission-design.md` — builder, idempotency, PCN generation
- `2026-06-22-module-7b-era-ingest-design.md` — `_match_claim` guard (`remittance_id IS NULL`);
  `post_insurance_remittance` denial write-off behaviour (§2 above)
- `2026-06-23-module-8a-patient-ledger-design.md` — `reverse_entry`, `add_manual_adjustment`,
  insurance idempotency constraint
- `2026-06-29-module-8b-insurance-ar-design.md` — Problem / Appealing categories that surface
  the claims this spec resolves; `insurance_reviewed_at` used here for write-off resolution
- `longterm_build_plan.md` §Deferred — "Claim recovery & appeals" item; update to BUILT once shipped
