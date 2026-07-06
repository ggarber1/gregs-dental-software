# Claim Attachments (275) — Design

**Date:** 2026-07-06
**Phase:** 3 — Billing & Insurance Depth
**Status:** Approved — ready for implementation plan
**Depends on:** Module 7a (claims submission, 837D builder, StediClaimsClient), Phase 2
perio charting (perio chart data model)

## 1. Scope

Claims for high-value dental procedures (crowns D2xxx, root canals D3xxx, perio surgery
D4xxx, implants D6xxx, impacted extractions D7210/7240) routinely require supporting
documentation before payers will adjudicate them. Without attachment support, staff must
submit these files separately via fax or payer portal — a manual out-of-system step for
a significant share of billed dollars at major-restorative and perio-heavy practices.

This spec closes that gap with:

1. **File storage** — S3-backed `appointment_attachments` table; files attach to the
   appointment (not the claim) so they survive resubmission and serve appeal workflows.
2. **Perio narrative auto-generation** — for appointments with D4xxx procedures and a
   recorded perio chart, generate a structured narrative attachment automatically at
   claim submission time; no manual upload required.
3. **Electronic 275 transmission via Stedi** — at claim submission, upload attachments
   to Stedi and include `attachmentId` references in the 837D JSON. Stedi routes both
   the claim and the 275 to the payer together.
4. **Payer fallback** — Stedi validates per-payer 275 support; for unsupported payers
   the claim goes through with an `attachmentControlNumber` reference and the UI prompts
   staff to submit files through the payer's portal.

**Out of scope:**
- Solicited attachments (277 RFA → 275 response workflow)
- Imaging software integration (Dexis, Carestream, etc.) — manual upload is the input
- Prior authorization (278) documentation
- Secondary / COB claim attachments

## 2. Why attach to appointments, not claims

Files exist before a claim is created and are reused on resubmission. Attaching at the
appointment level means:
- Staff uploads once; the file is available for the original claim, any resubmission, and
  future appeal documentation.
- No re-upload required when `resubmit_claim` creates a new submission attempt.
- The perio narrative (auto-generated) is naturally tied to the clinical encounter, not
  the billing transaction.

## 3. Data model — one migration

One new table. No changes to `claims`.

```sql
CREATE TABLE appointment_attachments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    practice_id     UUID NOT NULL,
    appointment_id  UUID NOT NULL REFERENCES appointments(id),
    s3_key          TEXT NOT NULL,
    file_name       TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    content_type    VARCHAR(50) NOT NULL,
    -- image/jpeg | image/png | application/pdf | image/tiff | text/plain
    attachment_type VARCHAR(30) NOT NULL,
    -- xray | photo | perio_narrative | lab_rx | other
    uploaded_by     TEXT NOT NULL,   -- user sub; "system" for auto-generated narratives
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_appt_attachments_appt ON appointment_attachments(appointment_id);
```

S3 key scheme: `{practice_id}/appointments/{appointment_id}/{attachment_id}/{filename}`

