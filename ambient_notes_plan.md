# Ambient Clinical Notes Plan (4.1)

## Gate status

Dad's "Post Review" input in `longterm_build_plan.md` confirmed the note structure:
> "Notes should just be a single textbox that user can have templates for"

The current `ClinicalNoteEditor` implements exactly that — one `treatmentRendered` textarea, template chips, sign-and-lock. The gate is cleared. This feature can be built on top of the existing form without structural changes to the note model or editor.

---

## What this ships

A microphone button appears in the New Clinical Note editor. The dentist dictates post-procedure. The app transcribes the audio, runs it through a Bedrock-hosted Haiku call, and pre-fills the note textarea with a formatted draft. The dentist reviews, edits if needed, and saves/signs as normal. Nothing is autonomous — the dentist always has the last word.

---

## Architecture

```
Browser (MediaRecorder API)
     |
     | POST /api/v1/patients/{id}/ambient-note-draft
     | multipart/form-data: audio blob + optional template_hint
     v
Molar API (FastAPI, ECS)
     |
     | POST /transcribe (internal VPC only)
     v
Whisper Service (EC2, private subnet)
     |  faster-whisper, audio bytes → transcript string
     |  audio never written to disk
     v
Molar API
     |
     | InvokeModel (Bedrock, claude-haiku-3-5)
     | transcript + template hint → draft note text
     v
Browser
     | draft pre-filled into treatmentRendered textarea
     | yellow "AI draft — review before saving" banner
     v
Dentist edits, saves draft or signs
```

---

## Components

### Module 4.1-A: Whisper transcription service (`apps/whisper/`)

A standalone FastAPI service that runs on a private EC2 instance. It has one job: receive audio bytes, run Whisper, return transcript text. It never sees PHI beyond the audio itself, and the audio bytes are never written to disk.

**Files:**
- `apps/whisper/app/main.py` — FastAPI app with two endpoints
- `apps/whisper/app/transcriber.py` — loads the model on startup, exposes `transcribe(audio_bytes) -> str`
- `apps/whisper/Dockerfile`
- `apps/whisper/requirements.txt`

**Endpoints:**
```
GET  /health        → { "status": "ok", "model": "large-v3-turbo" }
POST /transcribe    → multipart: audio (bytes) → { "transcript": "..." }
```

**Whisper config:**
- Library: `faster-whisper` (4× faster than openai-whisper, same model weights)
- Model: `large-v3-turbo` — best quality/speed tradeoff for English dental dictation
- Language: hardcoded `en` (skip language detection, saves ~1s)
- Compute: CPU-only to start (`c5.xlarge` or `t3.large`)
  - At one practice, CPU is fine: expected 2–5 dictations/hour, ~30s per 2-min clip on c5.xlarge
  - Upgrade path: swap to `g4dn.xlarge` (CUDA) when latency becomes a complaint
- Model loaded at startup into memory, reused across requests (no cold load per request)
- Audio is consumed as `bytes` from the request body, passed to `faster-whisper` via a `BytesIO` buffer — no temp files

