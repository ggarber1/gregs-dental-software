# Molar — Phase 2 Build Plan: Clinical Core

## Goal

Replace the paper chart. This is the last thing keeping a practice on Eaglesoft day-to-day.

Dad explicitly said he likes paper charts because history is easy to flip through and they work when the system is down. The digital chart has to match that or it won't get used.

---

## Build Order

**2.5 Medical History → 2.2 Clinical Notes → 2.1 Tooth Chart → 2.4 Treatment Planning → 2.3 Perio Charting → 2.7 Offline Resilience (Phase 1 of offline plan only — rest deferred)**

---

## Module 2.5: Medical History — Done

Structured medical history with version tracking. Replaces Eaglesoft's weak medical history support (mom flagged this explicitly as a gap).

### What was built

**DB:** `medical_history_versions` table — insert-only version log per patient. Each save creates a new row; no updates, no deletes. Active version identified by `is_current = TRUE`.

**API:**
- `GET /api/v1/patients/{id}/medical-history` — returns current version
- `POST /api/v1/patients/{id}/medical-history` — creates new version (old becomes non-current)
- `GET /api/v1/patients/{id}/medical-history/history` — version list for the history drawer

**Frontend:**
- `MedicalHistoryCard` — editable card on patient chart showing conditions, medications, allergies
- `MedicalHistoryModal` — full edit form (conditions, medications, allergies, free-text notes)
- `MedicalHistoryHistoryDrawer` — version history timeline, click any version to see its snapshot
- `MedicalAlertsBar` — auto-computed flags (blood thinners, bisphosphonates, heart conditions, diabetes, pacemaker) displayed prominently on every patient view; flags inferred from medication/condition names via keyword match, plus explicit client-side overrides

**Flag inference keywords:**
- Blood thinners: warfarin, coumadin, xarelto, eliquis, heparin
- Bisphosphonates: bisphosphonate, fosamax, boniva, prolia, actonel
- Heart conditions: heart, cardiac, arrhythmia, afib, murmur
- Diabetes: diabetes, diabetic, insulin, metformin
- Pacemaker: pacemaker, icd, defibrillator

---

## Module 2.2: Clinical Notes - Done

Per-visit notes tied to appointments. Replaces the paper chart narrative.

### Why this is next

Dad's primary paper chart use case is reading back what happened at the last visit while treating the patient. Clinical notes directly solve this.

### DB Schema

```
clinical_notes
  id                    UUID PK
  practice_id           UUID NOT NULL FK → practices(id)
  patient_id            UUID NOT NULL FK → patients(id)
  appointment_id        UUID UNIQUE FK → appointments(id)  -- one note per appointment
  provider_id           UUID NOT NULL FK → providers(id)
  visit_date            DATE NOT NULL
  chief_complaint       TEXT
  anesthesia            TEXT                                -- e.g. 'Lidocaine 2% 1:100k, 1.7ml'
  patient_tolerance     TEXT CHECK (patient_tolerance IN ('excellent', 'good', 'fair', 'poor'))
  complications         TEXT
  treatment_rendered    TEXT NOT NULL
  next_visit_plan       TEXT
  notes                 TEXT                                -- free-form catch-all
  template_type         TEXT CHECK (template_type IN ('exam', 'prophy', 'extraction', 'crown_prep', 'crown_seat', 'root_canal', 'filling', 'srp', 'other'))
  is_signed             BOOLEAN NOT NULL DEFAULT FALSE
  signed_at             TIMESTAMPTZ
  signed_by_provider_id UUID FK → providers(id)
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
  deleted_at            TIMESTAMPTZ
```

- Uses `PHIMixin` — contains clinical PHI
- Indexes: `(patient_id, visit_date DESC)`, `(appointment_id)`, `(practice_id, visit_date DESC)`
- `appointment_id` is UNIQUE — one note per appointment; nullable for notes not tied to a specific appointment slot

### API