Accepted file types: `image/jpeg`, `image/png`, `application/pdf`, `image/tiff`.
Size limit: 64MB per file (Stedi's documented recommendation; some payers may be lower).

`attachment_type` → Stedi `attachmentReportTypeCode` (PWK01) mapping:

| attachment_type  | PWK01 | Description               |
|-----------------|-------|---------------------------|
| xray            | B4    | Radiology Reports         |
| perio_narrative | DG    | Diagnostic Report         |
| photo           | DA    | Dental Models/Photographs |
| lab_rx          | 77    | Referral/Prescription     |
| other           | OB    | Other                     |

## 4. File upload service

```
app/services/attachments/
  service.py    # upload_attachment, list_attachments, delete_attachment,
                # generate_perio_narrative
```

**`upload_attachment(session, practice_id, appointment_id, file, filename, content_type, attachment_type, user_sub)`**

1. Validate appointment belongs to `practice_id`.
2. Validate `content_type` is in the accepted set; raise `422` otherwise.
3. Generate `attachment_id = uuid4()`. Build `s3_key`.
4. Upload bytes to S3 (`boto3.put_object`, SSE-S3 encryption).
5. Insert `appointment_attachments` row. Return it.

**`delete_attachment(session, practice_id, attachment_id)`**

1. Fetch row, verify `practice_id`. Raise `404` if not found.
2. Delete from S3.
3. Delete row.

**`generate_perio_narrative(session, appointment_id)`** — called by the claims service
at submission time, not by staff.

1. Check if any `appointment_procedures` on this appointment have a CDT code matching
   `D4[0-9]{3}` (perio procedures).
2. If yes, query the perio chart for this appointment. If no chart recorded, return
   `None`.
3. Format a structured text narrative (pocket depths by sextant, furcation involvement,
   bone loss assessment, provider name, date of service).
4. Write the text as a `.txt` file to S3 under the same key scheme.
5. Insert an `appointment_attachments` row with `attachment_type = "perio_narrative"`,
   `uploaded_by = "system"`. Return the row.

## 5. Claims service extension

Changes to `app/services/claims/service.py` and `app/services/claims/stedi.py`.

### Pre-submission step in `submit_claim_for_appointment`

Before building the claim payload, the service:

1. **Auto-generate perio narrative** — calls `generate_perio_narrative` if not already
   present for this appointment (idempotent: checks for existing `perio_narrative` row
   before generating).
2. **Query attachments** — `SELECT * FROM appointment_attachments WHERE appointment_id = ?`
   → list of `AttachmentRef` objects.
3. **Upload to Stedi** (per attachment):
   a. Stream file from S3.
   b. POST to Stedi's Create Claim Attachment endpoint → receive `stediUploadUrl` +
      `stediAttachmentId`.
   c. PUT file bytes to `stediUploadUrl` with correct `Content-Type`.
   d. Collect `(attachment_type, stediAttachmentId)` pairs.
4. **Payer fallback** — if Stedi returns `TRANSACTION_TYPE_NOT_SUPPORTED` (400):
   - Skip Stedi upload for all attachments.
   - Generate a UUID `attachmentControlNumber` per attachment.
   - Set `payer_supports_275 = False`; carry `attachmentControlNumbers` forward.
5. Pass attachment references to `build_claim_input`.

### Builder extension (`builder.py`)

`build_claim_input` accepts two new optional kwargs:
- `attachment_ids: list[tuple[str, str]] | None` — `(attachmentReportTypeCode, stediAttachmentId)` pairs
- `attachment_control_numbers: list[tuple[str, str]] | None` — `(attachmentReportTypeCode, controlNumber)` pairs for the fallback path

These populate `claimInformation.claimSupplementalInformation.reportInformations` in the
Stedi JSON payload. `attachmentTransmissionCode` is always `"EL"`.

### Service response extension

`submit_claim_for_appointment` returns a new field alongside the `Claim` row:

```python
@dataclass
class ClaimSubmissionResult:
    claim: Claim
    attachments_sent_electronically: int   # count
    attachments_manual: list[str]          # filenames needing manual payer portal submission
    payer_supports_275: bool
```

## 6. API

New router: `app/routers/attachments.py`. Practice-scoped, write-role required for
upload/delete, read-role for list. Feature-gated on `claims_submission` (same gate as
the claims endpoints — attachments are only useful in the context of claims).

Schemas added to the Zod source and regenerated via `pnpm generate`.

```
POST   /api/v1/appointments/{appointment_id}/attachments
       Multipart form: file + attachment_type field.
       201 → AppointmentAttachment
       422 UNSUPPORTED_FILE_TYPE — content_type not in accepted set
       422 FILE_TOO_LARGE — > 64MB
       404 — appointment not in practice scope

GET    /api/v1/appointments/{appointment_id}/attachments
       200 → AppointmentAttachment[]
       404 — appointment not in practice scope

DELETE /api/v1/appointments/{appointment_id}/attachments/{attachment_id}
       204
       404 — not found or not in practice scope
```

`POST /appointments/{id}/claim` response body gains `ClaimSubmissionResult` fields:
`attachmentsSentElectronically`, `attachmentsManual`, `payerSupports275`.

## 7. Frontend

### Attachment panel (new — appointment view)

A new panel on the appointment page alongside the existing Claim and Eligibility panels.

Rows: filename, type badge (`X-ray` / `Photo` / `Lab Rx` / `Perio chart` / `Other`),
file size, uploaded-by. Auto-generated perio narrative rows show `Perio chart —
auto-generated` and have no delete button.

Upload: file picker filtered to `.jpg .png .pdf .tif .tiff`, 64MB limit. Multipart POST
on selection. File appears in list on success.

New hooks in `apps/web/lib/api/attachments.ts`:
- `useAppointmentAttachments(appointmentId)` → `GET`
- `useUploadAttachment(appointmentId)` → `POST`
- `useDeleteAttachment(appointmentId, attachmentId)` → `DELETE`

All mutations invalidate `attachmentsKeys.forAppointment(appointmentId)`.

### Claim panel extension (existing component)

**Pre-submission:** show an "Attachments" section listing files that will be sent with
this claim.

**Post-submission:** show result per attachment:
- `Sent electronically` — 275 went through Stedi.
- `Send manually` — payer doesn't support 275. Display:
  *"[Carrier] doesn't support electronic attachments. Upload these files to [Carrier]'s
  provider portal before your claim can be processed."*

On claim submission success, invalidate both the claim query and
`attachmentsKeys.forAppointment(appointmentId)`.

## 8. Testing

Per CLAUDE.md: new exported function or endpoint → happy path + one failure case.

### Unit (`tests/services/`)

**`upload_attachment`:**
- Happy path → S3 key written, row inserted, returned
- Unsupported content type → raises `422 UNSUPPORTED_FILE_TYPE`

**`generate_perio_narrative`:**
- Appointment with D4xxx procedure + perio chart → narrative text written to S3, row inserted
- Appointment with D4xxx procedure but no perio chart → returns `None`, no row inserted
- Idempotency: called twice → second call returns existing row, no second S3 write

**Builder extension:**
- `build_claim_input` with `attachment_ids` → `reportInformations` array present with correct `attachmentReportTypeCode` per type
- `build_claim_input` with no attachments → `reportInformations` absent from payload

**Stedi upload step in service:**
- Successful upload → `stediAttachmentId` collected and passed to builder
- Payer returns `TRANSACTION_TYPE_NOT_SUPPORTED` → fallback `attachmentControlNumber` used, `payer_supports_275 = False` in result
- S3 stream failure → `submission_failed` status, claim not submitted

### Endpoint tests (`tests/routers/`)

**`POST /appointments/{id}/attachments`:**
- Happy path → 201 with attachment record
- Unsupported content type → 422
- Appointment not in practice scope → 404

**`GET /appointments/{id}/attachments`:**
- Returns only that appointment's attachments; attachments from another practice not returned

**`DELETE /appointments/{id}/attachments/{id}`:**
- Happy path → 204, S3 object deleted
- Not found → 404

### Integration (ask before running)

Submit a sandbox claim with a JPEG attachment to a payer that supports 275 — verify
Stedi receives both 837D and 275, and the response includes the expected
`attachmentsSentElectronically` count.

## 9. Cross-references

- `2026-06-18-module-7a-claims-submission-design.md` — `StediClaimsClient`, `build_claim_input`, claim submission flow
- `2026-06-30-claim-recovery-appeals-design.md` — resubmission flow; attachments on `appointment_attachments` carry over to resubmissions automatically (no re-upload needed since they're appointment-scoped)
- Perio charting design decisions (memory) — perio chart data model that `generate_perio_narrative` reads from
- `longterm_build_plan.md` §Deferred — "Claim attachments (275)" item; update to IN PROGRESS / BUILT once shipped
