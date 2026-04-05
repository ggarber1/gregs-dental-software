# Phase 1 Build Plan — Dental PMS MVP

## Overview

Replace the core Eaglesoft workflow for a solo dental practice. Dad runs Eaglesoft for existing patients while this system goes live for new patients. Full cutover once feature parity is sufficient.

**Pricing target:** $299–$399/month flat (dad currently pays $380/month for Eaglesoft + reminder add-on, with no accurate co-pay calculation and multi-system billing chaos)

---

## Optional Modules — Feature Flags

Modules 5 (Insurance Verification), 6 (Co-pay Estimation), and 7 (Claims Submission) are **opt-in per practice**. A practice must explicitly enable each one. The system is fully usable for scheduling, patient records, and reminders without any of them active.

This matters because:
- Clearinghouse enrollment (DentalXChange, Stedi) takes 2–4 weeks — practices shouldn't be blocked from using the system while they wait
- Some practices may use a separate billing service and only want the scheduling/comms layer
- Modules 6 and 7 require NPI, tax ID, and clearinghouse credentials that not every practice will have ready at onboarding

### Feature Flag Implementation

```sql
-- practices table additions
ALTER TABLE practices ADD COLUMN features JSONB NOT NULL DEFAULT '{}';
-- e.g. {"eligibility_verification": true, "copay_estimation": false, "claims_submission": true}

ALTER TABLE practices ADD COLUMN clearinghouse_provider TEXT
    CHECK (clearinghouse_provider IN ('stedi', 'dentalxchange'));
ALTER TABLE practices ADD COLUMN clearinghouse_submitter_id TEXT;
ALTER TABLE practices ADD COLUMN clearinghouse_api_key_ssm_path TEXT; -- SSM path, never store key directly
ALTER TABLE practices ADD COLUMN billing_npi TEXT;
ALTER TABLE practices ADD COLUMN billing_tax_id_encrypted BYTEA;
ALTER TABLE practices ADD COLUMN billing_taxonomy_code TEXT;
ALTER TABLE practices ADD COLUMN masshealth_provider_id TEXT; -- required for CKMA1 claims
```

### Rules
- Module 6 cannot be enabled unless Module 5 is enabled (no eligibility data = no estimation)
- Module 7 can be enabled independently of Modules 5 and 6 (claims can be submitted with manually-entered co-pays)
- All three modules check the feature flag at the API and worker level before executing — disabled = 404 or silent no-op depending on context
- Settings page in UI shows setup checklist per module: credentials entered, test transaction passed, module active
- Practices can disable a module at any time — existing data is retained, workers stop processing new jobs

### Onboarding Flow
```
Step 1 (required): Practice info, providers, operatories
Step 2 (required): Scheduling + reminders → live immediately
Step 3 (optional): Enable eligibility verification → enter clearinghouse credentials → run test check
Step 4 (optional): Enable co-pay estimation → requires Step 3 complete
Step 5 (optional): Enable claims submission → enter NPI, tax ID, taxonomy → run test claim in sandbox
```

---

## Module 1: Foundation & Infrastructure

### 1.1 Monorepo Scaffolding
- [ ] Turborepo monorepo with `apps/web`, `apps/api`, `packages/shared-types`, `packages/ui`, `packages/config`
- [ ] Docker Compose for local dev (PostgreSQL, Redis, LocalStack for S3/SQS)
- [ ] Root ESLint, Prettier, TypeScript configs in `packages/config`
- [ ] `packages/shared-types` — Zod schemas with inferred TypeScript types (mirrored as Pydantic models in API)

