# Patient Aging + Statements — Design Spec

**Date:** 2026-08-05
**Module:** 8b — Patient Aging + Statements
**Depends on:** Module 8a (ledger_entries, ledger service, billing_ledger feature flag)

---

## 1. Overview

Gives front-desk staff a patient A/R aging worklist and the ability to generate and deliver PDF billing statements to patients with outstanding balances. Statements are always **manually triggered** — no automatic batch sends. Delivery is **PDF-first**: email with PDF attachment (SES) or download for physical mail. Statements are never auto-generated.

---

## 2. Data Model

### 2.1 New table: `patient_statements` (migration 0039)

Append-only record of every statement generated (emailed or downloaded). Used to track "last statement sent" on the worklist and for HIPAA audit purposes.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `practice_id` | UUID | Tenant key, FK → practices |
| `patient_id` | UUID | FK → patients |
| `delivery_method` | String(20) | CHECK: `email`, `download` |
| `balance_cents` | Integer | Total balance at time of generation |
| `aging_snapshot` | JSONB | `{current_cents, days_31_60_cents, days_61_90_cents, days_90_plus_cents}` — point-in-time snapshot |
| `generated_at` | DateTime TZ | When the PDF was generated |
| `delivered_at` | DateTime TZ nullable | When SES accepted the send; null for downloads |
| `generated_by` | String(255) | User sub |
| `created_at` | DateTime TZ | |
| `updated_at` | DateTime TZ | |

Indexes: `(practice_id, patient_id, generated_at DESC)`, `(practice_id, generated_at DESC)`.

No S3 storage — PDFs are regenerated on demand. The `aging_snapshot` preserves what the patient saw at delivery time.

### 2.2 Aging computation

Charges are bucketed by `posted_at` into four age ranges relative to today:

| Bucket | Age |
|---|---|
| Current | 0–30 days |
| 31–60 days | 31–60 days |
| 61–90 days | 61–90 days |
| 90+ days | > 90 days |

Payments and adjustments reduce the total balance but are **not attributed to specific buckets** — they are shown as a single "Payments & Credits" total. Buckets show gross charge amounts. This avoids FIFO attribution complexity and matches standard small-practice dental billing software behavior.

Patients with `balance_cents ≤ 0` are excluded from the worklist entirely. A statement cannot be generated for a patient with no outstanding balance.

---

## 3. API Endpoints

All endpoints in this module are gated on the existing `billing_ledger` feature flag. The patient aging worklist is a ledger-derived report (not claims-derived), so it uses `billing_ledger` rather than `claims_submission`.

### 3.1 Patient Aging Worklist

```
GET /api/v1/reports/patient-aging
```

Query params:
- `sort_by`: `balance` (default) | `oldest_charge` | `last_statement`
- `min_balance_cents`: integer, default `500` ($5.00)

Response: paginated list of `PatientAgingRow`:
```json
{
  "patient_id": "uuid",
  "patient_name": "Jane Smith",
  "email": "jane@example.com",
  "balance_cents": 15000,
  "current_cents": 5000,
  "days_31_60_cents": 5000,
  "days_61_90_cents": 3000,
  "days_90_plus_cents": 2000,
  "last_statement_at": "2026-07-01T10:00:00Z",
  "last_statement_method": "email"
}
```

Single SQL query: `GROUP BY patient_id` with `SUM(amount_cents) > min_balance_cents`, age buckets computed with `CASE WHEN` on `posted_at`, left join to `patient_statements` subquery for `last_statement_at`.

### 3.2 Statement Endpoints

Router: `apps/api/app/routers/statements.py`, mounted at `/api/v1`.

**Generate and deliver:**
```
POST /api/v1/patients/{patient_id}/statements
```
Body: `{"delivery_method": "email" | "download"}`

- `email`: generates PDF bytes → sends via SES with PDF attachment → records statement row with `delivered_at` set → returns `{"statement_id": "...", "delivered_at": "..."}`.
- `download`: generates PDF bytes → records statement row (`delivered_at` null) → returns raw PDF as `application/pdf` with `Content-Disposition: attachment; filename="statement-{date}.pdf"`.

Errors:
- 400 if patient balance ≤ 0: `"No outstanding balance."`
- 400 if `delivery_method=email` and patient has no email address: `"Patient has no email address on file."`
- 502 if SES fails (statement row not created — transaction rolled back).

**Statement history:**
```
GET /api/v1/patients/{patient_id}/statements
```
Returns list of past statements for this patient, most recent first. Used by the Ledger tab statement history section.

**Preview (no record created):**
```
GET /api/v1/patients/{patient_id}/statements/preview
```
Generates and returns PDF bytes without recording a statement row. Lets staff review what the statement looks like before sending.

---

## 4. PDF Generation

### 4.1 Service structure

New directory: `apps/api/app/services/statements/`

**`aging.py`**
- `bucket_ledger_entries(entries: list[LedgerEntry]) -> AgingBreakdown` — pure function. Splits charge entries into four age buckets by `posted_at`; sums all payments and adjustments as `credits_cents`. Returns `AgingBreakdown` dataclass.
- `get_patient_aging_worklist(session, practice_id, min_balance_cents, sort_by) -> list[PatientAgingRow]` — single SQL query returning all patients with outstanding balance above threshold, with aging breakdown and last statement metadata.

**`pdf.py`**
- `generate_statement_pdf(practice, patient, entries, aging: AgingBreakdown) -> bytes` — renders the Jinja2 HTML template and passes through WeasyPrint, returns raw PDF bytes.
- `send_statement_email(patient, pdf_bytes, practice) -> str` — wraps the existing `send_email()` service, attaches PDF as base64-encoded MIME attachment. Returns SES MessageId. Subject: `"Statement from {practice.name}"`.