**Security:**
- No public ingress — internal VPC security group only
- API ECS task SG → Whisper EC2 SG, port 8080
- No auth on the Whisper service (it's only reachable from the API)

**Tests (`apps/whisper/tests/`):**
- `test_transcriber.py`: mock `faster-whisper`, assert transcript returned; assert no temp file created
- `test_main.py`: `TestClient` health check, mock transcriber for transcribe endpoint

---

### Module 4.1-B: Ambient notes API endpoint (`apps/api/`)

A new router mounted on the existing FastAPI app. Orchestrates the Whisper → Bedrock pipeline. Same auth/audit middleware as everything else.

**New files:**
- `apps/api/app/routers/ambient_notes.py` — the endpoint
- `apps/api/app/services/whisper_client.py` — async HTTP client for the Whisper service
- `apps/api/app/services/bedrock_extraction.py` — Bedrock call, prompt, caching

**Modified files:**
- `apps/api/app/core/config.py` — add `WHISPER_ENDPOINT_URL: str`
- `apps/api/app/main.py` — register the new router

**Endpoint:**
```
POST /api/v1/patients/{patient_id}/ambient-note-draft
Content-Type: multipart/form-data

Fields:
  audio         (file, required)  — WebM, MP3, WAV, M4A; max 25 MB
  template_hint (str, optional)   — one of the TemplateType enum values

Response 200:
  {
    "draft": "CC: Restoration\nAnesthesia: ...",
    "detected_template": "filling"   // may differ from hint; null if unknown
  }

Response 400: audio too large, unsupported format
Response 502: Whisper service unreachable
Response 504: pipeline timed out
```

**Auth:** same `_require_practice_scope` + `_require_write_role` guards as clinical notes. Patient scoping is enforced (patient must belong to the practice).

**Pipeline in the handler:**
1. Validate file size (< 25 MB) and content-type
2. Read audio bytes into memory (never to disk)
3. Call `whisper_client.transcribe(audio_bytes)` — timeout 90s
4. Call `bedrock_extraction.draft_note(transcript, template_hint)` — timeout 15s
5. Return draft and detected template type
6. Audio bytes go out of scope — GC'd

**`whisper_client.py`:**
- `httpx.AsyncClient` with 90s read timeout
- Posts audio bytes as multipart to `{WHISPER_ENDPOINT_URL}/transcribe`
- Raises `WhisperUnavailableError` on connection error → endpoint returns 502
- Raises `WhisperTimeoutError` on timeout → endpoint returns 504

**`bedrock_extraction.py`:**
- `boto3` `bedrock-runtime` client, region `us-east-1`
- Model: `anthropic.claude-haiku-3-5` (latest Haiku via Bedrock)
- Prompt caching: system prompt + template block on `cache_control: ephemeral`
  - Cache TTL is 5 min (Bedrock Haiku); reused across concurrent dictations
- Tool use (structured output):

```python
tools = [{
    "name": "format_clinical_note",
    "description": "Format a dental clinical note from dictation",
    "input_schema": {
        "type": "object",
        "properties": {
            "draft": {
                "type": "string",
                "description": "Formatted note text, matching the practice template style"
            },
            "detected_template": {
                "type": "string",
                "enum": ["exam", "prophy", "extraction", "crown_prep", "crown_seat",
                         "root_canal", "filling", "srp", "other"],
                "description": "Best-fit template type for this note"
            }
        },
        "required": ["draft", "detected_template"]
    }
}]
```

- System prompt (cached):
  ```
  You are a dental clinical note assistant for a private dental practice.
  Given a dentist's post-procedure dictation transcript, produce a structured
  clinical note in the practice's standard format.

  Note format (single text block):
  CC: <chief complaint or reason for visit>
  Anesthesia: <what was used, dose, or "None">
  Treatment: <procedure performed, CDT code in parentheses, tooth number if applicable>
  Next visit: <follow-up plan>

  Rules:
  - Fill in tooth numbers, CDT codes, and surface notation from context clues in the transcript
  - If the dentist says "two carpules" of lidocaine, write "Lidocaine 2% 1:100,000 epinephrine, 3.4 mL"
  - Mirror the template examples: concise, clinical, no first-person
  - If any field is unclear from the transcript, leave it at a short placeholder (e.g., "tooth #___")
  - Identify the best-fit template type from: exam, prophy, extraction, crown_prep,
    crown_seat, root_canal, filling, srp, other
  ```
  
  Template examples (cached, appended to system prompt to anchor style)

**Tests (`apps/api/tests/routers/test_ambient_notes.py`):**
- Happy path: mock Whisper client + mock Bedrock → assert 200, draft in response
- Audio too large → 400
- Wrong content-type → 400
- Patient not found → 404
- Whisper unreachable → 502
- Whisper timeout → 504
- Auth: unauthenticated → 401, wrong practice → 404

---

### Module 4.1-C: Frontend recording UI (`apps/web/`)

A new `AmbientNoteRecorder` component embedded in `ClinicalNoteEditor`. It only appears when creating a new (unsigned) note. It does not appear in edit or sign-review mode.

**New file:**
`apps/web/components/patients/AmbientNoteRecorder.tsx`

**Modified file:**
`apps/web/components/patients/ClinicalNoteEditor.tsx` — import and embed recorder in the new-note path

**Recorder states and UI:**

```
idle         → [🎤 Dictate] button
requesting   → requesting mic permission (browser prompt)
recording    → [⏹ Stop] button + red dot + elapsed timer (MM:SS)
processing   → spinner + "Transcribing…"
done         → yellow banner "AI draft — review before saving" (dismissible)
error        → inline error message + [Try again] link
```

**Key behaviors:**
- Uses `navigator.mediaDevices.getUserMedia({ audio: true })` — requests mic permission on first click
- `MediaRecorder` with `mimeType: 'audio/webm;codecs=opus'` (fallback: `audio/webm`)
- Max recording: 10 minutes (timer shows remaining; stops automatically at 10:00)
- On "Stop": blobs concatenated into a single `Blob`, POSTed to the endpoint as FormData
- `template_hint` passed if a template chip is already selected
- On success: `setFields` to update `treatmentRendered` with draft; set banner visible
- The dentist can freely edit the draft before saving — it's just a textarea prefill
- Banner dismissed on any keystroke in the textarea

**API call (`apps/web/lib/api/clinical-notes.ts` or new file):**
```ts
async function fetchAmbientNoteDraft(
  patientId: string,
  audio: Blob,
  templateHint?: string,
): Promise<{ draft: string; detectedTemplate: string | null }>
```

**Tests (`apps/web/__tests__/components/patients/ambientNoteRecorder.test.ts`):**
- Happy path: mock `getUserMedia`, mock `MediaRecorder`, mock fetch → draft populated
- Permission denied → error state
- API error → error state shown, no crash

---

### Module 4.1-D: Infrastructure

**EC2 Whisper instance (Terraform: `infra/terraform/modules/whisper/`):**
```hcl
resource "aws_instance" "whisper" {
  ami           = "ami-0c7217cdde317cfec"  # Ubuntu 22.04 LTS, us-east-1
  instance_type = "c5.xlarge"              # 4 vCPU, 8 GB — sufficient for CPU Whisper
  subnet_id     = var.private_subnet_id
  vpc_security_group_ids = [aws_security_group.whisper.id]
  iam_instance_profile   = aws_iam_instance_profile.whisper.name

  user_data = file("${path.module}/user_data.sh")  # installs Docker, pulls whisper image
  
  tags = { Name = "molar-whisper-${var.env}" }
}

resource "aws_security_group" "whisper" {
  ingress {
    from_port       = 8080
    to_port         = 8080
    protocol        = "tcp"
    security_groups = [var.api_security_group_id]  # API ECS tasks only
  }
  egress { ... }  # allow outbound for model download on first boot
}
```

**SSM parameters (populated manually after `terraform apply`):**
```
/dental/{env}/whisper/endpoint_url   = "http://{whisper-private-ip}:8080"
```

**Bedrock IAM — add to API ECS task role:**
```json
{
  "Effect": "Allow",
  "Action": ["bedrock:InvokeModel"],
  "Resource": "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-haiku-3-5*"
}
```

**Config (`apps/api/app/core/config.py`):**
```python
WHISPER_ENDPOINT_URL: str = "http://localhost:8080"  # overridden by SSM in staging/prod
BEDROCK_REGION: str = "us-east-1"
BEDROCK_MODEL_ID: str = "anthropic.claude-haiku-3-5"
AMBIENT_NOTE_MAX_AUDIO_MB: int = 25
```

---

## HIPAA / security summary

| Concern | Decision |
|---|---|
| Audio storage | Never written to disk or DB anywhere in the pipeline; bytes flow through memory only |
| Transcript storage | Ephemeral in-request memory; not logged, not persisted |
| Bedrock | HIPAA-eligible service; covered under AWS BAA — no separate Anthropic BAA needed |
| Whisper EC2 | Private subnet only; no public IP; audio bytes handled in-process |
| Audit logging | Existing `AuditLogMiddleware` on all API requests; audio bytes not logged (content excluded by middleware's existing pattern) |
| Fallback if unavailable | Feature fails gracefully — dentist fills note manually as before |

---

## Implementation sequence

1. **Whisper service** (`apps/whisper/`) — write the FastAPI app, Dockerfile, tests; get it running locally against a sample WAV file
2. **Terraform** — add the Whisper EC2 module to staging; provision and populate SSM
3. **API config + client** — `config.py` additions, `whisper_client.py`, verify round-trip locally (Whisper service running in Docker)
4. **Bedrock extraction** — `bedrock_extraction.py`, test against Bedrock (staging has IAM); tune prompt until output matches template style
5. **Ambient notes endpoint** — `ambient_notes.py` router, register in `main.py`, write tests
6. **Frontend** — `AmbientNoteRecorder.tsx`, embed in `ClinicalNoteEditor`, test in browser
7. **End-to-end smoke test** — dictate a 30-second extraction description, verify the draft looks right

---

## Open questions before starting

- **HIPAA BAA**: `longterm_build_plan.md` notes this must be in place before going to production. Confirm the AWS BAA covers Bedrock in the account used for staging/prod. Start that confirmation now — it's not a blocker for building, but must be verified before onboarding dad's practice.
- **Whisper EC2 cost**: `c5.xlarge` ~$0.17/hr. Run it only during practice hours? A scheduled stop/start Lambda (pattern already exists for staging) could keep costs low. Decide before staging deploy.
- **Model download on first boot**: `large-v3-turbo` is ~1.5 GB. The user_data script needs to pull it on first boot (or bake an AMI). AMI is faster for practice use.