### 1.2 AWS Infrastructure (Terraform)
- [ ] VPC with public/private subnets, NAT Gateway, VPC flow logs
- [ ] RDS PostgreSQL — encrypted at rest (KMS), private subnet only, automated backups (35-day retention), deletion protection
- [ ] ElastiCache Redis — idempotency key cache, session cache, rate limiting
- [ ] ECS Fargate cluster — separate task definitions for `api`, `web`, `reminder-worker`, `eligibility-worker`, `era-worker`
- [ ] ALB with HTTPS termination, WAF rules
- [ ] CloudFront distribution for Next.js static assets
- [ ] S3 buckets — `phi-documents`, `era-files`, `exports`, `terraform-state` (versioning + KMS encryption + no public access on all)
- [ ] SQS queues — `reminders`, `eligibility`, `era-processing`, `audit-logs`
- [ ] AWS Cognito user pool — MFA enforced, password policy, app client
- [ ] SSM Parameter Store — all secrets stored here (never in env vars or task definitions)
- [ ] CloudWatch log groups, alarms (API error rate, claim failures, DLQ depth), dashboard
- [ ] AWS Backup for RDS
- [ ] Staging and production environments as separate Terraform workspaces

### 1.3 CI/CD
- [ ] GitHub Actions pipeline: lint → test → build Docker images → push to ECR → deploy to ECS
- [ ] Separate staging and production deployment jobs
- [ ] Database migration step in deploy pipeline (Alembic)

### 1.4 FastAPI Skeleton
- [ ] App factory with middleware registration
- [ ] Cognito JWT verification middleware
- [ ] **Audit log middleware** — insert-only PHI access logging, wired before any routes are written
- [ ] Idempotency key middleware — enforces `Idempotency-Key` header on all mutation endpoints
- [ ] HIPAA security headers middleware
- [ ] Alembic migrations setup
- [ ] Health check endpoint

### 1.5 Next.js Skeleton
- [ ] App Router setup with `(auth)` and `(practice)` route groups
- [ ] Cognito Amplify login flow (login page, MFA page)
- [ ] Authenticated layout (sidebar nav, session management)
- [ ] Typed API client (`lib/api-client.ts`)

### 1.6 Database Schema (Initial Migration)
- [ ] `practices` table
- [ ] `users` table (linked to Cognito sub)
- [ ] `providers` table (dentists, hygienists — NPI required)
- [ ] `operatories` table (chairs/rooms)
- [ ] `audit_logs` table — append-only, Postgres trigger preventing UPDATE/DELETE, app DB user has INSERT only
- [ ] All PHI tables with `created_at`, `updated_at`, `deleted_at`, `last_accessed_by`, `last_accessed_at`
- [ ] UUID primary keys everywhere (no exposed sequential integers)
- [ ] Indexes for scheduling queries, insurance lookups, claims processing, audit compliance

---

## Module 2: Patient Management & Digital Intake

### 2.1 Patient API
- [ ] `POST /api/v1/patients` — create patient, write audit log
- [ ] `GET /api/v1/patients` — search/list with pagination
- [ ] `GET /api/v1/patients/{id}` — patient detail, write audit log on every read
- [ ] `PATCH /api/v1/patients/{id}` — update patient
- [ ] Soft delete only (`deleted_at`)
- [ ] SSN encrypted at application layer (AES-256) before storage

### 2.2 Patient Frontend
- [ ] Patient search/list page
- [ ] New patient form
- [ ] Patient chart overview page
- [ ] Medical alerts bar (allergies always visible)

### 2.3 X-Ray Viewer (Basic)

Dad reviews X-rays before every patient using separate software. Without this, staff still has to keep the old X-ray software open alongside ours for every appointment — persistent daily friction.

Phase 1 scope is upload + display only. Sensor integration (hardware capture directly into the system) stays in Phase 4.

- [ ] Upload X-ray images to patient record (JPG, PNG, DICOM `.dcm` files accepted)
- [ ] Store in S3 under `phi-documents` bucket, encrypted at rest, pre-signed URL for retrieval
- [ ] Link X-rays to specific appointments and/or tooth numbers
- [ ] Basic viewer in patient chart — display image, brightness/contrast slider, zoom
- [ ] X-ray history tab on patient chart — all images across all visits in chronological order
- [ ] Staff workflow: export image from existing X-ray software → drag and drop into patient record
- [ ] **Not in Phase 1:** DICOM proper rendering with measurement tools (Phase 2), hardware sensor integration (Phase 4)

