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

---

## Phase 2 — Clinical Core 🔄

Replace the paper chart. The last thing keeping a practice on Eaglesoft.

- ✅ Medical History (versioned, alert inference)
- ✅ Clinical Notes (per-visit, templates, sign-and-lock)
- ✅ Digital Tooth Chart (SVG, condition tracking, history mode)
- ✅ Treatment Planning (multi-item plans, open-plan queue)
- 🔲 Perio Charting (6-point probing, comparison view, keyboard entry): Gonna merge but needs review
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
- 🔲 **Module 8 — Billing & Payments** — patient ledger (charges, payments, adjustments, running balance); patient-facing statements (email/print); insurance aging report (outstanding claims by carrier + age bucket); QuickBooks export. (requires 7)

**Clearinghouse call allowance:** The $249/mo plan includes 250 clearinghouse calls/month (claims + eligibility combined). Track monthly usage per practice in the DB so we can identify practices approaching or exceeding the limit. Overage handling TBD — options are absorb the cost, throttle, or add a per-call surcharge above 250. At Stedi PAYG rates ($0.30/call), the 250-call bundle costs ~$75/mo and is already priced into the margin model. See `research/16_cost_and_scaling_model.md`.

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

**Module 7b (ERA pull) is blocked the same way.** The Stedi `Poll Transactions` / `835 ERA
Report` endpoints can't be exercised in test mode (no claims submit → no ERAs; test ERAs
additionally require sending the claim to the **Stedi Test Payer**). So `parse_stedi_era`,
the poll-item 835 detection (`stedi._is_835`), and the JSON nesting
(`parser._iter_claim_payment_objs`, `detailInfo[].paymentInfo[]`) + the report URL are
**aligned to docs but unverified against a real response** — each is isolated to a single
function for easy correction. At **Staging Checkpoint 5**, with the full-access key, run
`python apps/api/scripts/stedi_era_smoke.py` to verify the live ERA shape (and confirm PCN
match-back end-to-end against a claim submitted in step 2 above).

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
| Multiple rendering providers per appointment; queryable `claim_service_lines`; claim attachments (275) | Module 7a spec §11 | Demand-driven |
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
- **Multi-location practices:** Not scoped yet. `practice_id` is on every table, so the data model supports it, but the UI and billing rollup logic do not.
- **HIPAA BAA with Anthropic:** Must be in place before ambient notes (4.1) goes to production. Start the paperwork during Phase 2 so it doesn't block 4.1.
