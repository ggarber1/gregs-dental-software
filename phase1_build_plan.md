# Molar — Phase 1 Build Plan

## Overview

Replace the core Eaglesoft workflow for a solo dental practice. Dad runs Eaglesoft for existing patients while this system goes live for new patients. Full cutover once feature parity is sufficient.

**Pricing target:** $299–$399/month flat (dad currently pays $380/month for Eaglesoft + reminder add-on, with no accurate co-pay calculation and multi-system billing chaos)

---

## Optional Modules — Feature Flags

Modules 5 (Insurance Verification), 6 (Co-pay Estimation), and 7 (Claims Submission) are **opt-in per practice**. A practice must explicitly enable each one. The system is fully usable for scheduling, patient records, and reminders without any of them active.

This matters because:
- Clearinghouse enrollment (Availity, Stedi) takes 2–4 weeks — practices shouldn't be blocked from using the system while they wait
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

### 1.1 Monorepo Scaffolding - Done
- [x] Turborepo monorepo with `apps/web`, `apps/api`, `packages/shared-types`, `packages/ui`, `packages/config`
- [x] Docker Compose for local dev (PostgreSQL, Redis, LocalStack for S3/SQS)
- [x] Root ESLint, Prettier, TypeScript configs in `packages/config`
- [x] `packages/shared-types` — Zod schemas with inferred TypeScript types (mirrored as Pydantic models in API)

### 1.2 AWS Infrastructure (Terraform) - Done
- [x] VPC with public/private subnets, NAT Gateway, VPC flow logs
- [x] RDS PostgreSQL — encrypted at rest (KMS), private subnet only, automated backups (35-day retention), deletion protection
- [x] ElastiCache Redis — idempotency key cache, session cache, rate limiting
- [x] ECS Fargate cluster — separate task definitions for `api`, `web`, `reminder-worker`, `eligibility-worker`, `era-worker`
- [x] ALB with HTTPS termination, WAF rules
- [x] CloudFront distribution for Next.js static assets
- [x] S3 buckets — `phi-documents`, `era-files`, `exports`, `terraform-state` (versioning + KMS encryption + no public access on all)
- [x] SQS queues — `reminders`, `eligibility`, `era-processing`, `audit-logs`
- [x] AWS Cognito user pool — MFA enforced, password policy, app client
- [x] SSM Parameter Store — all secrets stored here (never in env vars or task definitions)
- [x] CloudWatch log groups, alarms (API error rate, claim failures, DLQ depth), dashboard
- [x] AWS Backup for RDS
- [x] Staging and production environments as separate Terraform workspaces

### 1.3 CI/CD - Done
- [x] GitHub Actions pipeline: lint → test → build Docker images → push to ECR → deploy to ECS
- [x] Separate staging and production deployment jobs
- [x] Database migration step in deploy pipeline (Alembic)

### 1.4 FastAPI Skeleton - Done
- [x] App factory with middleware registration
- [x] Cognito JWT verification middleware
- [x] **Audit log middleware** — insert-only PHI access logging, wired before any routes are written
- [x] Idempotency key middleware — enforces `Idempotency-Key` header on all mutation endpoints
- [x] HIPAA security headers middleware
- [x] Alembic migrations setup
- [x] Health check endpoint

### 1.5 Next.js Skeleton - Done
- [x] App Router setup with `(auth)` and `(practice)` route groups
- [x] Cognito Amplify login flow (login page, MFA page)
- [x] Authenticated layout (sidebar nav, session management)
- [x] Typed API client (`lib/api-client.ts`)

### 1.6 Database Schema (Initial Migration)

#### Scope

Foundation tables only — practice configuration, identity, and the insert-only audit log. Patient and scheduling tables come in Modules 2 and 3. Nothing here touches PHI yet; that boundary starts when `patients` is created.

#### Files to create

```
apps/api/app/models/practice.py
apps/api/app/models/user.py          -- includes PracticeUser association model
apps/api/app/models/provider.py
apps/api/app/models/operatory.py
apps/api/alembic/versions/0001_initial_schema.py
```

Update `apps/api/alembic/env.py` — add imports for all four new model modules so Alembic autogenerate sees them.

#### Base conventions (already in place)