### 2.4 Digital Intake Forms
- [ ] `POST /api/v1/intake/send` — generate cryptographically random 32-byte token, set 72h expiry, send SMS via Twilio
- [ ] `GET /intake/[token]` — public route (no auth), single-use, mobile-optimised
- [ ] Form fields: personal info, medical history, medications, allergies, dental history, insurance info, HIPAA consent + signature
- [ ] On submission: store encrypted responses in `intake_forms.responses` (jsonb), mark token used, write audit log with IP address
- [ ] Completed intake data auto-populates patient record for staff review
- [ ] `/intake/[token]/complete` — confirmation page
- [ ] Reject resubmission on already-completed tokens

---

## Module 3: Scheduling

### 3.1 Scheduling API
- [ ] `GET /api/v1/appointments` — by date range, provider, operatory
- [ ] `POST /api/v1/appointments` — create with double-booking conflict detection
- [ ] `PATCH /api/v1/appointments/{id}` — update (reschedule, status change)
- [ ] `DELETE /api/v1/appointments/{id}` — soft cancel with `cancellation_reason`
- [ ] Appointment status state machine: `scheduled → confirmed → checked_in → in_chair → completed | cancelled | no_show`
- [ ] Appointment types CRUD (name, duration, default CDT codes, color)
- [ ] Provider and operatory management CRUD

