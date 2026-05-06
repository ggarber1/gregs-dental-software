# No-Show Risk Scoring Plan (4.2A)

## Scope

Rule-based risk score per appointment — low / medium / high — surfaced as a badge on the schedule view appointment card. High-risk appointments automatically receive an extra reminder. No ML training required; rule weights are based on established dental no-show research.

This is Feature A of 4.2. Feature B (waiting list) is a separate plan.

---

## Architecture

Score is stored on the `appointments` row (`no_show_risk` column) and recomputed nightly by a Lambda job. Computing on-the-fly per request would cause N+1 patient history queries on the schedule view — storing the score avoids this. Stale by at most one day, which is acceptable for a daily schedule.

```
EventBridge (2am nightly)
     |
     v
Risk Scoring Lambda
     |
     +──► Query upcoming appointments (next 7 days, all practices)
     |
     +──► Batch-fetch patient history (aggregate no-show/cancel counts per patient — one query)
     |
     +──► Batch-fetch reminder status per appointment (one query)
     |
     +──► compute_risk_score() → low | medium | high
     |
     +──► Write scores back to appointments table (batch UPDATE)
     |
     +──► For each high-risk appointment: queue extra reminder if not already queued
          (uses existing stage_reminder_jobs path → SQS → Twilio Lambda)

On confirmation (appointment status → 'confirmed'):
     Appointment router recomputes score immediately in the same transaction
     (confirmation is the biggest signal — same-day accuracy matters here)
```

---

## Risk Scoring Algorithm

Pure Python function. No DB calls inside — all inputs are passed in. Fully unit-testable.

### Inputs

```python
@dataclass
class PatientAppointmentHistory:
    total: int        # total past appointments
    no_show_count: int
    cancel_count: int

    @property
    def no_show_rate(self) -> float:
        return self.no_show_count / self.total if self.total else 0.0

    @property
    def cancel_rate(self) -> float:
        return self.cancel_count / self.total if self.total else 0.0
```

### Scoring Table

| Signal | Points |
|---|---|
| Patient no-show rate ≥ 33% (1-in-3 or worse) | +40 |
| Patient no-show rate 15–33% | +20 |
| Patient cancellation rate ≥ 33% | +15 |
| Patient cancellation rate 15–33% | +8 |
| Appointment still unconfirmed at scoring time | +25 |
| Monday or Friday | +10 |
| Early morning (< 9am) or end of day (≥ 4pm) | +10 |
| Booked with < 24h lead time | +10 |

### Buckets

| Score | Risk Level |
|---|---|
| ≥ 50 | `high` |
| 25–49 | `medium` |
| < 25 | `low` |

### Function Signature

```python
def compute_risk_score(
    appointment: Appointment,
    history: PatientAppointmentHistory,
    is_confirmed: bool,
    lead_time_hours: float,
) -> Literal["low", "medium", "high"]:
    ...
```

---

## Extra Reminder for High-Risk

When the nightly job scores an appointment as `high`:

1. Check if `start_time` is > 4 hours away
2. Check if an `AppointmentReminder` with `hours_before = 4` already exists for this appointment
3. If neither condition blocks, call `stage_reminder_jobs` with `hours_before=4`

This reuses the entire existing reminder pipeline (SQS → Twilio Lambda) with no new send infrastructure. The dedup check on step 2 makes the nightly job safe to run multiple times.

---

## What We Build

### 1. DB Migration `0022`

Add to `appointments` table:

```sql
no_show_risk          TEXT CHECK (no_show_risk IN ('low', 'medium', 'high')),
no_show_risk_computed_at  TIMESTAMPTZ
```

Both nullable — null means "not yet scored."

### 2. `app/services/risk_scoring.py`

- `PatientAppointmentHistory` dataclass
- `compute_risk_score(appointment, history, is_confirmed, lead_time_hours) -> Literal["low", "medium", "high"]`
- Pure function, no side effects

### 3. Nightly Risk Scoring Lambda

New function added to `modules/lambda-workers` Terraform module.

**Responsibilities:**
- Query all upcoming appointments across all practices (next 7 days, status not in `cancelled`, `no_show`)
- Batch-fetch patient appointment history: one aggregate query (`GROUP BY patient_id`) — no N+1
- Batch-fetch reminder status per appointment (existing `_batch_reminder_summary` pattern)
- Call `compute_risk_score` for each appointment
- Batch-UPDATE `no_show_risk` and `no_show_risk_computed_at`
- For each `high`-risk appointment: queue extra `hours_before=4` reminder if not already present and appointment is > 4h away

### 4. `app/routers/appointments.py`

**Schema:** `noShowRisk` serializes automatically once the column exists — no schema file changes needed.

**Recompute on confirmation:** When appointment status transitions to `confirmed`, call `compute_risk_score` after fetching patient history and update `no_show_risk` in the same transaction. Confirmation is the highest-weight signal, so same-day accuracy is important.

### 5. Frontend — `schedule/page.tsx`

Update `renderEventContent` to prefix patient name with a risk indicator:

| Risk | Indicator |
|---|---|
| `high` | Red dot `●` before name |
| `medium` | Yellow dot `●` before name |
| `low` / `null` | Nothing — keep cards uncluttered |

One small change to the existing render function. No new component needed.

---

## Terraform Changes

All changes are additive within the existing `lambda-workers` module and both environment `main.tf` files.

- New Lambda function: `risk-scoring-worker`
- New EventBridge scheduled rule: `cron(0 7 * * ? *)` (2am ET / 7am UTC)
- Same VPC, same `worker_sg_id`, same DB connection string from SSM — no new security groups or SSM params
- Both `environments/production/main.tf` and `environments/staging/main.tf` updated to pass the new function into the `lambda_workers` module

---

## Tests

| Test | Type |
|---|---|
| `compute_risk_score`: clean patient, confirmed → `low` | Unit |
| `compute_risk_score`: 2 prior no-shows out of 4 appts → `high` | Unit |
| `compute_risk_score`: unconfirmed + Monday early morning → `medium` or `high` | Unit |
| `compute_risk_score`: confirmed + no history → `low` | Unit |
| Nightly job: second run does not create a second `hours_before=4` reminder | Unit |
| Nightly job: appointment < 4h away does not get extra reminder | Unit |
| Appointment status → `confirmed`: `no_show_risk` recomputed in same response | Integration |

---

## Build Order

| Step | What |
|---|---|
| 1 | Migration `0022` — add `no_show_risk` + `no_show_risk_computed_at` columns |
| 2 | `app/services/risk_scoring.py` — pure function + unit tests |
| 3 | Appointment router: serialize `noShowRisk`, recompute on confirmation |
| 4 | Nightly Lambda + EventBridge (Terraform) |
| 5 | Extra high-risk reminder queuing inside Lambda |
| 6 | Frontend risk badge in `renderEventContent` |

---

## Open Questions

- **Score on new appointment creation?** Currently the nightly job is the main compute path. Should we also score immediately when an appointment is booked? Adds a patient-history query to the create path but keeps the badge from showing null for a full day.
- **Risk badge in day sheet view?** The schedule has both a calendar view and a `DaySheet` component — badge should appear in both. Confirm before frontend step.
- **Extra reminder channel:** Currently assumes SMS (matches primary reminder channel). Should the extra reminder also send email if the patient has email reminders enabled?
