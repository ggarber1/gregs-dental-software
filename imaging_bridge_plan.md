# Imaging Bridge Plan

## Scope

A button on the patient chart that opens the patient's record in their imaging software. No images are displayed inside Molar. Molar's job is to launch the right software with the right patient pre-selected — nothing more.

This replaces the manual workflow of: open imaging software → search for patient by name → select correct patient.

---

## Architecture Overview

Dental imaging software is a native Windows (or Mac) desktop application. A browser-based PMS cannot write files to disk or launch processes directly. A lightweight local bridge agent is required on each imaging workstation.

```
Molar Web App
     |
     | POST /open-patient (localhost)
     v
Bridge Agent (local Windows service)
     |
     | writes temp file + launches exe
     v
Imaging Software (Sidexis, DEXIS, Romexis, etc.)
     |
     | reads file, opens patient
     v
Staff sees correct patient in imaging software
```

The bridge agent is the only piece that needs to be installed on workstations. The rest is handled server-side (patient data) and in the web app (button UI).

---

## Components

### 1. Bridge Agent (local Windows service)

A small Go executable that runs as a Windows service on imaging workstations.

**Endpoints:**
- `GET /health` — returns `{ platform, version, ready: true/false }`. Used by the web app to detect whether imaging software is installed on the current workstation.
- `POST /open-patient` — accepts patient data, writes the bridge file, and launches the imaging software.

**Request body for `/open-patient`:**
```json
{
  "platform": "sidexis4",
  "patient": {
    "last_name": "Smith",
    "first_name": "John",
    "dob": "1980-03-15",
    "chart_num": "P001234",
    "pat_num": "42"
  }
}
```

**Config file** (`bridge-config.json`, sits next to the executable):
```json
{
  "platform": "sidexis4",
  "executable_path": "C:\\Program Files\\Sidexis 4\\Sidexis4.exe",
  "mailbox_path": "C:\\ProgramData\\Sidexis\\Bridge\\molar.sdx"
}
```

Platform is set once during installation. Changing platforms means editing the config and restarting the service.

**Security:**
- Listens on `127.0.0.1` only — not accessible from outside the machine
- No auth needed (localhost only, workstation-scoped)
- Does not log patient data

---

### 2. Platform Handlers (inside the bridge agent)

Each imaging platform has its own handler that implements:
```
WritePatientFile(config, patient) error
LaunchSoftware(config) error
```

#### Sidexis 4 (SLIDA protocol) — Phase 2.6 initial target

Sidexis uses the SLIDA (SIDEXIS Link to Dental Applications) file-based bridge.

**How it works:**
1. Bridge agent writes a `.sdx` file to a configured mailbox path
2. Sidexis watches the mailbox path and picks up the file
3. Sidexis opens the matching patient (matched by name + DOB)

**File format** (SLIDA spec):
```
[A]
LN=Smith
FN=John
BD=15.03.1980
```
- `[A]` = Autoselect section (triggers patient selection without UI prompt)
- `LN` = last name
- `FN` = first name  
- `BD` = birthdate in `dd.mm.yyyy` format (European standard — Sidexis requires this exact format)

**Config values needed:**
- `mailbox_path`: full path to the `.sdx` file Sidexis is watching (configured in Sidexis under Options → Program Interfaces)
- No executable launch needed — Sidexis must already be running. If it's not running, the bridge returns an error.

**Known limitation:** Sidexis must be open before clicking the button. The SLIDA bridge does not launch Sidexis — it only selects a patient within an already-running instance. Surface this in the UI.

---

#### DEXIS (Integrator) — Phase 2.6 follow-on

DEXIS uses the DEXIS Integrator, a separate helper process. Communication is via DDE or a text file written to a configured path.

**File format:**
```
PatNum=42
ChartNum=P001234
LName=Smith
FName=John
Birthdate=1980-03-15
```
DEXIS Integrator reads this file, selects the patient in DEXIS, and opens their images.

**Config values needed:**
- `integrator_path`: path to the Integra.ini-configured watch directory

---

#### Romexis (PMBridge / DxStart) — Phase 2.6 follow-on

Planmeca's Romexis supports two methods:
1. **PMBridge**: file-based bridge, similar pattern to Sidexis
2. **DxStart.exe**: CLI args — `DxStart.exe /patient:"Smith,John" /dob:"1980-03-15"`

Prefer DxStart for simplicity: no file writing, just a process launch with args.

**Config values needed:**
- `executable_path`: path to DxStart.exe
- No separate config file needed

---

#### Apteryx XVWeb — deferred (DSO / multi-location target)