- `GET /api/v1/patients/{id}/clinical-notes` — paginated list, sorted by `visit_date DESC`; query params: `limit`, `cursor` (ISO date cursor for stability under concurrent writes), optional `appointment_id` filter
- `POST /api/v1/patients/{id}/clinical-notes` — create note; requires `treatment_rendered`; `appointment_id` checked for ownership (must belong to same practice and patient)
- `GET /api/v1/patients/{id}/clinical-notes/{noteId}` — detail
- `PATCH /api/v1/patients/{id}/clinical-notes/{noteId}` — edit; blocked once `is_signed = TRUE`
- `POST /api/v1/patients/{id}/clinical-notes/{noteId}/sign` — sign the note; sets `is_signed`, `signed_at`, `signed_by_provider_id`; no further edits allowed after signing
- Audit log on every read and write (PHI)

### Templates

Pre-filled field sets keyed by `template_type`. Implemented as frontend-side JSON constants (no DB table needed — content is static). On selecting a template, the form pre-fills `chief_complaint`, `anesthesia`, and `treatment_rendered` placeholder text that the provider edits.

Templates to ship:
- `exam` — D0120/D0150 exam with perio screening note
- `prophy` — D1110 adult prophy
- `extraction` — D7140/D7210 extraction
- `crown_prep` — D2710 crown preparation
- `crown_seat` — crown delivery
- `root_canal` — D3310–D3330 RCT
- `filling` — D2391 composite
- `srp` — D4341/D4342 scaling and root planing
- `other` — blank

### Frontend

- `ClinicalNoteCard` — compact read-only card in patient chart showing most recent note (date, provider, treatment summary, 2-line preview of `treatment_rendered`)
- `ClinicalNoteList` — scrollable list of all notes for the patient; click to expand full note; previous notes visible in sidebar while writing current (side-by-side layout on wide screens)
- `ClinicalNoteEditor` — full write form:
  - Template picker (dropdown or pill buttons at top)
  - All structured fields (anesthesia, patient tolerance, complications)
  - Rich text or plain textarea for `treatment_rendered` and `notes`
  - Sign button — one-time action with confirmation; locked fields turn read-only after signing
- Accessible from appointment detail and from patient chart "Notes" tab
- On appointment detail: "Add Note" button pre-fills `appointment_id`, `provider_id` (from appointment), `visit_date`

### Tests

