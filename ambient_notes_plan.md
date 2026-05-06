# Ambient Clinical Notes Plan (4.1)

## Scope

Post-procedure dictation that turns a dentist's spoken words into a structured clinical note draft. The dentist speaks for ~60 seconds after completing a procedure; the system transcribes it, extracts structured fields, and pre-populates the existing clinical note form for review and confirmation.

Not fully autonomous — staff reviews and confirms every note before it is saved. The save path is identical to a manually typed note.

---

## Architecture Overview

```
Browser (clinical note page)
     |
     | POST /api/v1/clinical-notes/ambient-draft
     | (multipart/form-data, audio bytes)
     v
Main FastAPI backend (audio held in memory only — never persisted)
     |
     +──► Whisper service (internal VPC, EC2 t3.medium)
     |         returns: transcript text
     |
     +──► Claude API (Haiku 4.5, tool use, prompt caching)
               returns: structured JSON matching clinical note fields
     |
     v
Draft JSON returned to browser
     |
     v
Clinical note form pre-filled, AI-populated fields highlighted
     |
     v
Dentist reviews, edits, confirms → existing POST/PATCH clinical note endpoint
     (same save path as a manually typed note)
```

---

## Components

### 1. Whisper Service

A lightweight FastAPI wrapper around the Whisper model, deployed as a separate service inside the private VPC. Not publicly exposed.

**Hosting:** Always-on EC2 `t3.medium` (~$30/month). Model loads once at startup. Cold start is not acceptable for a real-time workflow.

**Model:** `medium.en` — good accuracy on medical/dental terminology, runs on CPU without GPU, ~2–3s latency for a 60-second audio clip.

**Endpoint:**
- `POST /transcribe` — accepts audio bytes (WAV or WebM), returns transcript text
- `GET /health` — liveness check

**Audio handling:**
- Audio bytes are received in memory and passed directly to the Whisper model
- Never written to disk, never logged, discarded immediately after transcription
- No queue, no retry storage — if the call fails the frontend prompts the dentist to re-record

**Security:**
- Listens on the private VPC subnet only — no internet exposure
- No auth needed (VPC-internal, main backend is the only caller)
- Does not log audio data or transcripts

---

### 2. Claude Integration

Called from the main FastAPI backend immediately after Whisper returns the transcript.

**Model:** `claude-haiku-4-5-20251001` — structured extraction is well within Haiku's capability; no reasoning required.

**Prompt caching:** The system prompt is static and large (~500 tokens). It is sent with `cache_control: ephemeral` on every call. After the first call per cache window, subsequent calls read from cache at 1/10th the input token cost.

**Structured output via tool use:** Claude is given a single tool definition (`extract_clinical_note`) that defines the exact fields to populate. This guarantees a valid JSON shape every time — no free-form parsing.

**Tool schema:**
```json
{
  "name": "extract_clinical_note",
  "description": "Extract structured clinical note fields from a dental dictation transcript",
  "input_schema": {
    "type": "object",
    "properties": {
      "procedure_description": {
        "type": "string",
        "description": "Free-text narrative of the procedure performed"
      },
      "cdt_codes": {
        "type": "array",
        "items": { "type": "string" },
        "description": "CDT procedure codes mentioned (e.g. D2391, D7210)"
      },
      "tooth_numbers": {
        "type": "array",
        "items": { "type": "integer" },
        "description": "Tooth numbers referenced using Universal Numbering System (1-32)"
      },
      "surfaces": {
        "type": "array",
        "items": { "type": "string", "enum": ["M", "O", "D", "B", "L", "F", "I"] },
        "description": "Tooth surfaces involved"
      },
      "anesthesia_type": {
        "type": "string",
        "description": "Type of anesthesia administered (e.g. 'lidocaine 2% with epi 1:100,000')"
      },
      "anesthesia_amount": {
        "type": "string",
        "description": "Amount of anesthesia given (e.g. '1.8ml', '2 carpules')"
      },
      "patient_tolerance": {
        "type": "string",
        "enum": ["excellent", "good", "fair", "poor"],
        "description": "Patient tolerance during procedure"
      },
      "complications": {
        "type": "string",
        "description": "Any complications or notable findings. Empty string if none."
      },
      "follow_up_instructions": {
        "type": "string",
        "description": "Post-procedure instructions given to patient"
      },
      "next_appointment_note": {
        "type": "string",
        "description": "Anything the dentist flagged for the next visit"
      }
    },
    "required": ["procedure_description", "cdt_codes", "tooth_numbers"]
  }
}
```

**System prompt (static, cached):** Explains Universal Numbering System, common CDT code patterns for dental dictations, surface abbreviations, and instructs Claude to extract only what is explicitly stated — never infer or guess.

**Call pattern:**
```python
import anthropic

client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1024,
    system=[
        {
            "type": "text",
            "text": DENTAL_NOTE_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"}
        }
    ],
    messages=[{"role": "user", "content": f"Transcript: {transcript}"}],
    tools=[DENTAL_NOTE_TOOL_SCHEMA],
    tool_choice={"type": "tool", "name": "extract_clinical_note"}
)

draft = response.content[0].input  # always the tool call input
```

---

### 3. Backend API Endpoint

`POST /api/v1/clinical-notes/ambient-draft`

**Auth:** Standard practice auth — dentist or hygienist role required. Appointment ID is required in the body to scope the draft to the correct visit.

**Request:** `multipart/form-data`
- `audio`: audio file bytes (WAV or WebM, max 10MB)
- `appointment_id`: UUID

