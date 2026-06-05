# Molar — Long-Term Build Plan

## North Star

Replace Eaglesoft as the daily operating system for small-to-mid dental practices. Win on: clinical workflow (paper chart replacement), AI-native features (ambient notes, no-show prediction), and a modern UX that doesn't require a training manual.

---

## Phase Status Summary

| Phase | Theme | Status |
|---|---|---|
| 1 | Core Practice Operations | 🔄 Mostly done |
| 2 | Clinical Core (Paper Chart Replacement) | 🔄 Mostly done |
| 3 | Billing & Insurance Depth | 🔜 Next |
| 4 | AI & Automation | 🔜 Planned |
| 5 | Platform Expansion | 🔜 Future |

---

## Phase 1 — Core Practice Operations 🔄

Everything a practice needs to run day-to-day before seeing a patient.

- ✅ Patient records (CRUD, search, demographics)
- ✅ Scheduling (calendar, operatories, appointment types, providers)
- ✅ Appointment reminders (SMS + email via Twilio/SES, configurable hours)
- 🔲 Insurance (eligibility checks via 271/272, plan management)
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
- 🔲 Practice Fee Schedule (CDT code catalog per practice — blocked on practice providing their procedure list)
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

## Phase 3 — Billing & Insurance Depth

Close the revenue cycle loop so the practice doesn't need a separate billing tool.

- ERA parsing (835 electronic remittance, auto-post payments)
- Claim submission (837P generation, clearinghouse integration)
- Patient ledger (charges, payments, adjustments, running balance)
- Statements (patient-facing billing statements via email/print)
- Insurance aging report (outstanding claims by carrier + age bucket)
- Practice fee schedule → insurance estimation (coverage % per plan per CDT code)

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

### 4.2A No-Show Risk Scoring (Rule-Based) — Ship First
- Risk score per appointment: low / medium / high
- Badge on schedule view appointment card
- High-risk → extra SMS reminder queued automatically (reuses existing reminder pipeline)
- **Algorithm:** Point-based rules (prior no-show rate, unconfirmed, day-of-week, time-of-day, lead time) — no training data required, ships immediately
- **Plan:** `no_show_risk_plan.md`
- **Status:** ✅ Done

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

**Original notes:**
- Patient-facing web app (separate subdomain)
- View appointments, treatment plans, past visit summaries
- Pay outstanding balances online
- Update medical history and insurance before visit
- Download records and X-rays

**Updated plan:**
- Patient-facing web app (separate subdomain)
- Security baseline (required before launch):
  - Dedicated patient auth path and role claims (no staff-role token reuse)
  - Least-privilege API scope: patients can only read/write their own records
  - Full audit trail for every portal read/write touching PHI
  - Strict PHI-safe logging and error handling (no PHI in logs/errors)
- Portal MVP (ship first):
  - View upcoming appointments and appointment details
  - View active treatment plans and completed visit summaries
  - Update medical history and insurance before visit
  - Download records (CCD/PDF exports) and intake copies
- Portal Billing Extension (after Phase 3 billing APIs are stable):
  - View outstanding balances and statement history
  - Pay balances online (hosted payment page + webhook reconciliation)
  - Save payment receipts in patient portal history
- Deferred from this phase:
  - X-ray download/viewing (depends on imaging integration workstream)
  - Patient self-booking (covered in 5.3 Online Booking)
- Suggested delivery sequence:
  - 5.2A Auth + patient profile linkage + portal shell
  - 5.2B Read-only portal (appointments, treatment plans, visit summaries)
  - 5.2C Update flows (medical history + insurance updates with staff review queue)
  - 5.2D Billing/payments + receipts

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

## Open Decisions

- **Phase 3 scope:** Which billing features are table stakes vs. nice-to-have? ERA + ledger + statements are probably the minimum before dropping Eaglesoft entirely for billing.
- **Clearinghouse:** Which clearinghouse for claim submission? (Availity, Office Ally, etc.) — affects Phase 3 timeline significantly.
- **Multi-location practices:** Not scoped yet. `practice_id` is on every table, so the data model supports it, but the UI and billing rollup logic do not.
- **HIPAA BAA with Anthropic:** Must be in place before ambient notes (4.1) goes to production. Start the paperwork during Phase 2 so it doesn't block 4.1.
