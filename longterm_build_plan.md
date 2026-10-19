# Molar — Long-Term Build Plan

## North Star

Replace Eaglesoft as the daily operating system for small-to-mid dental practices. Win on: clinical workflow (paper chart replacement), AI-native features (ambient notes, no-show prediction), and a modern UX that doesn't require a training manual.

---

## Phase Status Summary

| Phase | Theme | Status |
|---|---|---|
| 1 | Core Practice Operations | 🔄 Mostly done |
| 2 | Clinical Core (Paper Chart Replacement) | 🔄 Mostly done |
| 3 | Billing & Insurance Depth | 🔄 In progress |
| 4 | AI & Automation | 🔜 Planned |
| 5 | Platform Expansion | 🔜 Future |

---

## Phase 1 — Core Practice Operations 🔄

Everything a practice needs to run day-to-day before seeing a patient.

- ✅ Patient records (CRUD, search, demographics)
- ✅ Scheduling (calendar, operatories, appointment types, providers)
- ✅ Appointment reminders (SMS + email via Twilio/SES, configurable hours)
- 🔄 Insurance — plan management ✅; eligibility checks (271) manual/sync ✅ (PR #52); async pre-appointment auto-verify + queue/badge UI + staging Checkpoint 5 pending
- ✅ Intake forms (digital forms with patient-facing token link)
- ✅ Medical history (versioned, with alerts bar for blood thinners/bisphosphonates/etc.)
- 🔲 Practice Signup & Onboarding Flow — self-signup (email + practice name), email verification, guided first-run wizard (NPI, billing address, provider(s), Stedi API key entry, Stripe payment method); current auth is functional but not customer-ready
- 🔲 SaaS Subscription Billing (Stripe) — payment method capture at signup, recurring invoice via Stripe Billing, hosted customer portal (update card, view invoices, cancel); prerequisite before any practice is charged

---

## Phase 2 — Clinical Core 🔄

Replace the paper chart. The last thing keeping a practice on Eaglesoft.

- ✅ Medical History (versioned, alert inference)
- ✅ Clinical Notes (per-visit, templates, sign-and-lock)
- ✅ Digital Tooth Chart (SVG, condition tracking, history mode)
- ✅ Treatment Planning (multi-item plans, open-plan queue)
- ✅ Perio Charting (6-point probing, comparison view, keyboard entry) — PRs #40, #45; still needs dad's review
- 🔲 Offline Resilience Phase 1 (PWA app shell, read-only offline mode)
- ✅ Practice Fee Schedule (CDT code catalog per practice) — delivered as **Module 3.6** in Phase 3 (full CDT catalog seeded + per-practice fee entry in Settings)
- 🔲 Imaging Software Integration (local bridge agent launches imaging software with correct patient pre-selected — plan: `imaging_bridge_plan.md`)

**Gating concern:** Dad needs to review the clinical note form structure before ambient notes (4.1) can be built on top of it. Schedule this review.

Post Review

- Dictating for treatment plan
  - Treatment plan is showed on tooth chart
- Treatment plan should have tooth number procedure needed to be done (from list of procedures) and some notes
- Treatment plan should also have level of urgency, which one should be worked on first
- Tooth chart is very simple right now
  - look at example ones
  - There are 3d ones these days
  - I guess there are different levels to a tooth the dentists care about?
  - Also would be cool if dentist didnt have to click on a tooth to get all of the information
- Notes should just be a single textbox that user can have templates for
  

---

## Phase 3 — Billing & Insurance Depth 🔄

Close the revenue cycle loop so the practice doesn't need a separate billing tool.
Decomposed into modules — see `docs/superpowers/specs/phase3-build-order.md` for the
dependency graph and detailed sequencing.

- ✅ **Module 3.5 — Per-Appointment Procedures** (procedure capture on appointments; prerequisite for 6 + 7)
- ✅ **Module 3.6 — Practice Fee Schedule** (per-practice fee per CDT code; auto-fills procedures, feeds co-pay estimation)
- ✅ **Module 5.2–5.4 — Eligibility Verification** — sync slice done (271 parse + benefit-summary card + verify button). Async pre-appointment batch + verification-queue page + appointment-slot badge deferred to **Staging Checkpoint 5**.
- ✅ **Module 6 — Co-pay Calculation** (PRs #53–#56: contracted fees, per-CDT coinsurance parser, full CDT catalog, engine + service + endpoints + estimate card). This is the "insurance estimation (coverage % per plan per CDT code)" line. DHMO / alternate-benefit downgrade / secondary-COB deferred per spec §Deferred.
- ✅ **Module 7 — Claims Submission (837D) + ERA Processing (835)** — split into **7a** and **7b**, both built. **7a (claims submission, PR #57 merged):** `DentalClaimInput` → Stedi Dental Claims JSON endpoint (Stedi generates the X12; synchronous 277CA), sync submit endpoint, claims table, claim panel + worklist. Spec: `specs/2026-06-18-module-7a-claims-submission-design.md`. **7b (835 ERA ingest + auto-post, PR #58):** Stedi `Poll Transactions` → `835 ERA Report` (JSON, no raw X12) → parse → match-by-PCN onto the `claims` row (paid/patient-resp/adjustments/denial), sync `POST /era/poll` + remittances worklist + unmatched-review queue; `era_remittances`/`unmatched_era_payments` tables (migration 0033). Spec: `specs/2026-06-22-module-7b-era-ingest-design.md`. **Both live paths (claim submit + ERA pull) are unverified until a full-access Stedi key at Staging Checkpoint 5** — see "Pending Manual Verification" below. (requires 3.5; 6 optional)
- 🔄 **Module 8 — Billing & Payments** — split into **8a** and **8b+**. **8a (patient ledger, built):** append-only `ledger_entries` table (migration 0034) + ledger service computing running balance and posting entries — auto-posted charges on appointment checkout, insurance payment + non-PR contractual write-off from ERA, record-only patient payments (Stripe card processing deferred), manual adjustments, and reversals; feature-gated `billing_ledger` router (GET ledger / POST payments / POST adjustments / POST reverse); patient-chart Ledger tab; all hooks (checkout + ERA poll) soft-gated on `billing_ledger`. Spec: `specs/2026-06-23-module-8a-patient-ledger-design.md`. **8b+ (🔲 remainder):** patient-facing statements (email/print), QuickBooks export, full guarantor/family accounts, and Stripe card processing. (requires 7)
  - **8b first slice — Insurance A/R Worklist (aging + underpayment) — ✅ BUILT, PR #61** (spec: `specs/2026-06-29-module-8b-insurance-ar-design.md`; plan: `plans/2026-06-29-module-8b-insurance-ar.md`). Read-mostly worklist over `claims` + the Module 6 estimate: **awaiting-carrier** (aged, chase oldest first), **underpaid** (auto-detected when insurance pays >5% below the Module 6 estimate → Write off), **problem** (denied/rejected/failed with Stedi reason), and appealing (folded into problem — no actions while appeal is live). Plus a birds-eye carrier × age-bucket summary. **Claim recovery & appeals — ✅ BUILT, PR #62** (resubmission + write-off + patient Claims tab + A/R worklist actions). 275 claim attachments for formal appeals remain deferred (demand-driven).
  - **8b second slice — ERA Reconciliation + Practice A/R Dashboard — ✅ BUILT, PR #64.** Migration 0039 (`claims.reconciliation_confirmed_at`, `practices.automation_config`). Reconciliation service classifies ERA-settled claims as overpaid / within-tolerance / matched / no-estimate; confirm-mode requires staff sign-off before closing. `GET /reports/reconciliation/claims` + confirm endpoint + `GET /reports/ar-summary` aggregation. Billing dashboard (`/billing`) with insurance A/R, patient A/R, and claims-needing-attention cards. Unified 6-tab claims hub (All / Awaiting / Underpaid / Problem / Reconciled) replacing the old `/insurance-ar` page. CARC denial-code lookup maps common codes to plain English; Stedi submission-error strings surfaced for clearinghouse rejections. Resubmit is two-step (amber confirmation prompting staff to fix the underlying issue first). Sonner toasts on all claim mutations (success + API error message on failure). Write-off on underpaid claims posts a negative `adjustment` ledger entry for the shortfall. **8b+ remainder:** see third slice below.

  - **8b third slice — Patient Aging + Statements — ✅ BUILT.** Migration 0040 (`patient_statements`: append-only delivery record + point-in-time aging snapshot keyed like ARBuckets). `GET /reports/patient-aging` (gated on `billing_ledger`) lists every live patient owing ≥ $5 (default; `min_balance_cents` query param), positive-amount entries bucketed 0–30 / 31–60 / 61–90 / 90+ by `posted_at`, payments/negative adjustments as one credits total (no FIFO attribution), reversal pairs excluded (shared `unreversed_entry_where` in `ledger/balance.py`, also used by posting); sorts by balance / oldest charge / last statement with a deterministic tiebreaker. Statements are always manual, never batch: `POST /patients/{id}/statements` (`email` → Jinja2 → WeasyPrint PDF rendered off-loop, attached via SES `SendRawEmail` with the practice name as display name; `download` → records only) returns JSON; bytes come from `GET …/statements/{id}/pdf` and `GET …/statements/preview` because IdempotencyMiddleware text-decodes mutation bodies. Nothing is written when SES fails (502). `email_opt_out` is intentionally ignored (transactional). New `/billing/patient-aging` page (sort, show-all, per-row Send email / Download PDF, totals footer) + Preview / Email / Download buttons and a collapsible statement history with per-row PDF re-download on the patient Ledger tab. Runtime image now installs Pango/HarfBuzz for WeasyPrint; local dev needs `brew install pango`. Spec: `specs/2026-08-05-patient-aging-statements-design.md`; plan: `plans/2026-09-08-patient-aging-statements.md`. **8b+ remainder:** overpayment/refund handling, guarantor/family billing, QuickBooks export, Stripe card processing, batch statement sends, payment URL on statements (needs patient portal).
- ✅ **Claim attachments (275) — BUILT, PR #63** — S3-backed file uploads on appointments; Stedi 275 electronic transmission bundled with 837D; perio chart auto-narrative for D4xxx procedures; payer fallback (attachmentControlNumber reference + manual portal prompt for unsupported payers). Live Stedi 275 path unverified until Staging Checkpoint 5 (no sandbox mode; see "Pending Manual Verification" below). UI not yet clicked through (see "Needs UI / Manual Testing"). Deferred: solicited attachments (277 RFA → 275), prior authorization (278), secondary/COB claim attachments. Spec: `specs/2026-07-06-claim-attachments-design.md`. (requires 7a)

**Open checkout/payment workflow questions — discuss with dad (gates 8b UX):**

8a posts charges when an appointment is marked `completed` and records payments in the patient's Ledger tab. Before building the 8b checkout UX, confirm how the real front-desk flow works:

- **Pay-on-the-spot timing:** Patients sometimes pay immediately at checkout, so the **total owed must be computed and visible at the moment of completion** — not just the gross fee. Need patient-responsibility (gross − insurance estimate, from Module 6 co-pay) ready to collect at checkout. Confirm: do they always collect at checkout, or sometimes bill later?
- **Who enters procedures, and when?** Dentist, assistant, or front desk — and during the visit or at checkout? This determines whether the fee total is actually "ready" when the patient is standing at the desk.
- **Edit-appointment modal as the checkout hub?** Should adding/editing procedures, seeing the running total, AND recording "patient paid $X" all happen inside the edit-appointment modal at checkout — rather than completing the appointment and then navigating to the patient's Ledger tab separately? (Current 8a flow is two steps: complete → Ledger tab. Dad's workflow may want it in one place.)

**Make procedure entry easier — where does "add procedure" live?** Procedures are per-appointment (`appointment_procedures.appointment_id`), so the add surface should be wherever an appointment is already in context. Proposed direction (depends on the "who enters procedures" answer above):

- **Two entry points for two moments:** (1) **day-of/checkout** → the edit-appointment modal from the schedule (front desk is already there when the patient finishes); (2) **patient-centric review/correction** → a new **Appointments tab** on the patient page (drill into a visit → add/edit its procedures, see completion status + the charge it generated).
- **Do NOT put an Add button on the Procedures (history) tab** — that tab is flat cross-visit history with no appointment context, so adding there forces an awkward "which appointment?" picker. Keep it as the read-only record.
- **Watch overlap:** a new Appointments tab (grouped by visit) is a close cousin of the existing Procedures tab (flat history) — decide whether it complements or subsumes it; avoid two tabs that feel like the same data sliced differently.
- **Caveat:** if the *dentist* enters procedures chairside (not front desk), the primary surface may be the clinical-note/tooth-chart flow instead — so this rides on the "who enters procedures, and when" question above.

**Clearinghouse call allowance & overage billing:**

The $249/mo plan includes 250 clearinghouse calls/month (claims + eligibility combined). At Stedi PAYG rates ($0.30/call), the 250-call bundle costs ~$75/mo and is already priced into the margin model. See `research/16_cost_and_scaling_model.md`.

Concrete overage plan (not yet built):
- **Track usage:** `clearinghouse_usage` table — one row per call (practice_id, call_type, timestamp). Monthly count queryable at billing time and surfaced in the Practice Settings UI so staff can self-monitor.
- **Alert at 200 calls:** email the practice owner ("you've used 200 of your 250 included calls this month — overage is billed at $0.50/call").
- **Overage billing via Stripe Metered Billing:** at month end, report `max(0, calls - 250)` units to a Stripe metered usage item on the subscription; Stripe adds the overage line to the next invoice automatically. Rate: $0.50/call (covers our $0.30 Stedi cost + $0.20 margin).
- **No throttle:** don't cut off clinical workflows mid-month — bill the overage instead. A practice submitting 300 claims is a good problem; throttling would cost the relationship.
- **Dependency:** Stripe subscription billing (Phase 1 above) must be live first.

---

## Phase 4 — AI & Automation

The features that create switching costs through embedded workflow value. Sequenced by data dependency — rule-based features ship first; ML features require data accumulation.

### 4.1 Ambient Clinical Notes
- Post-procedure dictation → structured clinical note draft
- Dentist reviews and confirms — not fully autonomous
- **Stack:** Whisper (self-hosted EC2, transcription) + Claude Haiku via AWS Bedrock (structured extraction via tool use, prompt caching)
- **HIPAA:** Audio in-memory only, never persisted; covered under AWS BAA (Bedrock is HIPAA-eligible) — no separate Anthropic BAA needed. Revisit only if Bedrock's model/feature lag becomes a quality bottleneck.
- **Plan:** `ambient_notes_plan.md`
- **Status:** 🔲 Blocked — waiting on dad's clinical note form review (see Phase 2 gate)

VERIFY THIS WORKS!!!!!

### 4.2A No-Show Risk Scoring (Rule-Based) — Ship First
- Risk score per appointment: low / medium / high
- Badge on schedule view appointment card
- High-risk → extra SMS reminder queued automatically (reuses existing reminder pipeline)
- **Algorithm:** Point-based rules (prior no-show rate, unconfirmed, day-of-week, time-of-day, lead time) — no training data required, ships immediately
- **Plan:** `no_show_risk_plan.md`
- **Status:** ✅ Done

VERIFY THIS WORKS!!!!!

### 4.2B No-Show Risk Scoring (ML Model) — Long-Term, Data-Dependent
- Replace rule-based scorer with a trained gradient-boosted model (scikit-learn / XGBoost)
- **Minimum viable dataset:** ~5,000–10,000 completed/no-show appointments with full feature history
- **Realistic timeline:** 6–12 months after 4.2A ships and practices are actively using the system
- **Training pipeline:** Monthly retrain job (Lambda + S3 for model artifact), model serialized to file, loaded at scoring time — no SageMaker needed at this scale
- **Features to add beyond rules:** provider-patient relationship history, insurance type, weather (day-of), seasonal patterns, time-since-last-visit
- **Transition:** Model is swapped behind the same `compute_risk_score` interface — frontend and reminder logic unchanged
- **Gate:** Do not start until we have verified training data volume and the rule-based model has been live long enough to validate its buckets

### 4.3 Waiting List Auto-Fill
- Staff-managed waitlist per practice (patient, preferred time window; appointment type is not required to match)
- When a cancellation comes in → auto-text the top waitlist patient for that slot; if they decline or don't respond within the offer window, move to the next candidate sequentially
- **Lead time gate:** Skip auto-fill for slots where the appointment starts within 2 hours of the cancellation — not enough time for patients to respond and travel
- **Race condition:** Slot acceptance is an atomic compare-and-swap on the waitlist entry status — only the first ACCEPT wins; concurrent acceptances receive a "slot already taken" reply and are re-offered the next available slot
- **Sequential, not simultaneous:** Only one patient holds an active offer at a time; this avoids overbooking and is fairer to patients lower in the queue
- **Hardcoded defaults (all configurable long-term — see 4.3.1):** offer expiry = 2 hrs, lead time gate = 2 hrs
- Future: patient self-service enrollment from scheduling or patient portal flow
- **Dependency:** None — can be built independently of 4.2

#### 4.3.1 Practice Automation Configuration Panel
All automation parameters that are currently hardcoded defaults should eventually be surfaced as per-practice settings in a dedicated configuration UI. This is not a Phase 4 blocker — ship with sensible defaults first — but the data model should store them as JSONB fields on the practice so they can be tuned without a code deploy.

Parameters to make configurable (priority order):
- **Waitlist offer expiry** (default 2 hrs) — how long a patient has to respond before the offer passes to the next person
- **Waitlist lead time gate** (default 2 hrs) — minimum time between cancellation and appointment start before auto-fill is attempted
- **Reminder hours** (already configurable as `reminder_hours` JSONB) — keep as-is, good pattern to follow for the above
- **Recall campaign cadence** (4.5) — weeks before due date to send first touch, number of touches, spacing between touches
- **Treatment plan follow-up** (4.6) — number of touches, days between touches, urgency tier thresholds
- **No-show risk thresholds** (4.2A) — the bucket boundaries that separate low/medium/high risk (currently hardcoded in scorer)

**Implementation pattern:** Store all of these under `practice.automation_config` (JSONB, default `{}`). Each feature reads its value from that dict with a fallback to a module-level constant. When the config UI is built, it reads/writes this dict. No migration needed per new parameter — just add keys to the dict.

### 4.4 AI Insurance Verification Enhancement
- Cross-reference 271 eligibility response against historical ERA data for the same carrier
- Flag carriers that consistently return stale deductible data
- Improve co-pay estimate confidence over time
- **Dependency:** Phase 3 ERA parsing must be live and accumulating data first

### 4.5 Recall Automation
- Automated recall campaign: patients due for 6-month cleaning get SMS/email 4 weeks out
- Reactivation campaign: patients not seen in 12+ months
- **Dad's input:** Make cadence conservative and configurable — he doesn't want to be pushy

### 4.6 Treatment Plan Follow-Up Automation
- Automated follow-up for patients with accepted but unscheduled treatment plans
- Configurable: number of touches, spacing, channel (SMS/email)
- Urgency tiering: infection/decay (urgent) vs. cosmetic (low cadence)
- **Dependency:** Treatment planning (Phase 2) must be live with real plan data

### 4.7 Practice Analytics Dashboard
- Daily production vs. goal
- Case acceptance rate (plans proposed → accepted → completed)
- No-show and cancellation rate trends
- Insurance collection rate by carrier
- Hygiene recare rate
- New patient acquisition by referral source
- **Dependency:** Billing (Phase 3) data required for production and collection metrics

### 4.8 Practice Benchmarking
- Anonymous aggregate benchmarks across all practices on the platform
- "Your recare rate is 68% — similar practices average 74%"
- Benchmarks by: practice size, specialty, geography, insurance mix
- **Dependency:** Meaningful multi-practice data (10+ active practices minimum)
- **Note:** This is the network effect moat — value compounds with more practices

---

## Phase 5 — Platform Expansion

Grow beyond solo practices; expand TAM.

### 5.1 Native Mobile App (iOS/Android)
- Check and manage schedule from anywhere
- Push notifications for same-day cancellations
- Patient check-in via QR code scan
- **Stack:** React Native (reuse web components)

### 5.2 Patient Portal
- Patient-facing web app (separate subdomain)
- View appointments, treatment plans, past visit summaries
- Pay outstanding balances online
- Update medical history and insurance before visit
- Download records and X-rays

### 5.3 Online Booking
- Public-facing booking page (by procedure type, provider, time)
- Integrates with live schedule — no double-booking

### 5.4 Multi-Practice & DSO Support
- **Organization layer** above practice: one account (owner) owns N practices; a new `organizations` table with a FK from `practices.organization_id`
- **Billing rollup:** single Stripe subscription per org, priced per practice seat; overage tracked and billed at the org level (one invoice, one card on file)
- **Auth scoping:** new `org_admin` role that can see all practices in the org; existing staff roles remain scoped to a single practice
- **Cross-practice analytics** (4.7/4.8 metrics at the org level) — production, collection, no-show rates rolled up across all locations
- **Shared providers:** a provider can be assigned to multiple practices within the same org (relevant for associate dentists who float between locations)
- **Note:** `practice_id` is already on every table so the data model supports it; the UI, auth, and billing rollup are what need to be built. No schema migration needed to enable the feature — just add the `organizations` table and the FK.
- **Dependency:** Validate single-practice billing and auth at scale before tackling multi-practice complexity. Also a prerequisite for 4.8 Benchmarking at meaningful scale.

---

## Data Accumulation Timeline

Some features are gated on having enough production data. Track this explicitly.

| Feature | Data Needed | Realistic Start |
|---|---|---|
| 4.2A Rule-based risk scoring | None | Now |
| 4.2B ML risk model | 5,000–10,000 labeled appointments | 6–12 months post 4.2A launch |
| 4.4 AI insurance enhancement | 12+ months of ERA data per carrier | 12+ months post Phase 3 launch |
| 4.8 Benchmarking | 10+ active practices | Phase 5 |

---

## Infrastructure Scaling Checkpoints

| Milestone | Infrastructure change |
|---|---|
| First paying practice | Current stack sufficient (ECS Fargate, RDS t3.medium, Lambda workers) |
| 10 practices | Review RDS instance size; add read replica for analytics queries |
| 50 practices | Evaluate RDS → Aurora; dedicated analytics DB or read replica to isolate reporting queries |
| 100 practices | Multi-region consideration; dedicated data warehouse (Redshift/BigQuery) for 4.7/4.8 |
| ML model training | S3 for training data export, monthly Lambda retrain job — no SageMaker needed until 100+ practices |

---

## Needs UI / Manual Testing

Features built and merged but not yet clicked through. Do these before onboarding a real practice.

### Claim attachments (PR #63)

- **Upload flow:** open an appointment modal in edit mode → AttachmentPanel visible → click "Add files" → select a JPEG → confirm type defaults to "X-ray", filename and size display, "Uploading…" state appears then resolves
- **Re-upload same file:** after uploading, select the same file again — confirm the `onChange` fires (file input resets after each selection)
- **Perio narrative row:** upload a perio narrative (auto-generated or manual) → confirm no delete button appears on that row
- **PDF and TIFF acceptance:** confirm the file picker accepts `.pdf` and `.tif`/`.tiff`; confirm `.txt` is rejected at the picker (accept attribute)
- **Delete:** upload a file → click delete → confirm row disappears; verify DB soft-delete (`deleted_at` set) and S3 object gone
- **ClaimPanel result — electronic:** submit a claim for an appointment with an attached JPEG → confirm the "N file(s) sent electronically" line appears in ClaimPanel
- **ClaimPanel result — manual fallback:** simulate or trigger the payer-unsupported path → confirm the amber "Upload manually" warning with file list appears
- **Perio auto-narrative on submit:** create an appointment with a D4341 procedure and a PerioChart → submit claim → confirm a `perio_narrative` attachment row appears in AttachmentPanel after submission

### ERA Reconciliation + A/R Dashboard (PR #64)

- **Billing dashboard cards:** `/billing` shows Insurance A/R, Claims Needing Attention, and Patient A/R cards; clicking each navigates to the correct claims tab
- **Tab navigation:** All / Awaiting / Underpaid / Problem / Reconciled tabs all render and filter correctly
- **Underpaid write-off:** find an underpaid claim → click Write off → amber confirmation prompt appears → confirm → toast fires → claim leaves worklist → patient Ledger tab shows negative adjustment entry
- **Resubmit two-step:** click Resubmit → amber prompt appears with "fix the issue first" message → Cancel dismisses it → Confirm sends (toast appears)
- **Appealing claims in Problem tab:** verify "pending appeal" reason text appears and no action buttons are visible
- **CARC denial reason display:** requires a claim with real `denial_codes` from an ERA — the demo seed doesn't populate these, so CARC descriptions only appear after a real denial comes back from a carrier. Verify at Staging Checkpoint 5.
- **Clearinghouse rejection reason:** same — requires a claim where Stedi populated `submission_errors`. Appears after a real submission rejection.
- **Toast on error:** manually trigger a failure (e.g., write off an already-reviewed claim) and confirm the error message from the API appears in the toast rather than failing silently
- **Reconciled tab (confirm mode):** requires `practices.automation_config = {"era_reconciliation_mode": "confirm"}` — set this on a test practice and verify pending/confirmed split and Confirm button

### Patient Aging + Statements

- **Aging page:** `/billing` → Patient A/R tile → table renders; sort dropdown and "Show balances under $5.00" refetch (table stays in place); totals footer sums the visible rows
- **Download PDF:** saves `statement-<date>.pdf`; open it and confirm letterhead, patient address block, aging summary, itemized table, and running balance match the Ledger tab
- **Send email:** requires SES configured (`SES_FROM_ADDRESS`) — verify at staging; locally the send is logged and the statement is still recorded with `delivered_at` set. Sender shows as "<Practice name> <from-address>"
- **Ledger tab:** Preview opens a PDF in a new tab (falls back to a download if the popup is blocked); buttons disabled with tooltips for no balance / no email; statement history expands, lists each action, and each row's PDF link re-downloads without creating a new row
- **Write-off then late ERA payment (credit balance):** patient disappears from the aging worklist (balance ≤ 0); refund workflow remains unbuilt (8b+)

### Claim recovery & appeals (PR #62)

- **Write-off end-to-end:** find a `denied` claim with no `insurance_reviewed_at` → click Write off on the A/R worklist → verify claim leaves the worklist → open patient Ledger tab → verify negative adjustment entry appears
- **Written-off claim hides Resubmit:** after writing off, confirm the Resubmit button is gone in both ClaimPanel and the patient Claims tab
- **Resubmit visibility by status:** Resubmit button present for `clearinghouse_rejected`, `submission_failed`, `denied`, `appealing`; absent for `paid`, `submitted`, `acknowledged`
- **Patient Claims tab:** navigate to a patient with claims — verify the tab renders with correct statuses, billed amounts, and ins. paid amounts
- **Denial reason display:** on a claim with CARC denial codes from an ERA, open ClaimPanel — verify plain-English reason text appears instead of raw codes

Note: the Resubmit network call itself (Stedi 837D submission) is already tracked under Staging Checkpoint 5 below — can't verify without a full-access Stedi key.

---

## Pending Manual Verification — S3 PHI Document Bucket

`app/core/s3.py` (`put_object`, `get_object_bytes`, `delete_object`) was introduced for
claim attachments and is unit-tested with mocked boto3, but has **never been exercised
against a real bucket**. This is independent of the Stedi key — just needs the staging
S3 bucket and ECS task IAM role to exist.

**To do (when staging infra is live):**
1. Confirm the PHI documents bucket name is set in SSM / env (`S3_BUCKET_PHI_DOCUMENTS`).
2. Upload a test file via the attachment endpoint (POST `/appointments/{id}/attachments`)
   and verify the S3 object lands under the expected key (`attachments/{practice_id}/{uuid}/{filename}`).
3. Fetch via GET `/appointments/{id}/attachments` — confirm the ORM row is returned.
4. Delete via DELETE endpoint — confirm `deleted_at` is set in the DB and the S3 object
   is gone (check via `aws s3 ls` or the AWS console).
5. Confirm SSE-S3 (`AES256`) server-side encryption is set on the uploaded object
   (`aws s3api head-object --bucket <bucket> --key <key>` → `ServerSideEncryption: AES256`).

---

## Pending Manual Verification — Eligibility (Staging Checkpoint 5)

The Module 5.2–5.4 eligibility *sync slice* is built and merged (PR #52), and the
live Stedi sandbox call is confirmed **locally** via
`apps/api/scripts/stedi_eligibility_smoke.py` (a real Cigna mock 271 parses
correctly). What is **not** yet proven — and can't be tested off-AWS — is the
same call from inside the ECS **private subnet**: NAT egress to Stedi, fetching
the clearinghouse key from SSM, and the task IAM/KMS permissions. Do this when
convenient; it's not a blocker for further dev.

**Prerequisites / steps (staging):**
1. **Set the Stedi test key in SSM** — currently still the Terraform placeholder
   (`/dental/staging/clearinghouse/api_key`, verified placeholder 2026-06-14):
   ```
   source apps/api/.stedi-smoke.env && aws ssm put-parameter \
     --name /dental/staging/clearinghouse/api_key \
     --type SecureString --overwrite \
     --value "$STEDI_TEST_API_KEY" --region us-east-1
   ```
2. **Bring staging up** — `make staging-up` in `infra/terraform` (starts the
   stoppable NAT instance and scales the api service up from 0).
3. **Seed a practice** with `features.eligibility_verification = true`,
   `billing_npi`, `clearinghouse_submitter_id`, and
   `clearinghouse_api_key_ssm_path = /dental/staging/clearinghouse/api_key`.
4. **Seed a test patient + insurance** matching the Stedi dental mock exactly:
   `insurance_plan.payer_id = 62308`, patient (relationship `self`) =
   **Jaguar Dent**, DOB **1996-05-05**, member **U3141592653**.
5. In the app, open that patient → **Eligibility card → "Verify now."**

**Expected result** (same as the local smoke test): status `active`, deductible
$50.00, annual max $2,000, plan `TOTAL CIGNA DPPO`. Coinsurance fields blank —
the per-CDT-code coinsurance model is deferred to Module 6.

**What it proves (the part untestable locally):** the ECS api task reaches
`healthcare.us.stedi.com` via the NAT instance; the task role reads the key from
SSM (via the SSM VPC interface endpoint) and decrypts via KMS; no 500s.

**Failure triage:** request timeout → NAT instance not running / route missing.
A `failed` check with "Clearinghouse API key unavailable" → SSM param still
placeholder, or IAM/KMS permission gap. `not_supported`/401 → wrong key. It's a
**test-mode** key (free, mock requests only); production uses
`/dental/production/clearinghouse/api_key` with the real key.

---

## Pending Manual Verification — Claims Submission + ERA (needs a full-access Stedi key)

Module 7a (claims submission, PR #57) is built, but the **live 837D submission path is
unverified** because **Stedi's dental-claims submission endpoint is not available to
test-mode API keys** (unlike eligibility, there is *no* mock/sandbox mode for claim
submission). A live smoke run on 2026-06-19 confirmed the endpoint URL
(`/2024-04-01/dental-claims/submission`) and the `Authorization: Key <key>` header, then
hit `403 access_denied "not available in Test Mode."` So the JSON payload field names in
`StediClaimsClient.to_stedi_payload()` are **aligned to Stedi's documented schema but never
validated against an accepted claim.**

**To do (when a full-access / production Stedi key is available — not now):**
1. Put the full-access key in `apps/api/.stedi-smoke.env` as `STEDI_TEST_API_KEY` (it can
   still use `usageIndicator: "T"` so accepted claims are NOT forwarded to a real payer).
2. Run `python apps/api/scripts/stedi_claim_smoke.py` and iterate on any field-name errors
   Stedi reports until `accepted: True`.
3. Fix the two known best-effort gaps surfaced during doc-alignment: `receiver.organizationName`
   currently sends the payer **id** (needs a payer-name source); a non-self subscriber's
   `gender`/`address` fall back to the patient's/unknown (we only store the insured's name + DOB).
4. Bundle with **Staging Checkpoint 5** (first live outbound Stedi call from the deployed ECS
   private subnet), same as the eligibility live-call verification above.

This is a **prerequisite before any real practice submits live claims through Molar**, but
it was **not a dev blocker** for Module 7b or anything else.

**Write-off + subsequent ERA payment (prod edge case, not testable locally).** If a staff member writes off an underpaid claim and then an ERA posts a full payment (e.g., appeal succeeds, or carrier corrects an error), the ledger will have a charge + insurance_payment + adjustment (write-off) + a second insurance_payment. This creates a credit balance that needs to be noticed and refunded to the patient. No automated alert exists for this yet — it will show up as a negative patient balance in the (unbuilt) patient aging report. Track this when patient statements are built (8b+).

**Module 8b resubmission (PR #62 + PR #64) also depends on this.** Resubmit sends a corrected claim with frequency code `"7"` (denied/appealing) or `"1"` (clearinghouse-rejected/failed) and passes the prior `payer_claim_control_number` as `original_claim_reference`. Neither path can be exercised without a full-access key. Verify at Checkpoint 5 alongside the initial claim submission smoke test.

**Module 7b (ERA pull) is blocked the same way.** The Stedi `Poll Transactions` / `835 ERA
Report` endpoints can't be exercised in test mode (no claims submit → no ERAs; test ERAs
additionally require sending the claim to the **Stedi Test Payer**). So `parse_stedi_era`,
the poll-item 835 detection (`stedi._is_835`), and the JSON nesting
(`parser._iter_claim_payment_objs`, `detailInfo[].paymentInfo[]`) + the report URL are
**aligned to docs but unverified against a real response** — each is isolated to a single
function for easy correction. At **Staging Checkpoint 5**, with the full-access key, run
`python apps/api/scripts/stedi_era_smoke.py` to verify the live ERA shape (and confirm PCN
match-back end-to-end against a claim submitted in step 2 above).

**Module 8c (Claim Attachments / 275) is blocked the same way.** The claim attachment
endpoint (`POST https://claims.us.stedi.com/2025-03-07/claim-attachments/file`) and the
presigned S3 `uploadUrl` it returns have **no test/sandbox mode** — a smoke run with a
test-mode key will hit the same `403 access_denied` as the 837D endpoint. The full live
path (S3 upload → `attachmentId` → `reportInformations` in the 837D payload → accepted
claim that the payer links to the attachment) is unverifiable until a full-access key is
available. The code is unit-tested with mocked httpx. **Action items:**
1. Ask Stedi whether they can provide synthetic attachment test data or a test payer that
   supports 275 attachments — similar to the mock enrollment/eligibility test data they
   supply for 270/271 (`apps/api/scripts/stedi_eligibility_smoke.py`). File a support
   ticket or contact the Stedi partnership team.
2. At Staging Checkpoint 5 (full-access key), upload a real file (PDF X-ray), confirm
   `attachmentId` is returned and the presigned PUT succeeds, then submit a D2392 claim
   that references it and confirm the payer links the attachment to the claim.
3. Verify the payer-unsupported fallback path (control-number ref in `reportInformations`
   instead of `attachmentId`) with a payer known to reject 275 electronic attachments.

---

## Deferred Follow-Ups & Backlog

**This is the canonical roll-up of everything we've consciously deferred.** The
phase sections above are the forward roadmap; this section captures the granular
follow-ups that get spun off from individual module specs (and would otherwise be
lost inside them). **Detail-of-record stays in each spec's own "Deferred" section** —
the links below point there. When a module brainstorm defers something, add a line
here.

### A. Module follow-ups (from shipped / in-progress modules)

| Item | Source spec | Trigger / when |
|---|---|---|
| **🔴 Silent session refresh — users are logged out every hour** — the web app stores the Cognito access token in a cookie once at login and never refreshes it; access tokens live 1h, so the next request after that 401s and `api-client.ts` redirects to `/login`, losing any in-progress modal (seen on staging 2026-10-16, exactly 1h after login). Use Amplify `fetchAuthSession()` (30-day refresh token) to refresh before expiry, retry once on 401 before redirecting, and return to the original page after re-login. ~½ day incl. tests. | Staging click-through, 2026-10-16 | **High — before dad or staff use the app** |
| ✅ **FIXED (`fix/ledger-post-completion-procedures`)** — **Procedures added after completion are never charged** — `reconcile_charges_for_appointment` (idempotent: one live charge per live procedure, reverses deleted/changed ones) only runs from `PATCH /appointments/{id}` when status changes to `completed`. Adding, editing, or deleting a procedure on an already-completed appointment never posts to the ledger — the patient is silently never billed (reproduced on staging 2026-10-16: completed at 15:17:51, procedure added 15:18:22, ledger empty). Call reconcile from the appointment-procedures create/update/delete routes when the appointment is `completed` and `billing_ledger` is on. Tests: add after completion → charge; fee edit → old reversed + new posted; delete → reversed; not completed → nothing posted. ~1–2h. | Staging click-through, 2026-10-16 | **High — silent revenue loss** |
| **Procedure edits after a claim is submitted don't reach the claim** — since procedure create/edit/delete on a completed appointment now re-syncs ledger charges, the ledger can diverge from an already-submitted 837D (new/changed/removed lines). Detect it (procedure changed after `claims.submitted_at`) and prompt staff to Resubmit as a corrected claim (frequency code 7, existing 9a flow) instead of leaving claim and ledger out of step. | Fix for post-completion charges, 2026-10-19 | Before practices submit live claims |
| **🔴 S3 bucket names never reach ECS — attachments (and ERA/exports) fail** — the API task definition in `modules/ecs` sets only `ENV`/`PORT` + secrets, so `S3_BUCKET_PHI_DOCUMENTS` / `S3_BUCKET_ERA_FILES` / `S3_BUCKET_EXPORTS` fall back to the `dental-*-local` defaults in `core/config.py`. Staging PDF attachment upload → `NoSuchBucket` → 500 (2026-10-16); production would break identically. Real buckets (`dental-*-${env}`) and the task role's S3 grants already exist. Fix: add the three names to the API container `environment` in `modules/ecs`; and fail fast at startup when `ENV` is staging/production but any bucket is still a `-local` default (CLAUDE.md "crash on missing config"). Also audit other settings with dev defaults (e.g. SES sender). ~1h + a targeted apply of `module.ecs`. | Staging click-through, 2026-10-16 | **High — blocks attachments & ERA storage** |
| ✅ **FIXED (`fix/procedure-cdt-link`)** — **Procedures saved without `cdt_code_id` — co-pay engine can't match fees or categories** — `ProceduresSection.selectCdtCode` fills code/name/fee but `handleAdd` never sends `cdtCodeId`, and the create route doesn't resolve `procedureCode` → catalog row, so every UI-created procedure has `cdt_code_id = NULL`. The engine then skips contracted-fee lookup (keyed on `cdt_code_id`) and treats every line as category `other` — e.g. D0120 on Cigna PPO estimated 50/50 instead of preventive coverage (staging 2026-10-19, appt `20c49bb9…`). Fix: send `cdtCodeId` on select (clear it if the code text is edited); server-side, resolve an exact active catalog match when only `procedureCode` is given; backfill existing rows by exact code match. Tests: select → linked; typed exact code → linked; unknown code → stays free text; copay uses category + contracted fee. ~1–2h. | Staging click-through, 2026-10-19 | **High — makes Module 6 estimates wrong** |
| **Billing identity settings + specific claim errors** — there is no Settings UI for billing NPI, tax ID (EIN, stored encrypted), taxonomy code, or clearinghouse submitter ID / API key; they can only be set in the DB, so a practice can't make itself claim-ready. Add a "Billing & clearinghouse" Settings section (validate NPI Luhn, 9-digit EIN, taxonomy; never echo the full EIN back). Separately, the claim panel shows a generic "check NPI, tax ID, taxonomy, and clearinghouse…" message although the API returns a specific code (`MISSING_TAX_ID`, `MISSING_NPI`, `CLAIM_INVALID` + `errors[]`) — show the specific problem with a link to the settings field. A rejected-before-send claim also creates no claim row, so nothing appears under Problem; fine, but the message must say what to fix. Overlaps the onboarding wizard (Phase 1); this is the minimal piece needed first. ~½–1 day. | Staging click-through, 2026-10-16 | Before any practice submits claims |
| **"Copy link" for sent intake forms** — staff can't see or copy an intake form's URL; it only reaches the patient by SMS. If Twilio fails, the number is wrong, or A2P isn't approved, the form is undeliverable, and there's no way to open it on a front-desk tablet. Add a copy-link button per sent form on the patient page (the send response already returns `formUrl`). | Staging click-through, 2026-10-16 | Before onboarding the first practice (A2P approval may lag) |
| **Prefill the intake form from the patient record, behind a DOB check** — the form starts empty even when staff already entered name/DOB/phone/email/address. Return a `prefill` block from the token lookup, but only after the patient enters a DOB matching the record (the link is a bearer token; a misdelivered or forwarded SMS must not expose PHI). Never prefill SSN. No migration; ~1 day incl. API + web tests (prefill only after DOB match, no cross-practice exposure). | Staging click-through, 2026-10-16 | With or after the copy-link button; before onboarding returning patients |
| **"No insurance on file" indicator — patient chart + scheduling** — a patient with no active `patient_insurance` row looks identical to an insured one. Show a badge in `MedicalAlertsBar` on the chart, in the appointment modal's patient search results, and on calendar tiles / day sheet. API: add `hasInsurance` to patient list/detail and appointment list responses via an `EXISTS` subquery (no N+1). Open question for dad: distinguish intentional **self-pay** from **insurance not yet entered**? (would need a `self_pay` flag). ~1 day incl. tests. | Staging click-through, 2026-10-16 | Before dad's Checkpoint 3 schedule review |
| **Co-pay engine owns procedure estimates (replace manual Ins./Pt. est. inputs)** — today Insurance est. and Pt. est. on each appointment procedure are plain manual inputs (the 3.5 spec called for a computed patient portion), while the Module 6 Co-pay estimate card in the same modal computes them and writes Ins./Pt. est. + `estimateSource = eligibility` back onto the rows only when staff press Calculate. Target flow: (1) pick CDT → fee from fee schedule (exists); (2) whenever procedures change and a **fresh** verified eligibility check exists, run the engine automatically (DB-only — no Stedi call) and show Ins. est. / Pt. est. inline per row with a source badge, e.g. "Eligibility · Cigna · verified Oct 16"; (3) fallbacks shown inline: no insurance → Pt. est. = full fee ("self-pay", ties to the no-insurance indicator); no/stale check → inline "Verify insurance" button; failed check or secondary coverage → manual entry, labeled; (4) staff can override a row → marked Manual, not overwritten by recalcs, "reset to calculated" available; (5) totals strip: Fee · Insurance est. · **Patient due now**. `estimateSource` becomes system-set, not a dropdown; the separate Co-pay card shrinks to a details view (deductible remaining, annual max used, per-line math); `copay_calculations` snapshot records what was quoted. **Freshness rule (engine bug today):** `_latest_verified_check` uses the latest verified check regardless of age — re-verify when older than ~30 days or from a prior plan year, show check date on every estimate, and lean on the planned 3-days-before auto-check for routine refreshes (~1 Stedi call/patient/visit, within the 250-call allowance). **Prior EOB** fallback needs per-procedure payment history (`claim_service_lines`, deferred in 7a) — later. Ask dad: collect at checkout or bill after insurance pays? (decides whether "Patient due now" is the headline). | Staging click-through, 2026-10-16 | With the 8b checkout UX discussion (who enters procedures, pay-on-the-spot totals) |
| **Co-pay engine N+1: batch the contracted-fee lookup** — `services/copay/service.py` issues one `contracted_fee_schedule` query per procedure inside the loop. Load all rows for `(practice_id, payer_id, cdt_code_id IN …)` in one query and map by `cdt_code_id`. Small change; existing copay tests cover behavior. | Code read, 2026-10-16 | Next time the copay service is touched |
| **CDT code search by code *or* name, in appointments and treatment plans** — treatment plan procedure rows take free-text Code / Procedure name, while appointment procedures have a CDT typeahead — but only on the Code input; typing in Procedure name doesn't search (the `/cdt-codes` API already matches description `ILIKE %term%`, so typing "exam" in the Code box works today, which isn't discoverable). The typeahead UI is inline in `ProceduresSection.tsx` (only `useCdtCodeSearch` is shared). Extract a `CdtCodePicker` — one search box (type a code or a name) replacing the separate Code / Name inputs → fills code, name, and fee from the fee schedule; free-text fallback for off-catalog codes), use it in both places, and add picker tests. No schema change (plan items store strings). ~2–3h. Prepares the "complete plan item → procedure" link (`treatment_plan_item_id` row above). | Staging click-through, 2026-10-16 | Before dad's clinical review |
| Async eligibility batch (EventBridge→SQS→ECS worker) | `specs/...eligibility-verification-design.md` §9 | **Staging Checkpoint 5** (untestable locally; first live call from ECS) |
| Appointment-slot eligibility badge | eligibility §9 | Bundle with Checkpoint 5 |
| Verification-queue page (today's patients + status) | eligibility §9 | Bundle with Checkpoint 5 |
| DentalXChange adapter (behind the provider interface) | eligibility §9 | Demand-driven (only if prod needs a dental fallback; Stedi is primary) |
| MassHealth (CKMA1) frequency refdata + `payer_id_overrides` | eligibility §9 + Module 6 §1 | When a MassHealth practice onboards |
| Per-CDT-code coinsurance model | eligibility §9 item 7 | ✅ **Now folded into Module 6** (`specs/2026-06-16-module-6-copay-calculation-design.md`) |
| DHMO (capitation) co-pay + per-plan copay schedule | Module 6 §1 | Deferred Module 6 slice (needs a new data source) |
| Alternate-benefit / downgrade (composite→amalgam) | Module 6 §1 | Deferred Module 6 slice (needs per-carrier downgrade maps) |
| Secondary-insurance COB auto-calculation | Module 6 §1 + eligibility §9 | See §B Phase 3 "Coordination of Benefits" below |
| Plan-level (vs. payer-level) contracted-fee granularity | Module 6 §4.3 | Refinement once payer-level proves insufficient |
| Extract deductible-waiver flags from the 271 | Module 5 parser / Module 6 | Parser currently leaves `deductible_waived_*` at defaults (preventive=true, diagnostic/ortho=false) and doesn't detect waivers from the 271. Surfaced by the live Stedi smoke run: a Cigna DPPO applies the deductible to diagnostic (over-estimates patient). Errs conservative; low urgency. |
| `treatment_plan_item_id` nullable FK ("complete plan item → procedure") | Module 3.5 design | When the plan→procedure link feature is built |
| Fee-schedule CSV bulk import | Module 3.6 design | When a practice has hundreds of codes to load by hand |
| Module 7b — 835 ERA ingest + auto-post payments | Module 7a spec §11 | ✅ **BUILT — PR #58** (`specs/2026-06-22-module-7b-era-ingest-design.md`) |
| 7b follow-ups: `GET /era/remittances/{id}` detail endpoint; persisted poll cursor (vs re-listing the 30-day window); manual re-match of an unmatched payment to a chosen claim | Module 7b spec §10 | Detail endpoint + re-match demand-driven; persisted cursor rides with the async worker |
| Async claim-submission worker (SQS/ECS) | Module 7a spec §11 | If submission volume demands it; provable only on AWS (near Staging Checkpoint 5) |
| DentalXChange production client + raw-X12 `X12Builder` | Module 7a spec §11 | When a prod practice needs a non-Stedi route |
| 277CA webhook + 276/277 status-polling worker | Module 7a spec §11 | With the async worker; 7b ERA is the authoritative paid/denied source |
| MassHealth/Medicaid claims (`payer_type`, `claim_filing_code=MA`, DentaQuest enrollment) | Module 7a spec §11 | When a MassHealth practice onboards |
| Secondary / COB claims (837D COB loops) | Module 7a spec §11 | Now unblocked (7b ERA provides primary EOB data); demand-driven when a practice needs secondary billing |
| Multiple rendering providers per appointment; queryable `claim_service_lines` | Module 7a spec §11 | Demand-driven |
| **Contact Stedi for 275 / 837D test data** — no sandbox mode exists for claim submission or attachments (unlike eligibility 270/271). Ask Stedi support / partnership if they can supply a test payer + synthetic claim data so we can smoke-test the full attachment upload → `attachmentId` → 837D → accepted-claim round-trip before going live. Bundle with Staging Checkpoint 5 prep. | "Pending Manual Verification" section above | Before onboarding any practice that submits claims with attachments |
| Solicited attachments (277 RFA → 275 response) — payer requests docs after claim is submitted; provider responds with a 275 referencing the 277 RFA | `specs/2026-07-06-claim-attachments-design.md` §out-of-scope | Demand-driven; Stedi API only supports unsolicited 275 today |
| Prior authorization (278) — pre-approval request + response before performing high-value procedures (implants, bone grafts, osseous surgery); auth number flows onto the 837D | `specs/2026-07-06-claim-attachments-design.md` §out-of-scope | When a practice doing implants/perio surgery needs pre-auth workflow with major carriers |
| Secondary / COB claim attachments (primary EOB as 275 attachment on the secondary 837D) | `specs/2026-07-06-claim-attachments-design.md` §out-of-scope | Depends on secondary COB claims being built first (see row above) |
| ✅ **Claim recovery & appeals — BUILT, PR #62** (`specs/2026-06-01-pricing-model-design.md`; plan: `plans/2026-06-30-claim-recovery-appeals.md`). Resubmission (freq code 1 for clearinghouse-rejected/failed; freq code 7 corrected-claim for denied/appealing with prior attempt snapshotted in `submission_history` JSONB); optional ledger reversal of ERA entries on resubmission; write-off (adjustment entry zeroing remaining balance + sets `insurance_reviewed_at`); `POST /claims/{id}/resubmit` + `POST /claims/{id}/write-off` endpoints; patient Claims tab; Resubmit/Write-off buttons in ClaimPanel and insurance A/R worklist Problem/Appealing rows; CARC code lookup + submission-error hints for plain-English denial display. **Resolved discrepancy:** CO/OA write-offs from the ERA are posted independently of insurance payments (two separate if-blocks in `era/ledger/posting.py`) — a denied claim that posted write-offs gets those reversed on resubmission when `billing_ledger` is enabled. **Remaining:** 275 claim attachments for formal appeal documentation (demand-driven, low priority). | Module 8b design (2026-06-29) | ✅ Built |
| **Module 8b sibling reports.** (a) ✅ **Reconciliation worklist + A/R dashboard — BUILT, PR #64.** (b) **Patient aging + statements** — patient-grouped A/R from the Module 8a ledger → email/print statements (the "patient didn't pay at checkout, bill them" path). (c) **Overpayment/refund** — ERA overpayments are surfaced in the Reconciled tab but refund workflows (request check from carrier, credit patient account) are not yet built. | Module 8b design (2026-06-29) | Patient aging/statements next |
| **Observability story (NOT built — flagged 2026-06-29).** No real monitoring/alerting yet. Highest priority: **Stedi health** — failure/error-rate spike alerts across all call types, a distinct **auth-failure** alert (dead/expired key), cost/volume anomaly (retry storms), and claim **rejection-rate** spikes. Plus revenue-cycle SLOs (claims aged past N days, ERA unmatched-queue growth, eligibility failure rate); app/infra basics (API 5xx + p50/p95/p99 latency, DB pool/slow-query/migration-failure, worker queue depth + dead-letter); and **HIPAA** PHI-access audit logging + auth-failure alerting. Open stack decision: CloudWatch alarms+logs vs Datadog/Sentry; SNS→email/Slack/PagerDuty sink; request/trace IDs threaded through Stedi calls. Deserves its own spec. | Greg, 2026-06-29 (Module 8b session); ties to `research/16_cost_and_scaling_model.md` + AWS BAA | Before onboarding the first real practice (HIPAA audit + Stedi alerting); revisit each Stedi-touching module |
| **Stedi call-cost efficiency (cross-cutting)** — Stedi API calls (eligibility 270/271, claim submission, ERA transaction polling/report fetch) are a **material per-call cost** to us. Minimize them everywhere: (a) ERA poll uses the **Poll Transactions cursor (`pageToken`/`nextPageToken`)**, never a re-`List` of a window, and dedups GET-report calls on `transactionId`; (b) prefer **webhooks (free push)** over polling once the async path exists; (c) cache/short-circuit redundant eligibility re-checks; (d) batch where the API allows. Add a cost/efficiency check to any new Stedi integration. | Module 7b brainstorm (2026-06-22) + `research/16_cost_and_scaling_model.md` | **Now** for 7b's poll design; revisit each Stedi-touching module |

### B. Larger future features not yet broken into a spec

These were captured in the older `post_phase1_plan.md` (now superseded — see note
below) and are folded here so they aren't lost. They become their own spec +
implementation plan when their phase comes up.

- **Phase 3 (billing):** Eaglesoft data-migration tooling (the real cutover enabler —
  patient/insurance/treatment-history/balance import, dry-run + validation report);
  Coordination of Benefits (Traditional / Carve-Out / Non-Duplication, auto-detect per
  carrier); AR management beyond statements/aging (payment plans, 30/60/90 collections
  flagging); QuickBooks **real-time** API sync (upgrade from the planned CSV export);
  patient financing (CareCredit / Cherry / Sunbit, surfaced above a configurable
  responsibility threshold).
- **Clearinghouse routing abstraction:** a config-driven `payer_id → clearinghouse`
  map behind a common `ClearinghouseClient` interface, so adding a route (e.g.
  MassHealth dental via **DentaQuest**, or a state Medicaid via another vendor) is a
  config change, not an architectural one. **Note:** the current primary is **Stedi**
  (see Open Decisions); `post_phase1_plan.md`'s "Availity primary" framing is stale.
- **Phase 2 leftovers:** deep imaging integration (DICOM MWL + PACS surfacing — full
  detail in `post_phase1_plan.md` §2.6 and `imaging_bridge_plan.md`); family-member
  linking (low priority, confirmed with dad).
- **Phase 5 expansion:** HIPAA compliance dashboard; multi-location / DSO features
  (also tracked under Open Decisions); lab-case management; e-prescribing (EPCS).

> **Roadmap consolidation:** `longterm_build_plan.md` (this file) is the single
> canonical roadmap + backlog. `post_phase1_plan.md` is **superseded** and kept only
> as a detailed archive; its unique items have been folded into §B above. Do not add
> new planning there.

---

## Open Decisions

- **Phase 3 scope:** Which billing features are table stakes vs. nice-to-have? ERA + ledger + statements are probably the minimum before dropping Eaglesoft entirely for billing.
- **Clearinghouse:** Decided — Stedi PAYG (837D dental confirmed, no per-provider fees, transparent per-call pricing). See `research/17_clearinghouse_comparison.md`. Open sub-question: overage policy above the 250-call monthly allowance (absorb, throttle, or surcharge).
- **Multi-location practices:** Scoped as Phase 5.4. `practice_id` is on every table so the data model supports it; the UI, auth, and billing rollup are what need to be built.
- **HIPAA BAA with Anthropic:** Must be in place before ambient notes (4.1) goes to production. Start the paperwork during Phase 2 so it doesn't block 4.1.