**Flow:**
1. Validate appointment belongs to the requesting practice
2. Forward audio bytes (in memory) to Whisper service
3. Receive transcript text; discard audio bytes
4. Call Claude with transcript; receive structured JSON
5. Write audit log entry: `ambient_transcription_used`, `appointment_id`, `user_id`, `timestamp` — no audio, no transcript
6. Return draft JSON to frontend

**Response:**
```json
{
  "draft": {
    "procedure_description": "...",
    "cdt_codes": ["D2391"],
    "tooth_numbers": [14],
    "surfaces": ["O", "D"],
    "anesthesia_type": "lidocaine 2% with epi 1:100,000",
    "anesthesia_amount": "1.8ml",
    "patient_tolerance": "good",
    "complications": "",
    "follow_up_instructions": "...",
    "next_appointment_note": ""
  },
  "transcript": "..."
}
```

The raw transcript is returned alongside the structured draft so the dentist can reference it while reviewing. It is not stored server-side.

**Error handling:**
- Whisper service unavailable → 503, frontend shows "Transcription service unavailable — please type your note manually"
- Claude API error → 503, same message
- Audio too large or wrong format → 400 with specific message
- All errors are generic to the caller; full error is logged server-side

---

### 4. Frontend UI

**Record button** on the existing clinical note form — placed near the top of the note-entry area.

**States:**

| State | UI |
|---|---|
| Idle | Microphone button |
| Recording | Red pulsing indicator, "Stop" button, elapsed timer |
| Processing | Spinner, "Transcribing…" label |
| Draft ready | Form fields populated, AI badge on each pre-filled field |
| Error | Toast with message, form remains blank for manual entry |

**AI field highlighting:**
- Each field populated by AI shows a small `AI` badge (subtle, not alarming)
- Badge disappears once the dentist edits that field
- A banner at the top of the form: "Review AI-generated draft — verify all fields before saving"
- The banner is dismissed on save, not manually

**Save flow:** Identical to manual note entry. The draft just pre-populates the form. The save button calls the existing clinical note create/update endpoint — there is no separate "confirm AI draft" endpoint.

**Transcript drawer:** A collapsible panel below the form shows the raw transcript. Dentist can reference it while reviewing fields. Not editable — read only.

**Audio recording:**
- `MediaRecorder` API with `audio/webm` MIME type (broad browser support)
- Recording capped at 3 minutes — dental dictations do not exceed this; if the dentist goes over, recording stops automatically and the clip is submitted
- Audio bytes are sent as multipart upload on stop; never stored in browser storage or IndexedDB

---

## Cost Model

**Whisper (self-hosted EC2 `t3.medium`):** ~$30/month flat across all customers.

**Claude (Haiku 4.5 with prompt caching):**

| Token type | Per call | Cost at $0.80/MTok input, $4/MTok output |
|---|---|---|
| System prompt (cached read) | ~500 tokens | ~$0.00004 |
| Transcript input | ~300 tokens | ~$0.00024 |
| Output | ~400 tokens | ~$0.0016 |
| **Total per note** | | **~$0.002** |

| Scale | Notes/month | Claude cost/month |
|---|---|---|
| 10 practices | 6,000 | ~$12 |
| 50 practices | 30,000 | ~$60 |
| 100 practices | 60,000 | ~$120 |

Claude cost is negligible per practice (<$1.50/month). The EC2 is the meaningful fixed cost.

---

## HIPAA Surface Area

| Data | Handling |
|---|---|
| Audio bytes | In-memory only; discarded immediately after Whisper call |
| Transcript text | Returned to frontend, not stored server-side |
| Structured note draft | Returned to frontend; only persisted after dentist confirms save |
| Audit log | Records that ambient transcription was used (who, when, appointment) — no audio, no transcript |
| Whisper service | VPC-internal only, no internet exposure |
| Claude API | Anthropic has a HIPAA BAA available; transcript is PHI — BAA required before production |

**Note:** A BAA with Anthropic must be in place before sending transcripts to the Claude API in production. Anthropic offers BAAs under their API enterprise agreements.

---

## Build Order

| Step | What | Notes |
|---|---|---|
| 1 | Whisper service | FastAPI wrapper, `medium.en` model, `/transcribe` + `/health` endpoints, Docker image |
| 2 | EC2 deployment | `t3.medium`, private subnet, security group allows inbound from main backend only |
| 3 | Backend draft endpoint | `/ambient-draft`, Whisper call, Claude call, audit log, error handling |
| 4 | Claude tool schema + system prompt | Tool definition, dental system prompt, prompt caching wired up |
| 5 | Frontend record UI | MediaRecorder, state machine, upload on stop |
| 6 | Draft population + AI highlighting | Pre-fill form fields, AI badges, transcript drawer, review banner |
| 7 | Integration test | End-to-end with a real dictation sample; verify audio is not persisted anywhere |
| 8 | Anthropic BAA | Required before production — initiate early, it can take time |

---

## Open Questions

- **Whisper service region:** Should the Whisper EC2 be in the same region as the main backend? Yes — minimize latency on the internal call and keep data in one region for HIPAA simplicity.
- **Claude model upgrade path:** If Haiku accuracy is insufficient for dental terminology, the model string is the only change needed to move to Sonnet. Build the config so this is a one-line change.
- **Transcript retention:** Currently not stored. If dentists want a "what I said" reference later, this would require treating the transcript as PHI and storing it encrypted alongside the note. Decide before build step 3.
- **Multi-language:** Out of scope. `medium.en` is English-only. If non-English practices become a segment, `medium` (multilingual) is a drop-in swap.