### 3.2 Scheduling Frontend
- [ ] Day/week calendar view — FullCalendar integration (don't build from scratch)
- [ ] Appointment slot display by operatory (room view — this is how the front desk actually works)
- [ ] Create/edit appointment modal (patient search, type, provider, operatory, time)
- [ ] Appointment status update (check-in, mark complete, mark no-show)
- [ ] Day sheet view — ordered list of today's appointments for the front desk

### 3.3 Scheduling Logic
- [ ] Conflict detection — no double-booking same operatory or provider in overlapping time
- [ ] Practice timezone stored in `practices.timezone`, all display derived from this — never ad hoc
- [ ] All timestamps stored as UTC in database

---

## Module 4: Automated Reminders

### 4.1 Reminder Infrastructure
- [ ] SQS `dental-reminders-queue` with dead-letter queue
- [ ] ECS Fargate worker task — long-poll SQS, process reminder jobs
- [ ] Reminder scheduler — on appointment creation, enqueue reminder jobs at (48h before, 24h before)
- [ ] Appointment reschedule / cancellation cancels pending reminders

### 4.2 Reminder Delivery
- [ ] Twilio SMS integration — idempotency key per send, check `appointment_reminders.twilio_message_sid` before sending to prevent duplicates
- [ ] AWS SES email reminders
- [ ] Worker flow: read SQS → check DB for existing sent record → if not sent, send → write `sent_at` + message SID → delete SQS message
- [ ] Twilio inbound webhook — patient replies "YES" / "NO" / "STOP" update `appointment_reminders.response_received`
- [ ] STOP / opt-out handling — mark patient as opted out, never SMS again
- [ ] Confirmation status visible on day sheet (confirmed / unconfirmed / opted-out)

### 4.3 Reminder Frontend
- [ ] Reminder status column on day sheet
- [ ] Per-appointment reminder history in appointment detail
- [ ] Settings page — reminder timing configuration (how many hours before)

---

## Module 5: Insurance Verification

### 5.1 Insurance Plan Management
- [ ] `insurance_plans` CRUD — carrier name, payer ID (clearinghouse ID), group number, in/out of network flag
- [ ] Seed common carriers (Delta Dental, MassHealth `CKMA1`, Cigna, Aetna, United, MetLife)
- [ ] `patient_insurance` — link patient to plan, subscriber info, priority (primary/secondary)
- [ ] UI for adding/editing patient insurance on patient chart

### 5.2 Eligibility Verification API
- [ ] Abstract `EligibilityProvider` interface — swappable between Stedi (dev) and DentalXChange/Availity (production)
- [ ] `POST /api/v1/eligibility/check` — enqueue async check via SQS
- [ ] ECS eligibility worker — dequeues, calls clearinghouse API, stores structured result in `eligibility_checks`
- [ ] `GET /api/v1/eligibility/{checkId}` — poll for result
- [ ] Pre-appointment auto-fetch — trigger eligibility check 3 days before each appointment via CloudWatch scheduled rule
- [ ] MassHealth: route through clearinghouse as payer ID `CKMA1` — no special-case portal logic
- [ ] On clearinghouse failure: mark check as `failed`, alert staff, never silently skip

### 5.3 Eligibility Data Storage
- [ ] Parse and store structured benefit fields: deductible (individual/family/met), out-of-pocket max, coinsurance by category (preventive/basic/major/ortho), annual max + used, waiting periods, frequency limitations
- [ ] Store full raw response as `jsonb` for debugging and manual review
- [ ] Patients with secondary insurance flagged for manual co-pay review (no COB auto-calculation in Phase 1)

### 5.4 Eligibility Frontend
- [ ] Insurance verification queue — today's patients with verification status
- [ ] Eligibility card on patient chart — benefit summary, deductible remaining, coverage %  by category
- [ ] Eligibility badge inline on appointment slot (verified / pending / failed / not-checked)
- [ ] Manual re-verify button (re-triggers check)

---

## Module 6: Co-pay Calculation

### 6.1 Copay Calculation Service
- [ ] Pure function: takes `eligibility_check` + list of `appointment_procedures` → returns `PatientResponsibilityBreakdown`
- [ ] No I/O — 100% unit testable
- [ ] Calculation: `(fee - write_off) * coinsurance_pct`, applied after deductible, subject to annual max remaining, frequency limitations
- [ ] Handles multiple procedures per visit (each may have different category/coinsurance)
- [ ] Secondary insurance: flag for manual review — do not attempt COB auto-calculation in Phase 1
- [ ] Exhaustive unit test coverage — wrong here means practice loses money

### 6.2 Procedure Management
- [ ] CDT code catalog (seed all active ADA codes D0100–D9999 with description and category)
- [ ] `appointment_procedures` — link CDT codes to appointment (tooth number, surface, quantity, fee, status)
- [ ] Procedure entry UI — searchable CDT code selector on appointment detail

### 6.3 Copay Display
- [ ] Patient responsibility breakdown shown on appointment detail after procedures entered
- [ ] Breakdown by procedure: fee, insurance portion, patient portion
- [ ] Totals: insurance owes / patient owes at checkout
- [ ] Staff can override calculated co-pay with manual entry (with required note)

---

## Module 7: Claims Submission

### 7.1 Claims Generation
- [ ] 837D (dental) claim generation from `appointment_procedures` + `patient_insurance` + `provider` NPI
- [ ] Use custom `X12Builder` class to generate raw 837D — pyx12 is a validator only, not a generator
- [ ] Abstract `ClaimsProvider` interface — swappable between Stedi (dev/staging) and DentalXChange (production)
- [ ] Idempotency key on every claim submission — stored in `claims.idempotency_key`, prevents duplicate submissions on retry
- [ ] Store raw 837D payload in `claims.raw_submission` for debugging

### 7.2 Claims Submission
- [ ] `POST /api/v1/claims` — generate and submit claim, return `claim_id`
- [ ] Status polling — clearinghouse acknowledgment updates `claims.clearinghouse_status`
- [ ] Claims status state machine: `draft → submitted → acknowledged → pending → paid | denied | appealing`
- [ ] Denial reason and code stored on `claims` record
- [ ] MassHealth claims: route through clearinghouse as payer `CKMA1` — same code path as all other payers

### 7.3 ERA Processing
- [ ] SQS `dental-era-queue` — clearinghouse drops 835 ERA files to S3, S3 event triggers SQS message
- [ ] ERA worker — dequeues, parses 835 with `pyx12`, creates `payments` records from insurance payments
- [ ] Payment auto-reconciles against open claims
- [ ] Unmatched ERA payments flagged for manual review

### 7.4 Claims Frontend
- [ ] Claims worklist — filter by status (draft, submitted, pending, denied)
- [ ] Claim detail — procedures billed, amounts, denial reason if denied
- [ ] One-click resubmit for denied claims (new idempotency key)
- [ ] Submit claim button on completed appointment

---

## Module 8: Billing & Payments

### 8.1 Payment Recording
- [ ] `POST /api/v1/payments` — record payment with idempotency key
- [ ] Payment types: `insurance_era` (auto from ERA), `patient_copay`, `patient_balance`, `adjustment`
- [ ] Payment methods: cash, check, card, EFT
- [ ] Patient balance calculation: total billed - insurance paid - patient payments
- [ ] Bill patient for outstanding balance — print/mail workflow (generate printable statement PDF stored in S3)

### 8.2 Reporting
- [ ] Aging report — patient balances by age bucket (current, 30, 60, 90+ days)
- [ ] Daily production report — procedures completed, amounts billed
- [ ] Claims status summary — counts by status

### 8.3 Quickbooks Export
- [ ] Confirm CSV vs IIF format with dad's bookkeeper before building
- [ ] `POST /api/v1/exports/quickbooks` — generate CSV for date range, upload to S3, return pre-signed URL
- [ ] Include: payments received, payment method, patient name, date, insurance payments
- [ ] Mark payments as exported (`quickbooks_exported = true`) to prevent double-export
- [ ] Export is idempotent — re-exporting same date range returns same records plus any new ones

---

## Module 9: Eaglesoft Data Migration

### 9.1 Migration Script
- [ ] Export from Eaglesoft (MSSQL database or CSV export)
- [ ] Per-row validation — every record validated, rejections written to separate file, never silently skipped
- [ ] Migrate: patients, insurance plans, appointment history (last 2 years)
- [ ] Idempotent — safe to run multiple times (upsert on `external_id`)
- [ ] Dry-run mode with summary report before committing

### 9.2 Parallel Run
- [ ] New patients go into new system from go-live date
- [ ] Existing patients remain in Eaglesoft until migration cutover
- [ ] Staff training on new system before full cutover

---

## Non-Negotiable Technical Requirements (apply to all modules)

- **HIPAA** — encryption at rest (KMS) and in transit (TLS 1.2+), audit logs on all PHI access, BAAs with AWS, Twilio, clearinghouse
- **Idempotency** — all mutation endpoints require `Idempotency-Key` header; safe to retry without side effects
- **Crash-only design** — every worker and service fails hard and restarts, never degrades silently
- **Incremental progress** — no big-bang operations; every step leaves the system in a valid state
- **Audit logs are insert-only** — app DB user has INSERT only on `audit_logs`; Postgres trigger prevents UPDATE/DELETE
- **Timezone** — all timestamps stored UTC; display timezone derived from `practices.timezone`; single conversion layer
- **Tokens** — intake form tokens are 32-byte cryptographically random values, not UUIDs; 72h expiry; single-use
- **Secondary insurance** — flagged for manual review in Phase 1, no COB auto-calculation
- **No distributed locks** — use idempotency keys and fencing tokens instead

---

## Clearinghouse Setup (do on Day 1, not Week 9)

- [ ] Apply for **DentalXChange XConnect** sandbox access (2–4 week approval queue)
- [ ] Sign up for **Stedi** free tier (immediate access — use for dev/staging)
- [ ] Verify DentalXChange is on [MassHealth approved vendor list](https://www.mass.gov/doc/masshealth-vendor-list-effective-may-2025-0/download)
- [ ] Confirm MassHealth payer ID `CKMA1` routes correctly through chosen clearinghouse
- [ ] Obtain BAA from DentalXChange before submitting any real patient data

---

## Build Sequence

| Weeks | Modules |
|-------|---------|
| 1–2 | Foundation (monorepo, infra, auth, audit middleware, DB schema) |
| 3–4 | Patient management + digital intake + X-ray upload/viewer |
| 5–6 | Scheduling |
| 7–8 | Automated reminders |
| 9–10 | Insurance verification |
| 11–12 | Co-pay estimation + claims submission |
| 13–14 | Billing + Quickbooks export |
| 15–17 | Eaglesoft migration + hardening + dad's practice onboarding |