**`templates/statement.html`** — Jinja2 template. Layout:

1. **Header:** Practice name, address, phone number (right-aligned logo placeholder)
2. **Patient address block:** Patient name + address lines, positioned for a windowed envelope
3. **Statement metadata:** Statement Date, Account (short patient ID)
4. **Aging summary table:**

   | Current | 31–60 Days | 61–90 Days | 90+ Days | **Amount Due** |
   |---|---|---|---|---|
   | $X | $X | $X | $X | **$X** |

5. **Call-to-action:** *"Please contact our office at [phone] to arrange payment."*
   — Template includes a commented placeholder line: `{# pay_url: add payment URL here when patient portal launches #}`
6. **Itemized table:** Date | Description | Charges | Credits | Balance — one row per live ledger entry (reversals and their reversed entries excluded), running balance column, oldest-first order.
7. **Footer:** Practice phone number, *"Thank you for choosing [Practice Name]."*

### 4.2 Dependencies

**`requirements.txt`** additions:
- `weasyprint`
- `jinja2` (likely already present — verify)

**Dockerfile** (`apps/api/Dockerfile`) additions to the `apt-get install` line:
```
libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev
```

### 4.3 `email_opt_out` handling

Patients with `email_opt_out = True` still receive statements sent by email. The opt-out flag governs marketing and appointment reminders (see `reminder_worker.py`); a billing statement is a transactional communication. This distinction is enforced in `send_statement_email()` with a comment explaining why the opt-out check is intentionally skipped.

---

## 5. Frontend

### 5.1 New page: `/billing/patient-aging`

File: `apps/web/app/(app)/billing/patient-aging/page.tsx`

Table columns: Patient | Current | 31–60 days | 61–90 days | 90+ days | Total | Last Statement | Actions

- **Actions per row:** "Send Email" button (disabled + tooltip if patient has no email) and "Download PDF" button. Both call `POST /statements` and show a Sonner toast on success/error.
- **Last Statement** column: relative timestamp ("3 days ago") or "Never".
- **Sorting:** Total balance (default), Last Statement date.
- **Min-balance filter:** Default $5. A "Show all" toggle reveals patients with smaller balances.
- **Patient name** is a link to the patient chart.

### 5.2 Billing dashboard update

The existing "Patient A/R" tile in `apps/web/app/(app)/billing/page.tsx` (currently subtitled "Statements coming soon"):
- Drop the "coming soon" subtitle.
- Link the tile to `/billing/patient-aging`.

### 5.3 Patient Ledger tab additions (`LedgerTab.tsx`)

**Two new buttons** in the tab header (alongside "Record Payment" / "Add Adjustment"):
- **"Preview Statement"** — fetches the preview endpoint and opens the PDF in a new tab.
- **"Send Statement"** — opens a small dialog with two options: "Send by email to [patient.email]" and "Download PDF". Disabled states: "Send by email" is disabled with a tooltip if patient has no email on file; both are disabled with a tooltip if patient has no outstanding balance.

**Statement History section** — collapsible, below the ledger table. Lists past statements: date, delivery method (Email / Downloaded), sent by user. Populated by `GET /patients/{id}/statements`.

### 5.4 New API client

File: `apps/web/lib/api/statements.ts`

TanStack Query hooks:
- `usePatientStatements(patientId)` — GET statement history
- `useSendStatement()` — mutation for POST (handles both email and download; for download, triggers browser file save from response bytes)
- `usePatientAgingWorklist(params)` — GET aging worklist with sort/filter params

---

## 6. Testing

### Unit tests

**`test_aging.py`**
- `bucket_ledger_entries` with charges across all four buckets plus payments: assert correct bucket assignment and credits total.
- All entries on the same day (all in Current bucket).
- Zero balance → excluded from worklist.
- Credit balance (balance < 0) → excluded from worklist.

**`test_pdf.py`**
- `generate_statement_pdf` returns non-empty bytes.
- Rendered HTML contains practice name, patient name, and at least one charge row.
- WeasyPrint call is mocked — no real PDF rendering in CI.

### Router tests

**`test_statements_router.py`**
- POST email: mock `send_email`, assert statement row created with `delivered_at` set, returns 200 with `statement_id`.
- POST download: assert PDF bytes returned as `application/pdf`, statement row created with `delivered_at` null.
- POST with balance = 0: assert 400.
- POST email with no patient email: assert 400.
- GET list: assert ordering (most recent first), correct practice scoping (cannot see another practice's statements).
- GET preview: assert PDF bytes returned, no statement row created.

### Integration tests

**`test_patient_aging.py`**
- Seed practice + 3 patients with charges across different age ranges. Assert worklist returns correct bucket breakdowns, correct ordering by balance, patients with zero balance excluded, `min_balance_cents` filter respected.
- Assert `last_statement_at` populates correctly after a statement is generated.

---

## 7. Deferred

- **Online payment URL in statement CTA** — commented placeholder in the template; add when patient portal (Phase 5.2) is built.
- **Batch send** — send statements to all patients with a balance in one action. Deferred; the worklist row-by-row workflow is sufficient for a single practice.
- **Statement attachments / read receipt** — no delivery tracking beyond `delivered_at` (SES accepted the send). Bounce/open tracking deferred.
- **Guarantor/family billing** — `guarantor_account_id` on `ledger_entries` is unused; statement is always per individual patient. Family billing is a future 8b+ slice.
- **Overpayment/refund workflows** — patients with a credit balance (< 0) are excluded from the worklist. Refund handling is a separate deferred item.
- **Patient portal self-service** — patients cannot view or download their own statements yet.