`PHIMixin` in `app/models/base.py` provides `created_at`, `updated_at`, `deleted_at`, `last_accessed_by`, `last_accessed_at`. Foundation tables here do **not** use `PHIMixin` — they use a simpler `TimestampMixin` (just `created_at`, `updated_at`, `deleted_at`) to be defined in `base.py`. `PHIMixin` is reserved for tables that hold patient PHI (starting with Module 2's `patients` table). All tables use `UUIDMixin` (UUID v4 primary keys, already defined).

Add `TimestampMixin` to `base.py`:
```python
class TimestampMixin(UUIDMixin):
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

#### Table: `practices`

Holds all practice-level configuration. One row per tenant. Feature flags and clearinghouse credentials live here per the Optional Modules section.

```
id                          UUID PK
name                        TEXT NOT NULL
timezone                    TEXT NOT NULL DEFAULT 'America/New_York'
phone                       TEXT
address_line1               TEXT
address_line2               TEXT
city                        TEXT
state                       CHAR(2)
zip                         TEXT
features                    JSONB NOT NULL DEFAULT '{}'
clearinghouse_provider      TEXT CHECK (clearinghouse_provider IN ('stedi', 'availity', 'dentalxchange'))
clearinghouse_submitter_id  TEXT
clearinghouse_api_key_ssm_path TEXT  -- SSM path only, never the key
billing_npi                 TEXT
billing_tax_id_encrypted    BYTEA       -- AES-256 encrypted, app layer
billing_taxonomy_code       TEXT
masshealth_provider_id      TEXT
created_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
deleted_at                  TIMESTAMPTZ
```

Indexes: primary key only. Single-tenant lookup at app start, no hot-path queries against this table.

#### Table: `users`

Maps Cognito sub → internal user row. Practice membership and role are in `practice_users` (see below) — a user can belong to multiple practices with a different role at each.

```
id              UUID PK
cognito_sub     TEXT NOT NULL UNIQUE      -- from JWT sub claim
email           TEXT NOT NULL
full_name       TEXT NOT NULL
is_active       BOOLEAN NOT NULL DEFAULT TRUE
created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
deleted_at      TIMESTAMPTZ
```

Indexes:
- `UNIQUE (cognito_sub)` — fast JWT → user lookup on every authenticated request

#### Table: `practice_users`

Junction table scoping users to practices with a per-practice role. A doctor who owns two practices gets two rows here, one per practice, potentially with different roles.

```
practice_id     UUID NOT NULL FK → practices(id)
user_id         UUID NOT NULL FK → users(id)
role            TEXT NOT NULL CHECK (role IN ('admin', 'provider', 'front_desk', 'billing', 'read_only'))
is_active       BOOLEAN NOT NULL DEFAULT TRUE
created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
PRIMARY KEY (practice_id, user_id)
```

Indexes:
- `(user_id)` — given a user, list all their practices (practice switcher)
- `(practice_id)` — given a practice, list all its users

**Auth flow:** JWT arrives → look up `users` by `cognito_sub` → validate `practice_users` row exists and `is_active = TRUE` for the practice in the request scope → role from that row drives endpoint authorization. Practice scope comes from an `X-Practice-ID` request header; middleware rejects requests where the user has no active `practice_users` row for that practice ID.

#### Table: `providers`

Dentists, hygienists, and any clinical staff who appear on the schedule. `user_id` is nullable — a provider doesn't need a system login (e.g., an associate not using the system directly). NPI is required per Module 3 (claims generation).

```
id              UUID PK
practice_id     UUID NOT NULL FK → practices(id)
user_id         UUID FK → users(id)   -- nullable: not all providers have logins
full_name       TEXT NOT NULL
npi             TEXT NOT NULL          -- 10-digit NPI
provider_type   TEXT NOT NULL CHECK (provider_type IN ('dentist', 'hygienist', 'specialist', 'other'))
license_number  TEXT
specialty       TEXT                   -- e.g. 'general', 'orthodontics', 'oral_surgery'
color           CHAR(7) NOT NULL DEFAULT '#4F86C6'  -- hex, used on calendar
is_active       BOOLEAN NOT NULL DEFAULT TRUE
display_order   INTEGER NOT NULL DEFAULT 0
created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
deleted_at      TIMESTAMPTZ
```

Indexes:
- `(practice_id)` — all providers for a practice
- `(practice_id, is_active)` — scheduling query: available providers
- `(npi)` — claims validation: check NPI exists before generating 837D

#### Table: `operatories`

Physical chairs/rooms. Used for conflict detection (no double-booking same operatory) and the room-view calendar that front desk actually uses.

```
id              UUID PK
practice_id     UUID NOT NULL FK → practices(id)
name            TEXT NOT NULL           -- e.g. 'Operatory 1', 'Room A'
color           CHAR(7) NOT NULL DEFAULT '#7BC67E'  -- hex, used on calendar
is_active       BOOLEAN NOT NULL DEFAULT TRUE
display_order   INTEGER NOT NULL DEFAULT 0
created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
deleted_at      TIMESTAMPTZ
```

Indexes:
- `(practice_id)` — all operatories for a practice
- `(practice_id, is_active)` — scheduling query: available rooms

#### Table: `audit_logs`

Already exists as a SQLAlchemy model (`app/models/audit_log.py`). The migration must also apply a Postgres DDL trigger so no DB user can UPDATE or DELETE rows — enforced at the DB layer independent of application code.

Trigger DDL (include as raw SQL in migration `upgrade()`):

```sql
CREATE OR REPLACE FUNCTION audit_logs_immutable()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs rows are immutable';
END;
$$;

CREATE TRIGGER trg_audit_logs_no_update
    BEFORE UPDATE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();

CREATE TRIGGER trg_audit_logs_no_delete
    BEFORE DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();
```

Drop in `downgrade()`:
```sql
DROP TRIGGER IF EXISTS trg_audit_logs_no_update ON audit_logs;
DROP TRIGGER IF EXISTS trg_audit_logs_no_delete ON audit_logs;
DROP FUNCTION IF EXISTS audit_logs_immutable();
```

#### Migration file structure

Single Alembic revision `0001_initial_schema`. Creates tables in dependency order:

1. `audit_logs` (no FKs)
2. `practices` (no FKs)
3. `users` (no FKs)
4. `practice_users` (FK → practices, users)
5. `providers` (FK → practices, users)
6. `operatories` (FK → practices)
7. Apply audit_logs immutability triggers

`downgrade()` drops in reverse order and drops triggers/function. Migration is safe to re-run (Alembic tracks applied revisions in `alembic_version`).

#### What's deferred

- `patients`, `insurance_plans`, `patient_insurance` — Module 2
- `appointments`, `appointment_types` — Module 3
- `appointment_reminders` — Module 4
- `eligibility_checks` — Module 5
- `appointment_procedures`, `cdt_codes` — Module 6
- `claims`, `payments` — Module 7
- App DB user `GRANT INSERT ON audit_logs` / revoke UPDATE+DELETE — done in Terraform RDS bootstrap, not in Alembic

#### Checklist

- [x] Add `TimestampMixin` to `app/models/base.py`
- [x] `app/models/practice.py` — `Practice` model
- [x] `app/models/user.py` — `User` + `PracticeUser` models
- [x] `app/models/provider.py` — `Provider` model
- [x] `app/models/operatory.py` — `Operatory` model
- [x] `alembic/versions/0001_initial_schema.py` — all tables + audit trigger DDL
- [x] Update `alembic/env.py` — import all four new model modules
- [x] `alembic upgrade head` runs cleanly on local Postgres (Docker Compose)
- [x] Verify audit_logs trigger: `UPDATE audit_logs SET ...` raises exception
- [x] UUID PKs confirmed (no serial/integer PKs in `\d` output)

---

## 🚦 Staging Checkpoint 1 — End of Module 1 (after 1.4 + 1.5 + 1.6)

**Why here:** First ECS deploy. None of this can be validated locally — Cognito, RDS, ElastiCache, and CloudWatch all need real AWS.

Verify:
- [x] Both ECS tasks (`api`, `web`) start and stay healthy — no crash loops in CloudWatch logs
- [x] Cognito login flow works end-to-end: login → JWT issued → API accepts it (MFA optional in staging — see pre-production gate below)
- [x] `GET /health` returns `{"db": "ok", "redis": "ok"}` against real RDS + ElastiCache
- [x] Alembic `upgrade head` runs cleanly on staging RDS (runs as one-off ECS task in deploy workflow)
- [x] HIPAA headers visible in browser devtools on every response
- [x] CloudWatch log groups receiving output from both services
- [x] ALB HTTPS termination working; HTTP redirects to HTTPS (N/A — staging is HTTP-only, no domain set)

---

**Pre-production gate — MFA enrollment flow:**
Cognito is `OPTIONAL` in staging (sufficient for dev). Before production go-live, set to `ON` (required) and build a TOTP enrollment screen (shown on first login when no MFA is enrolled — generate QR code via `setupTOTP`, verify with `verifyTOTPSetup`). Without this, users with no TOTP enrolled will be locked out once MFA is required.

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

## 🚦 Staging Checkpoint 2 — End of Module 2 (after 2.1–2.4)

**Why here:** First real PHI in the system. Also the right moment to get dad's eyes on the first screens before building scheduling on top.

Verify:
- [ ] Create a patient — confirm SSN is stored as encrypted `bytea` in RDS (not plaintext)
- [ ] Audit log rows appear in `audit_logs` for every patient read and write
- [ ] Upload an X-ray to the real `phi-documents` S3 bucket; pre-signed URL loads the image
- [ ] Send a live intake form SMS via Twilio to a test phone number; complete the form on mobile
- [ ] Token is rejected on second submission (single-use enforced)
- [ ] Completed intake data appears on patient chart
- [ ] **Dad review:** walk through patient list, chart, and intake form UX — capture feedback before continuing

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

## 🚦 Staging Checkpoint 3 — End of Module 3 (after 3.1–3.3)

**Why here:** Scheduling is the core daily workflow. Dad needs to validate the UX before you build reminders on top of it — the appointment data model is the foundation for Modules 4–7.

Verify:
- [ ] Book appointments across multiple providers and operatories — no false conflict errors
- [ ] Double-booking correctly rejected
- [ ] All appointment timestamps display in the practice's local timezone, stored as UTC in RDS
- [ ] Appointment status transitions work (scheduled → checked_in → completed)
- [ ] Day sheet shows correct ordering
- [ ] **Dad + staff review:** book a full mock day's schedule; verify the calendar and day sheet match how they actually work

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

## ⚡ Action Required at End of Module 4 — Start Availity Prod Enrollment

Do not wait until Module 7 to start this. Payer enrollment queues run 4–8 weeks.

- [ ] Submit Availity production application
- [ ] Enroll for each target payer (Delta Dental, MassHealth/DentaQuest, Cigna, Aetna, MetLife)
- [ ] Submit NPI verification for the practice
- [ ] Sign BAA with Availity
- [ ] Pass Availity test claim submission requirements
- [ ] Target: prod credentials in hand before Staging Checkpoint 6

---

## 🚦 Staging Checkpoint 4 — End of Module 4 (after 4.1–4.3)

**Why here:** First async worker (ECS `reminder-worker`) and first Twilio integration. The inbound webhook cannot be tested locally — it needs a real publicly reachable URL.

Verify:
- [ ] Create an appointment → SQS reminder job enqueued → worker dequeues → Twilio SMS delivered to test number
- [ ] Email reminder also delivered via SES
- [ ] Duplicate send prevention: kill the worker mid-job, restart it — same SMS not sent twice
- [ ] Twilio inbound "YES" reply marks appointment confirmed; visible on day sheet
- [ ] "STOP" reply marks patient as opted out; no further SMS sent to that number
- [ ] Kill the ECS worker task — CloudWatch alarm fires on DLQ depth within expected window
- [ ] Reschedule an appointment — pending reminders for the old time are cancelled

---

## Module 5: Insurance Verification

### 5.1 Insurance Plan Management
- [ ] `insurance_plans` CRUD — carrier name, payer ID (clearinghouse ID), group number, in/out of network flag
- [ ] Seed common carriers (Delta Dental, MassHealth `CKMA1`, Cigna, Aetna, United, MetLife)
- [ ] `patient_insurance` — link patient to plan, subscriber info, priority (primary/secondary)
- [ ] UI for adding/editing patient insurance on patient chart

### 5.2 Eligibility Verification API
- [ ] Abstract `EligibilityProvider` interface — swappable between Stedi (dev/staging), Availity (production primary), and DentalXChange (secondary for dental-specific payers)
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

## 🚦 Staging Checkpoint 5 — End of Module 5 (after 5.1–5.4)

**Why here:** First outbound call to an external API (Stedi) from inside the ECS private subnet. NAT gateway routing, SSM parameter retrieval, and ECS task IAM roles all need to be correct — none of this is testable locally.

Verify:
- [ ] ECS `eligibility-worker` can reach Stedi sandbox from private subnet (NAT gateway routing confirmed in VPC flow logs)
- [ ] SSM parameter store: worker retrieves Stedi API key from SSM at runtime — never hardcoded
- [ ] Run a real eligibility check via Stedi sandbox for a test patient; structured result stored in `eligibility_checks`
- [ ] Pre-appointment auto-check fires via CloudWatch scheduled rule 3 days before a test appointment
- [ ] Clearinghouse failure (bad credentials / timeout): check marked `failed`, staff alert visible — no silent skip
- [ ] Eligibility badge updates on appointment slot after check completes
- [ ] MassHealth payer ID `CKMA1` routes correctly through Stedi

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
- [ ] Abstract `ClaimsProvider` interface — swappable between Stedi (dev/staging), Availity (production primary), and DentalXChange (secondary for dental-specific payers); routing is payer-config-driven, not hardcoded
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

## 🚦 Staging Checkpoint 6 — End of Modules 6 + 7 (after 6.1–7.4)

**Why here:** Highest financial risk in the entire system. Wrong co-pay calculation or a duplicate claim submission costs the practice money. Verify the full claims pipeline before touching billing.

Verify:
- [ ] Submit a test 837D to Stedi sandbox; confirm acknowledgment received and `claims.clearinghouse_status` updated
- [ ] Attempt to submit the same claim twice with the same idempotency key — only one submission goes through
- [ ] Simulate a denial: denied claim appears on worklist with denial code; one-click resubmit generates new idempotency key
- [ ] Drop a test 835 ERA file into S3 `era-files` bucket → SQS message → ERA worker parses it → payment auto-reconciled against claim
- [ ] Unmatched ERA payment flagged for manual review (not silently dropped)
- [ ] Co-pay calculation: verify several procedure combinations against known expected outputs (bring a real EOB for comparison)
- [ ] Secondary insurance flagged for manual review — not auto-calculated

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

## 🚦 Staging Checkpoint 7 — End of Module 8 (after 8.1–8.3)

**Why here:** Full billing cycle is complete. Before touching real patient data in the migration, dad and his bookkeeper should do a complete end-to-end dry run on staging with synthetic data.

Verify:
- [ ] Full workflow dry run: new patient → appointment → eligibility check → procedures entered → co-pay shown → appointment completed → claim submitted → ERA received → payment recorded → balance at zero
- [ ] Aging report shows correct buckets for outstanding balances
- [ ] Daily production report matches what was manually entered
- [ ] Quickbooks export CSV reviewed by bookkeeper — confirm format matches what they import
- [ ] Re-export same date range — no duplicates (idempotent export verified)
- [ ] **Dad sign-off:** he should be comfortable using the system for all daily tasks at this point

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

## 🚦 Staging Checkpoint 8 — Pre-Go-Live (after 9.1, before cutover)

**Why here:** Last gate before real patient data enters the system. This is the point of no return — once existing patients are migrated, rollback is painful.

Verify:
- [ ] Run migration script in dry-run mode against a real Eaglesoft export — review the summary report; rejection rate should be near zero
- [ ] Run migration for real on staging; spot-check 20+ patient records against Eaglesoft source data
- [ ] Audit logs confirm every migrated record has an entry (migration counts as a PHI write)
- [ ] Confirm production RDS deletion protection is on, automated backups are running, and a fresh snapshot exists before cutover
- [ ] Staff have completed training on staging — front desk can book, check in, and complete an appointment without help
- [ ] Availity and DentalXChange BAAs signed before any real patient insurance data is submitted to clearinghouse
- [ ] CloudWatch alarms tested: trigger an API error spike and a DLQ depth alarm artificially — confirm alerts fire
- [ ] Confirm dad is happy to go live for new patients while existing patients stay in Eaglesoft

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

**Strategy:** Availity is the production primary (MassHealth-approved, full transaction set). DentalXChange is secondary for dental-specific payers where Availity lacks connectivity. DentalXChange is NOT on MassHealth's approved vendor list — do not route MassHealth claims through it.

- [ ] Sign up for **Stedi** free tier (immediate access — use for dev/staging)
- [ ] Apply for **Availity** sandbox access (production primary — MassHealth-approved)
- [ ] Apply for **DentalXChange XConnect** sandbox access (secondary — dental-specific payers only)
- [ ] Confirm MassHealth payer ID `CKMA1` routes through Availity, not DentalXChange
- [ ] MassHealth dental specifically goes through **DentaQuest** (MassHealth's dental program) — verify routing with Availity
- [ ] Obtain BAAs from both Availity and DentalXChange before submitting any real patient data

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