- [ ] Unit: sign blocks edit; second sign attempt returns 409
- [ ] Unit: `appointment_id` belonging to a different patient is rejected
- [ ] Integration: create note → list → detail → sign → edit returns 409
- [ ] Integration: pagination cursor — 25 notes, page size 10, cursor navigates correctly
- [ ] Auth: provider from Practice B cannot read or write notes for Practice A's patient
- [ ] Template constants: snapshot test on all 9 template objects (ensures they're not accidentally deleted)

### Checklist

- [ ] `0017_clinical_notes.py` Alembic migration — creates `clinical_notes`, indexes, constraint
- [ ] `app/models/clinical_note.py` — SQLAlchemy model with `PHIMixin`
- [ ] `app/routers/clinical_notes.py` — all endpoints, audit logging
- [ ] `packages/shared-types` — `ClinicalNote`, `CreateClinicalNote`, `SignClinicalNote` Zod schemas
- [ ] `apps/web/lib/api/clinical-notes.ts` — typed API client functions
- [ ] `ClinicalNoteCard`, `ClinicalNoteList`, `ClinicalNoteEditor` components
- [ ] Template constants file `apps/web/lib/clinical-note-templates.ts`
- [ ] Patient chart "Notes" tab wired up
- [ ] All tests passing, lint clean

---

## Module 2.1: Digital Tooth Chart ✅

Interactive tooth diagram. The core visual artifact of the paper chart.

### Why this order

Clinical notes reference tooth numbers. Having the tooth chart before treatment planning means the chart state is visible when entering a treatment plan.

### DB Schema

```
tooth_conditions
  id                  UUID PK
  practice_id         UUID NOT NULL FK → practices(id)
  patient_id          UUID NOT NULL FK → patients(id)
  tooth_number        TEXT NOT NULL                       -- FDI or Universal: '1'–'32' adult, 'A'–'T' primary
  notation_system     TEXT NOT NULL DEFAULT 'universal'  CHECK (notation_system IN ('universal', 'fdi'))
  condition_type      TEXT NOT NULL CHECK (condition_type IN (
                        'existing_restoration', 'missing', 'implant', 'crown', 'bridge_pontic',
                        'bridge_abutment', 'root_canal', 'decay', 'fracture', 'watch', 'other'
                      ))
  surface             TEXT                                -- e.g. 'MOD', 'B', 'L'; null for whole-tooth conditions
  material            TEXT                                -- e.g. 'composite', 'amalgam', 'PFM', 'zirconia'
  notes               TEXT
  status              TEXT NOT NULL DEFAULT 'existing' CHECK (status IN (
                        'existing',          -- already present
                        'treatment_planned', -- accepted treatment plan item
                        'completed_today'    -- completed at current visit
                      ))
  recorded_at         DATE NOT NULL                       -- visit date the condition was recorded
  recorded_by         UUID NOT NULL FK → providers(id)
  appointment_id      UUID FK → appointments(id)          -- nullable: some conditions pre-date the system
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
  deleted_at          TIMESTAMPTZ
```

- Uses `PHIMixin`
- Indexes: `(patient_id, recorded_at DESC)`, `(patient_id, tooth_number)`, `(appointment_id)`
- No UNIQUE constraint on `(patient_id, tooth_number, condition_type)` — a tooth can have multiple simultaneous conditions (e.g. existing crown + decay under it)

### API

- `GET /api/v1/patients/{id}/tooth-chart` — returns all non-deleted conditions for the patient; optionally accepts `as_of_date` query param to return the chart state at a past visit date (conditions where `recorded_at <= as_of_date`)
- `POST /api/v1/patients/{id}/tooth-chart/conditions` — add a condition; `appointment_id` optional
- `PATCH /api/v1/patients/{id}/tooth-chart/conditions/{conditionId}` — update condition (status change, notes edit)
- `DELETE /api/v1/patients/{id}/tooth-chart/conditions/{conditionId}` — soft delete
- Audit log on every read and write

### Frontend

**Tooth diagram component (`ToothChart`):**
- SVG-based adult 32-tooth layout; toggle to primary 20-tooth (deciduous) layout
- Each tooth rendered as a simple SVG shape (5 surfaces: mesial, distal, occlusal, buccal, lingual), color-coded:
  - Existing restoration: blue
  - Missing/extracted: grey with X
  - Implant: gold
  - Crown: green outline
  - Treatment planned: orange
  - Completed today: bright green
  - Decay / watch: red
- Click a tooth → popover listing existing conditions for that tooth + "Add condition" button
- Condition entry form in popover: condition type, surface(s), material, notes
- Print-to-PDF button — opens a print-optimized view of the full chart (addresses dad's offline/physical backup concern)
- History mode: date picker to view chart state at any past date (conditions filtered by `recorded_at`)

**Integration points:**
- Patient chart "Tooth Chart" tab
- Appointment detail: tooth conditions recorded at this appointment highlighted

### Tests

- [ ] Unit: `as_of_date` filter — conditions recorded after the date are excluded
- [ ] Unit: soft-delete removes condition from active chart but visible in history
- [ ] Integration: add crown to tooth 14 → fetch chart → condition present; add extraction → fetch with `as_of_date` before extraction → crown still present, extraction absent
- [ ] Auth: Practice B cannot read Practice A's patient chart
- [ ] Frontend: ToothChart renders all 32 teeth (snapshot); color-coding matches condition type (unit)

### Checklist

- [ ] `0018_tooth_conditions.py` Alembic migration
- [ ] `app/models/tooth_condition.py` SQLAlchemy model
- [ ] `app/routers/tooth_chart.py` — all endpoints, audit logging
- [ ] `packages/shared-types` — `ToothCondition`, `CreateToothCondition` Zod schemas
- [ ] `apps/web/lib/api/tooth-chart.ts` — API client
- [ ] `ToothChart` SVG component with all 32 adult teeth
- [ ] Condition popover and entry form
- [ ] History mode date picker
- [ ] Print layout CSS (`@media print`)
- [ ] Patient chart "Tooth Chart" tab wired
- [ ] All tests passing, lint clean

---

## Module 2.4: Treatment Planning

Link planned procedures to teeth. Track plan from proposal to completion.

### DB Schema

```
treatment_plans
  id              UUID PK
  practice_id     UUID NOT NULL FK → practices(id)
  patient_id      UUID NOT NULL FK → patients(id)
  name            TEXT NOT NULL DEFAULT 'Treatment Plan'  -- e.g. 'Phase 1 — Restorations'
  status          TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN (
                    'proposed', 'accepted', 'in_progress', 'completed', 'refused', 'superseded'
                  ))
  presented_at    DATE
  accepted_at     DATE
  completed_at    DATE
  notes           TEXT
  created_by      UUID NOT NULL FK → providers(id)
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  deleted_at      TIMESTAMPTZ

treatment_plan_items
  id                      UUID PK
  practice_id             UUID NOT NULL FK → practices(id)
  treatment_plan_id       UUID NOT NULL FK → treatment_plans(id)
  tooth_number            TEXT                  -- nullable: some procedures are arch-level (e.g. full-mouth SRP)
  cdt_code_id             UUID FK → cdt_codes   -- nullable for free-text
  procedure_code          TEXT                  -- denormalized; required if cdt_code_id null
  procedure_name          TEXT NOT NULL
  surface                 TEXT
  fee_cents               INTEGER NOT NULL
  insurance_est_cents     INTEGER               -- estimated insurance portion; nullable
  patient_est_cents       INTEGER               -- estimated patient portion; nullable
  status                  TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN (
                            'proposed', 'accepted', 'scheduled', 'completed', 'refused'
                          ))
  priority                INTEGER NOT NULL DEFAULT 1  -- display sort order; 1 = highest
  appointment_id          UUID FK → appointments(id) -- set when item is scheduled
  completed_appointment_id UUID FK → appointments(id) -- set when item is completed
  notes                   TEXT
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
  deleted_at              TIMESTAMPTZ
```

- Both tables use `PHIMixin`
- Indexes on `treatment_plans`: `(patient_id, status)`, `(practice_id, status)` — for the open-plan tracking queue
- Indexes on `treatment_plan_items`: `(treatment_plan_id)`, `(patient_id, status)`, `(appointment_id)`

### API

- `GET /api/v1/patients/{id}/treatment-plans` — list plans; `status` filter; pagination
- `POST /api/v1/patients/{id}/treatment-plans` — create plan with initial items
- `GET /api/v1/patients/{id}/treatment-plans/{planId}` — detail with all items
- `PATCH /api/v1/patients/{id}/treatment-plans/{planId}` — update plan status/name/notes
- `POST /api/v1/patients/{id}/treatment-plans/{planId}/items` — add item to plan
- `PATCH /api/v1/patients/{id}/treatment-plans/{planId}/items/{itemId}` — update item (status, fee, scheduling)
- `DELETE /api/v1/patients/{id}/treatment-plans/{planId}/items/{itemId}` — soft delete item
- `GET /api/v1/treatment-plans/open` — practice-level queue: patients with accepted plans where no item is `scheduled` or `completed` (the follow-up queue)
- Audit log on all reads and writes

### Frontend

- Patient chart "Treatment Plan" tab:
  - List of plans grouped by status
  - Expand a plan to see all items with tooth diagram mini-view (which teeth are affected)
  - "Accept plan" / "Refuse plan" buttons on proposed plans
  - "Print treatment plan" button — generates patient-facing PDF printout (procedure names, fees, estimated portions; no internal notes)
  - Add/edit item inline
- **Open treatment plan queue** — practice-level page (`/treatment-plans/open`):
  - Patients with accepted plans and unscheduled items
  - Columns: patient name, plan name, items pending, days since acceptance
  - "Schedule" button opens appointment creation modal pre-filled with first pending procedure
  - This is the follow-up workflow dad mentioned — who has accepted a plan but never scheduled?

### Multi-visit grouping

Some procedures require multiple appointments (crown prep + crown seat). Model this as two `treatment_plan_items` in the same plan, each linked to its own `appointment_id` when scheduled. No separate multi-visit table; the ordering is captured by `priority`.

### Tests

- [ ] Unit: plan status transitions are valid (proposed → accepted → in_progress → completed; refused from any; superseded from any)
- [ ] Unit: item status transitions (proposed → accepted → scheduled → completed; refused from any)
- [ ] Integration: create plan with 3 items → accept plan → schedule item 1 → complete item 1 → plan status auto-transitions to `in_progress`
- [ ] Integration: open plan queue — only returns patients with accepted plans where ≥1 item is unscheduled
- [ ] Auth: Practice B cannot access Practice A's treatment plans
- [ ] Print PDF: smoke test that the printout endpoint returns a PDF MIME type and non-empty body

### Checklist

- [ ] `0019_treatment_plans.py` Alembic migration
- [ ] `app/models/treatment_plan.py`, `app/models/treatment_plan_item.py` SQLAlchemy models
- [ ] `app/routers/treatment_plans.py` — all endpoints, audit logging
- [ ] `packages/shared-types` — `TreatmentPlan`, `TreatmentPlanItem`, `CreateTreatmentPlan` Zod schemas
- [ ] `apps/web/lib/api/treatment-plans.ts` API client
- [ ] Patient chart Treatment Plan tab
- [ ] Open treatment plan queue page
- [ ] PDF printout endpoint and print layout
- [ ] All tests passing, lint clean

---

## 🚦 Staging Checkpoint P2-A — After Modules 2.5, 2.2, 2.1, 2.4

**Why here:** First clinical modules. Dad needs to validate the chart experience before perio charting (which has a very specific workflow) and before offline resilience work begins.

Verify:

- [ ] Create a patient → complete medical history → medical alerts bar shows correct flags
- [ ] Add clinical note for an appointment → sign it → attempt to edit after signing returns error
- [ ] Version history drawer shows prior medical history snapshots in order
- [ ] Tooth chart: add crown to tooth 14, mark tooth 17 missing → chart colors match; history mode with a past date excludes conditions added after that date
- [ ] Treatment plan: create plan with 3 items → accept → schedule one item → verify item links to appointment
- [ ] Open treatment plan queue shows the patient above; disappears when all items are scheduled
- [ ] Print tooth chart to PDF — output looks correct for a physical backup
- [ ] **Dad review:** walk through the full chart experience; confirm it replaces the paper chart flow

---

## Module 2.3: Perio Charting

Six-point probing per tooth with bleeding and recession. Hygienist-entry workflow.

### DB Schema

```
perio_charts
  id              UUID PK
  practice_id     UUID NOT NULL FK → practices(id)
  patient_id      UUID NOT NULL FK → patients(id)
  appointment_id  UUID FK → appointments(id)   -- nullable
  provider_id     UUID NOT NULL FK → providers(id)  -- the hygienist
  chart_date      DATE NOT NULL
  notes           TEXT
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  deleted_at      TIMESTAMPTZ

perio_readings
  id                  UUID PK
  perio_chart_id      UUID NOT NULL FK → perio_charts(id)
  tooth_number        TEXT NOT NULL               -- '1'–'32'
  site                TEXT NOT NULL CHECK (site IN (
                        'db', 'b', 'mb',          -- distal-buccal, buccal, mesial-buccal
                        'dl', 'l', 'ml'           -- distal-lingual, lingual, mesial-lingual
                      ))
  probing_depth_mm    SMALLINT NOT NULL CHECK (probing_depth_mm BETWEEN 0 AND 20)
  recession_mm        SMALLINT NOT NULL DEFAULT 0 CHECK (recession_mm BETWEEN 0 AND 15)
  bleeding            BOOLEAN NOT NULL DEFAULT FALSE
  suppuration         BOOLEAN NOT NULL DEFAULT FALSE
  furcation           TEXT CHECK (furcation IN (NULL, 'I', 'II', 'III'))  -- null = not applicable
  mobility            SMALLINT CHECK (mobility BETWEEN 0 AND 3)           -- null = not recorded
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
```

- `perio_charts` uses `PHIMixin`; `perio_readings` is child data, also under `PHIMixin`
- `perio_readings` is append-only during charting; no soft delete — delete the chart to delete its readings
- UNIQUE on `(perio_chart_id, tooth_number, site)` — one reading per site per chart
- Indexes: `(patient_id, chart_date DESC)` on `perio_charts`; `(perio_chart_id)` on `perio_readings`

### API

- `GET /api/v1/patients/{id}/perio-charts` — list all charts; pagination
- `POST /api/v1/patients/{id}/perio-charts` — create chart; optionally include all readings in the request body (batch creation — the typical entry pattern is to record an entire chart in one pass)
- `GET /api/v1/patients/{id}/perio-charts/{chartId}` — detail with all readings
- `POST /api/v1/patients/{id}/perio-charts/{chartId}/readings` — add / replace individual readings during active charting
- `DELETE /api/v1/patients/{id}/perio-charts/{chartId}` — soft delete entire chart (cascades to readings in service layer)
- Audit log on chart read and creation

### Frontend

**Perio chart entry component (`PerioChart`):**
- Grid layout matching dental perio charting convention:
  - Upper arch (teeth 1–16): readings displayed above the tooth icons, buccal sites on top row, lingual sites on bottom row
  - Lower arch (teeth 17–32): mirrored below
  - Left-to-right entry direction
- Tab / Enter key advances to next site — standard hygienist keyboard-entry flow
- Bleeding and suppuration: checkboxes per site (or single-tap on mobile)
- Furcation: dropdown I/II/III on applicable posterior teeth only
- Color coding: probing depth ≥4mm = yellow, ≥6mm = red (standard thresholds)
- Recession shown as a separate row; CAL (clinical attachment level = depth + recession) computed and displayed read-only
- Mobility: one value per tooth (not per site)

**Comparison view:**
- Select two chart dates → side-by-side display with delta highlighting (worse = red, improved = green)
- This is the primary clinical value — tracking change over time

**Patient chart "Perio" tab:**
- Most recent chart summary (average probing depth, # sites ≥4mm, # bleeding sites)
- "New chart" button → opens full-screen entry mode
- Previous charts listed with date, provider, summary stats; click to view or compare

### Tests

- [ ] Unit: CAL calculation (probing_depth + recession); batch creation inserts all 192 readings for a full-mouth chart (32 teeth × 6 sites)
- [ ] Unit: UNIQUE constraint on `(chart_id, tooth_number, site)` — duplicate site rejected
- [ ] Unit: probing depth out of range (0–20) rejected at API boundary
- [ ] Integration: create chart → add readings → fetch → comparison endpoint returns delta for two dates
- [ ] Auth: hygienist role can create perio charts; read_only role cannot
- [ ] Auth: Practice B cannot read Practice A's perio charts

### Checklist

- [ ] `0020_perio_charts.py` Alembic migration
- [ ] `app/models/perio_chart.py` SQLAlchemy models (`PerioChart`, `PerioReading`)
- [ ] `app/routers/perio_charts.py` — all endpoints, audit logging
- [ ] `packages/shared-types` — `PerioChart`, `PerioReading`, `CreatePerioChart` Zod schemas
- [ ] `apps/web/lib/api/perio-charts.ts` API client
- [ ] `PerioChart` entry grid component (keyboard navigation)
- [ ] Comparison view
- [ ] Patient chart "Perio" tab
- [ ] All tests passing, lint clean

---

## 🚦 Staging Checkpoint P2-B — After Module 2.3

**Why here:** Perio chart has the most complex UI in Phase 2 (keyboard navigation, dual-arch layout). Must be validated with actual hygienist input before shipping.

Verify:

- [ ] Enter a full-mouth perio chart via keyboard — Tab advances through all 192 sites in correct order without focus loss
- [ ] Bleeding sites and recession display correctly; CAL computed on read
- [ ] Probing depth ≥4mm and ≥6mm thresholds color correctly
- [ ] Comparison view shows delta between two chart dates; improved sites show green, worse show red
- [ ] Hygienist can create charts; read_only user cannot
- [ ] Chart date range filter returns only charts in range
- [ ] **Dad + hygienist review:** walk through full perio charting session on staging; verify keyboard flow matches how they actually chart

---

## Module 2.7: Offline Resilience (Phase 1 Only)

PWA app shell so the app loads when internet is down. Read-only mode for cached data.

**Scope:** Phase 1 of `offline_support_plan.md` only — the service worker and PWA app shell. Phases 2–7 (IndexedDB sync, mutation queue, React Query persister) are deferred until Phase 2 modules are stable in production.

**Why only Phase 1:** The full offline stack (Phases 2–7 of the offline plan) is substantial. Phases 2–7 require stable, production-tested data models for patients, appointments, and now clinical data. Build those first; add the sync layer after the practice is actively using clinical modules.

### What Phase 1 delivers

- App loads in the browser with no internet, as long as it was opened once while online
- Staff see a clear "You're offline — viewing cached data" banner
- No new writes accepted while offline (no mutation queue yet — that's Phases 4–5)

### Implementation

New dependencies:
```
@serwist/next   — Next.js service worker plugin
serwist         — Workbox-based service worker toolkit
```

Files to create/modify:
- `apps/web/app/sw.ts` — service worker entry point:
  - Precaches all Next.js static assets (JS, CSS, fonts)
  - `NavigationRoute` with `NetworkFirst` strategy (5s timeout) for HTML pages
  - Falls back to cached HTML on network failure
- `apps/web/next.config.ts` — wrap existing config with `@serwist/next` plugin (`swSrc: "app/sw.ts"`, `swDest: "public/sw.js"`; disabled in `development`)
- `apps/web/public/manifest.json` — PWA manifest (name, icons, `display: "standalone"`)
- `apps/web/app/layout.tsx` — add `<link rel="manifest">` and service worker registration script
- `apps/web/lib/offline/network-status.ts` — `useNetworkStatus(): { isOnline: boolean }` hook wrapping `navigator.onLine` + browser `online`/`offline` events
- `apps/web/components/ui/OfflineBanner.tsx` — fixed top banner shown when `!isOnline`: *"You're offline — viewing cached data. Changes will sync when reconnected."*
- `apps/web/app/(app)/layout.tsx` — add `<OfflineBanner />` above `<main>`

Deferred to Phases 2–7 of offline plan: IndexedDB (Dexie), PHI encryption, sync engine, offline-aware API layer, mutation queue, React Query persister, HIPAA logout cache clearing.

### Tests

- [ ] Unit: `useNetworkStatus` hook — returns `true` on `online` event, `false` on `offline` event
- [ ] Unit: `OfflineBanner` renders when `isOnline = false`; hidden when `isOnline = true`
- [ ] Service worker smoke test: build succeeds, `public/sw.js` generated
- [ ] Manual: open app, kill network, reload — app shell loads (service worker cache)

### Checklist

- [ ] `@serwist/next` and `serwist` added to `apps/web/package.json`
- [ ] `apps/web/app/sw.ts` service worker entry point
- [ ] `apps/web/next.config.ts` updated with serwist plugin
- [ ] `apps/web/public/manifest.json` PWA manifest
- [ ] `apps/web/app/layout.tsx` — manifest link + SW registration
- [ ] `network-status.ts` hook
- [ ] `OfflineBanner.tsx` component
- [ ] `(app)/layout.tsx` — banner wired
- [ ] All tests passing, lint clean

---

## 🚦 Staging Checkpoint P2-C — After Module 2.7

**Why here:** Service worker caching behavior cannot be tested locally — must be validated on a real HTTPS deployment.

Verify:

- [ ] Load app on staging HTTPS → kill network → reload → app shell renders
- [ ] Offline banner appears immediately on network loss; disappears on reconnect
- [ ] No CSP violations in browser console (service worker scope is correct)
- [ ] PWA install prompt appears on Chrome / Safari "Add to Home Screen" (manual check)
- [ ] Confirm service worker is disabled in `development` (no stale cache issues for local dev)

---

## Non-Negotiable Technical Requirements (apply to all Phase 2 modules)

- **PHI** — all new tables with patient data use `PHIMixin`; audit logs on every read and write
- **Pagination** — all list endpoints use cursor-based pagination; no unbounded queries
- **Idempotency** — all mutation endpoints require `Idempotency-Key` header
- **Soft deletes only** — `deleted_at` timestamp; no hard deletes of clinical data
- **Timezone** — all timestamps stored UTC; display timezone from `practices.timezone`
- **Auth at every endpoint** — practice scope validated via `X-Practice-ID` header; role check on all clinical writes

---

## Migration Numbers

| Migration | Module | Table(s) |
|-----------|--------|----------|
| `0016` | 2.5 | `medical_history_versions` |
| `0017` | 2.2 | `clinical_notes` |
| `0018` | 2.1 | `tooth_conditions` |
| `0019` | 2.4 | `treatment_plans`, `treatment_plan_items` |
| `0020` | 2.3 | `perio_charts`, `perio_readings` |

Next available migration number: `0021`