Apteryx XVWeb is cloud-native and owned by Planet DDS (who also makes Denticon, a competing PMS). It has strong adoption in DSOs and multi-location groups but low penetration in solo/small practices — the primary Molar market at this stage.

When it becomes a priority: integration is a direct HTTP API call from the Molar backend — no local agent involved. The "Open in Apteryx" button calls a Molar API endpoint, which calls the Apteryx REST API with the patient's chart number. Apteryx returns a URL; the browser opens it in a new tab. Requires a Planet DDS developer/partner account.

Add this when Molar is actively selling into DSOs or multi-location practices.

---

### 3. Patient Chart UI

**"Open in Imaging Software" button** on the patient chart (alongside other action buttons).

**States:**
- **Hidden** — `GET http://localhost:8732/health` fails or returns `ready: false`. No bridge installed on this workstation.
- **Enabled** — bridge is healthy and platform is configured.
- **Loading** — request in flight.
- **Error** — bridge returned an error (e.g. "Sidexis is not running"). Show a toast with the error message.

The health check runs once on page load and is cached for the session. No polling.

**For Sidexis specifically:** show a tooltip/note on the button: "Sidexis must be open before clicking."

---

### 4. Backend API endpoint

`POST /api/patients/:patient_id/open-imaging`

- Validates the patient belongs to the requesting practice (auth check)
- Fetches the patient's name, DOB, chart number from the DB
- Returns the patient data payload — the web app forwards this to the local bridge agent

The backend does not call the bridge agent directly. The browser calls localhost; the backend just supplies the patient data so the frontend doesn't need direct DB access.

**Response:**
```json
{
  "patient": {
    "last_name": "Smith",
    "first_name": "John", 
    "dob": "1980-03-15",
    "chart_num": "P001234",
    "pat_num": "42"
  }
}
```

---

### 5. Patient ID mapping

Imaging software maintains its own patient database. Matching is done by **name + DOB** (the approach used by Sidexis SLIDA and most file-bridge platforms).

This means:
- No additional column on the `patients` table needed for the initial implementation
- If the imaging software has two patients with the same name + DOB (rare), it will prompt the staff to select — acceptable behavior
- If a patient was entered with a different name spelling in the imaging software, matching will fail — staff will need to manually find the patient in that case

A future improvement (out of scope for now) would be a stored `imaging_patient_id` mapping per platform per practice, populated after the first successful bridge launch.

---

## Platform Priority

| Priority | Platform | Market | Reason |
|----------|----------|--------|--------|
| 1 | Sidexis 4 | Solo/small — Schick hardware practices | Most likely for initial practices; Dentsply Sirona dominant in this segment |
| 2 | DEXIS | Solo/small — Henry Schein ecosystem | Largest overall install base in traditional practices |
| 3 | Romexis | Solo/small — Planmeca hardware practices | Meaningful share, especially outside Henry Schein-supplied practices |
| 4 | Apteryx XVWeb | DSO / multi-location | Add when targeting groups; owned by a competing PMS vendor |

---

## Build Order

| Step | What | Notes |
|------|------|-------|
| 1 | Bridge agent skeleton | Go service, health endpoint, config loading, localhost only |
| 2 | Sidexis 4 handler | SLIDA file write, error if Sidexis not running |
| 3 | Backend API endpoint | `POST /api/patients/:id/open-imaging`, auth + data fetch |
| 4 | Frontend button | Health check on load, calls backend then bridge |
| 5 | DEXIS handler | Add to bridge agent |
| 6 | Romexis handler | Add to bridge agent |
| 7 | Apteryx XVWeb | Separate track — deferred until DSO market |
| 8 | Windows installer | MSI or simple .exe with install script, config wizard |

Steps 1–4 deliver a working Sidexis integration. Steps 5–6 are additive handlers with no architectural changes.

---

## Open Questions

- **Which imaging platform is dad's practice migrating to?** Sidexis 4 is the most likely given existing Schick hardware, but confirm before step 2.
- **Apteryx XVWeb API access:** Deferred. When relevant, requires a Planet DDS partner/developer account. Note that Planet DDS (Denticon) is a competing PMS — assess partnership viability at that time.
- **Mac support:** Sidexis 4 is Windows-only. If any practices run Mac workstations, Romexis (Java, runs on Mac) and Apteryx XVWeb are the relevant platforms. Bridge agent would need a Mac build.
- **Bridge agent distribution:** How does the agent get installed on workstations? Options: manual download from a practice settings page, or a proper MSI installer. Decide before step 8.
