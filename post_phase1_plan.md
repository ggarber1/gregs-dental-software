# Molar — Post-Phase 1 Roadmap

Phase 1 delivers: scheduling, reminders, patient records, digital intake, and optionally eligibility verification, co-pay estimation, and claims submission.

Everything below is what turns a working MVP into a full Eaglesoft replacement and beyond.

---

## Phase 2 — Clinical Core

**Goal:** Replace the paper chart. This is the last thing keeping a practice on Eaglesoft day-to-day.

Dad explicitly said he likes paper charts because history is easy to flip through and they work when the system is down. The digital chart has to match that or it won't get used.

### 2.1 Digital Tooth Chart - Done
- Interactive tooth diagram (adult 32-tooth + primary 20-tooth)
- Per-tooth status: existing restorations, missing teeth, implants, crowns
- Colour-coded by status (existing work vs. treatment planned vs. completed today)
- History view — see the full chart state at any past visit date
- Print-to-PDF for physical backup (addresses dad's offline concern)

### 2.2 Clinical Notes - Done
- Per-visit notes tied to appointment
- Free-text + structured fields (anesthesia used, patient tolerance, complications)
- Previous visit notes visible in sidebar while writing current note
- Note templates per procedure type (extraction, crown prep, root canal)
- Chronological history view — replaces flipping through paper chart

### 2.3 Perio Charting
- Six-point probing per tooth (mesial, mid, distal × buccal/lingual)
- Bleeding on probing, recession, furcation flags
- Side-by-side comparison of current vs. previous perio chart
- Hygienist-entry workflow (different role from dentist)

### 2.4 Treatment Planning - Done
- Link planned procedures (CDT codes) to specific teeth
- Treatment plan statuses: proposed → accepted → scheduled → completed → refused
- Multi-visit plan grouping (e.g. crown requires prep + seat appointments)
- Treatment plan printout for patient to take home
- Open treatment plan tracking — who has accepted a plan but never scheduled?
- Follow-up queue for patients with unscheduled accepted treatment

### 2.5 Medical History - Done
- Structured medical history form (conditions, medications, allergies)
- Flag high-risk conditions relevant to dental treatment (blood thinners, bisphosphonates, heart conditions)
- Medical alerts prominently displayed on every patient view
- Mom noted Eaglesoft isn't storing medical history well — this is a gap to fill
- Version history — track changes over time, not just current state

### 2.6 Imaging Integration (Deep)

**Pre-requisite:** Dad has migrated off CDR DICOM (EOL Dec 2024) to a supported platform. Likely candidates: Sidexis 4 (free Dentsply upgrade for compatible Schick hardware), Dexis, or Apteryx XVWeb (cloud). Confirm before starting this section.

**Goal:** Deep integration with the imaging software — not a replacement. Imaging software owns capture and clinical tools. PMS surfaces images in context and eliminates manual patient lookup in two systems.

**Patient context bridge**
- "Open in [Imaging Software]" button on patient chart — launches imaging software with patient pre-selected
- Pass patient ID via bridge protocol (CLI arg or COM object, varies by vendor)
- Button hidden on workstations where imaging software isn't installed

**DICOM Modality Worklist (MWL)**
- Stand up a DICOM MWL server (Orthanc, open-source) in the VPC — not publicly exposed
- Populate worklist from PMS appointment data: patient name, DOB, MRN, procedure, scheduled time
- Imaging software queries MWL at appointment start — staff selects patient from list instead of re-entering demographics
- Eliminates the main source of data-entry errors in X-ray labeling

**Image surfacing in PMS chart**
- Imaging software pushes completed studies to Orthanc PACS via DICOM Storage SCU (standard feature on all major platforms)
- On receive: extract metadata (tooth, date, modality), store DICOM in `phi-documents` S3, write to `patient_images` table linked to appointment
- Render in patient chart using Cornerstone.js or OHIF Viewer (open-source, display-only — no FDA clearance needed)
- X-ray history tab: all images across all visits, filterable by tooth/date/modality
- Pre-signed S3 URLs for retrieval; images never served through app server
- Audit log every image access (PHI read)

**Note:** We are not building imaging software. Measurement tools, bone level analysis, and pathology detection stay in the dedicated imaging platform. Replacing those would require FDA 510(k) clearance and is out of scope indefinitely.

### 2.8 Family Member Linking

- `patient_relationships` table (`patient_id`, `related_patient_id`, `relationship_type`)
- Relationship types: `spouse`, `parent`, `child`, `sibling`, `guardian`, `dependent`, `other`
- Read-only section on patient chart showing linked family members with quick-nav to their charts
- Both patients must share the same `practice_id`; store both directions (A→B and B→A) for query simplicity
- Use `PHIMixin` — social graph is PHI-sensitive even without raw demographics
- **Priority note:** Confirmed low priority with dad. Front desk can achieve the same via last-name search today. Revisit after scheduling is live, or if dad explicitly requests it.

### 2.7 Offline Resilience
- Read-only mode when internet is down — staff can view today's schedule and patient charts
- Queue writes locally, sync when connection restores
- Addresses dad's concern about needing a physical fallback
- Implement as service worker cache for the web app + SQS-backed write queue

---

## Phase 3 — Full Billing Engine

**Goal:** Close the gap between the Phase 1 estimator and financially reliable co-pay calculation. Also full Eaglesoft data migration.

By this point there are months of real claims data in the system. ERA responses can be cross-referenced against what Module 5 estimated to validate and tune the algorithm.

### 3.1 Full Co-pay Calculation Engine
- Replace the Phase 1 estimator with the complete algorithm
- DHMO fixed copay lookup (carrier copay schedule per CDT code)
- Alternate benefit / downgrade handling (posterior composite → amalgam)
- Frequency limit tracking from claims history (not just from 271)
- Waiting period enforcement with waiver support
- Build and validate against real ERA data collected during Phase 1

### 3.2 Coordination of Benefits (COB)
- Secondary insurance claim generation after primary ERA arrives
- Three COB methods: Traditional, Carve-Out, Non-Duplication
- Auto-detect which method applies per carrier
- Secondary claim workflow: primary ERA received → auto-generate secondary 837D → submit
- This was explicitly deferred to manual review in Phase 1

### 3.3 Eaglesoft Data Migration Tooling
- Full patient record migration (demographics, insurance, treatment history)
- Appointment history import (last 3–5 years for recall and frequency tracking)
- Outstanding balance migration
- Validation report before commit — every row validated, rejections surfaced for manual review
- Idempotent — safe to run multiple times
- Migration dry-run mode with diff summary
- This is what enables a practice to fully cut over from Eaglesoft

### 3.4 Accounts Receivable Management
- Patient statement generation (PDF, mailed or emailed)
- Automated payment reminder sequence for outstanding balances (30/60/90 day)
- Payment plan setup (installment agreements for large balances)
- Collections flagging for accounts over 90 days

### 3.5 Clearinghouse Architecture

DentalCXchange is NOT on MassHealth's approved vendor list, and as the payer network expands this gap will recur. Design around it from the start.

- **Primary clearinghouse: Availity** — MassHealth-approved, full transaction set (837P/D, 835, 270/271, COB, Void/Replace), large national network
- **Secondary: DentalCXchange** — retained only for dental-specific payers where Availity lacks connectivity
- **MassHealth dental specifically:** Routes through DentaQuest (MassHealth's dental program) — not a general clearinghouse
- **Payer routing is config-driven:** a `payer_id → clearinghouse` mapping, not hardcoded logic. Adding a new route = one config change
- **ClearinghouseClient interface:** all clearinghouse integrations behind a common interface so adding a third clearinghouse (e.g. Waystar for a specific state Medicaid) requires no architectural changes
- This is the foundation for reliable billing across all state Medicaid programs as the platform expands

Note: the routing abstraction should be designed during Phase 1 claims submission work even if only one clearinghouse is wired up at that point.

### 3.6 Quickbooks Integration (Real-Time)
- Replace the Phase 1 CSV export with a proper Quickbooks Online API integration
- Real-time sync of payments, write-offs, adjustments
- Map dental ledger entries to Quickbooks chart of accounts
- Reconciliation report

### 3.7 Patient Financing
- CareCredit integration — apply and get approval in-app
- Cherry / Sunbit as alternatives
- Financing option surfaced when patient responsibility exceeds a configurable threshold (e.g. > $500)
- 42% of CareCredit cardholders say they would have postponed treatment without financing — this directly improves case acceptance

---

## Phase 4 — AI & Automation

**Goal:** The features that make this product genuinely differentiated and create switching costs through embedded workflow value.

### 4.1 Ambient Clinical Notes (AI)
- Dentist speaks naturally during or after a procedure
- AI transcribes and structures into a clinical note (CDT codes, tooth numbers, surfaces, clinical observations)
- Staff reviews and confirms — not fully autonomous
- Dentists spend 2–3 hours/day on documentation. Whichever PMS solves this natively wins that cohort permanently.
- Use Whisper for transcription + Claude for structuring into chart format
- HIPAA: audio is processed and immediately discarded, never stored

### 4.2 Predictive No-Show Model
- Train on appointment history: who cancels, who no-shows, time of day, day of week, procedure type, prior no-show history, confirmation status
- Risk score per appointment: low / medium / high
- High-risk appointments: trigger extra confirmation outreach, surface for manual call by staff
- Waiting list auto-fill: when a cancellation comes in, automatically text the top waiting list patients for that time slot

### 4.3 AI Insurance Verification Enhancement
- Cross-reference 271 eligibility response against historical ERA data for the same carrier
- Learn which carriers consistently return stale deductible data and flag accordingly
- Improve co-pay estimate confidence scores over time
- Addresses the staleness problem identified in Module 5 research

### 4.4 Recall Automation
- Automated recall campaign: patients due for 6-month cleaning get a text/email 4 weeks out
- Smart scheduling: suggest specific open slots based on patient's historical preferred times
- Reactivation campaign: patients not seen in 12+ months
- Recall = 9% increase in hygiene revenue + 6% increase in overall production (market research stat)
- Dad mentioned this — he doesn't want to be pushy but knows recalls matter

### 4.5 Treatment Plan Follow-Up
- Automated follow-up sequence for patients with accepted but unscheduled treatment plans
- Configurable: how many touches, how far apart, what channel (SMS/email)
- Dad explicitly doesn't like being pushy — make the cadence conservative and configurable
- Urgent treatment (e.g. infection, crown with decay) vs. elective (whitening) — different urgency tiers

### 4.6 Practice Analytics Dashboard
- Daily production vs. goal
- Case acceptance rate (treatment plans proposed vs. accepted vs. completed)
- No-show and cancellation rate trends
- Insurance collection rate by carrier (which carriers are slow/problematic)
- Hygiene recare rate
- New patient acquisition by referral source
- These are the KPIs 73% of practices currently don't track — make them visible by default

### 4.7 Practice Benchmarking
- Anonymous aggregate benchmarks across all practices on the platform
- "Your recare rate is 68% — similar practices average 74%"
- Benchmarks by: practice size, specialty, geography, insurance mix
- This is the network effect moat — more practices = better benchmarks = more value for everyone
- 67% of practices currently have no benchmarking data (market research stat)

---

## Phase 5 — Platform Expansion

**Goal:** Grow beyond solo practices and add features that expand TAM.

### 5.1 Native Mobile App (iOS/Android)
- Check and manage schedule from anywhere
- Push notifications for same-day cancellations
- Patient check-in via QR code scan
- Key differentiator — no major dental PMS has a fully functional native mobile app
- Build with React Native to reuse web components

### 5.2 Patient Portal
- Patient-facing web app (separate from practice app)
- View upcoming appointments, past visit history
- View and accept treatment plans
- Pay outstanding balances online
- Download X-rays and records
- Update medical history and insurance info before visit
- Reduces front desk intake time for returning patients

### 5.3 Online Booking
- Public-facing booking page (bookable by procedure type, provider, time)
- Integrates with schedule — no double-booking
- New patient intake form embedded in booking flow
- Insurance capture during booking
- Dad's practice is phone-only now, but 60% of patients prefer online booking (market research stat)

### 5.4 HIPAA Compliance Dashboard
- Real-time view of audit log activity
- Access anomaly detection (unusual PHI access patterns)
- BAA tracking — all vendors documented
- Risk assessment checklist
- 73% of legacy Eaglesoft practices fail HIPAA risk assessments — this is a sales motion
- No PMS currently has this built in

### 5.5 Multi-Location / DSO Features
- Centralized patient records across locations
- Per-location scheduling and operatory management
- Consolidated reporting across locations
- Role-based access: corporate admin, location admin, provider, front desk
- Bulk insurance credentialing
- Provider can work at multiple locations
- Required to sell into group practices and emerging DSOs

### 5.6 Lab Case Management
- Track lab cases tied to appointments (crown impressions, denture fabrication)
- Lab case status: sent → received → seated
- Notify provider when lab case arrives
- Currently no standard solution — practices use sticky notes or spreadsheets

### 5.7 E-Prescribing
- Send prescriptions electronically to pharmacies
- EPCS (Electronic Prescribing for Controlled Substances) compliance
- Prescription history in patient chart
- Drug interaction check against patient medications

---

## Sequencing Rationale

| Phase | Unlocks | Dependency |
|-------|---------|------------|
| 1 | Practice can run day-to-day without Eaglesoft for new patients | — |
| 2 | Practice can fully cut over (paper chart replaced) | Phase 1 complete |
| 3 | Full billing accuracy + Eaglesoft migration = complete cutover | 6+ months of Phase 1 claims data |
| 4 | Differentiation and retention — hard to leave once AI workflows are embedded | Phase 2 + 3 data |
| 5 | Expand TAM beyond solo practices | Phase 4 stability |

Phase 3 specifically requires real Phase 1 claims data before the full co-pay engine can be validated. Don't build it in the abstract — build it against ground truth.
