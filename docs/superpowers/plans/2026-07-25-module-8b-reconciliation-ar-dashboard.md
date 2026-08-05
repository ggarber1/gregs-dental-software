# Module 8b — ERA Reconciliation & Practice A/R Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ERA reconciliation (surfacing settled claims that differed from the Module 6 estimate, with an optional confirm queue), overpayment visibility, and a practice A/R dashboard landing page; merge the insurance-ar worklist into the claims page to reduce navigation confusion.

**Architecture:** Pure-function reconciliation service mirrors the insurance_ar service pattern; three new endpoints on the existing reports router; Zod schemas generate new Pydantic models; frontend extends the existing claims page with a Reconciled tab and replaces the `/billing` placeholder with a summary dashboard.

**Tech Stack:** Python/FastAPI, SQLAlchemy async, Alembic, Pydantic v2, Next.js App Router, TanStack Query, shadcn/ui (badge, table, card), Zod

**Spec:** `docs/superpowers/specs/2026-07-25-module-8b-reconciliation-ar-dashboard-design.md`

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `apps/api/alembic/versions/0038_reconciliation_and_automation_config.py` | Create | Add `claims.reconciliation_confirmed_at` + `practice.automation_config` |
| `apps/api/app/models/claim.py` | Modify | Add `reconciliation_confirmed_at` mapped column |
| `apps/api/app/models/practice.py` | Modify | Add `automation_config` JSONB mapped column |
| `apps/api/app/services/reports/reconciliation.py` | Create | Pure classification functions + DB layer + AR summary |
| `apps/api/tests/services/test_reconciliation_core.py` | Create | Unit tests for pure classification functions |
| `apps/api/app/routers/reports.py` | Modify | Add 3 new endpoints |
| `apps/api/tests/routers/test_reports.py` | Modify | Add endpoint tests |
| `packages/shared-types/src/schemas/reports.ts` | Modify | Add `ReconciliationRow`, `ARSummary` Zod schemas |
| `packages/shared-types/scripts/generate-pydantic.ts` | Modify | Import + register new schemas |
| `apps/api/app/schemas/generated.py` | Auto-generated | Updated by `pnpm generate` — never hand-edit |
| `apps/web/lib/api/reports.ts` | Modify | Add TS types + hooks for reconciliation + AR summary |
| `apps/web/app/(app)/billing/page.tsx` | Modify | Replace placeholder with A/R dashboard |
| `apps/web/app/(app)/billing/claims/page.tsx` | Modify | Replace dropdown filter with 6-tab layout including Reconciled |
| `apps/web/app/(app)/billing/insurance-ar/page.tsx` | Modify | Redirect to `/billing/claims` |

---

## Task 1: Migration 0038 + model updates

**Files:**
- Create: `apps/api/alembic/versions/0038_reconciliation_and_automation_config.py`
- Modify: `apps/api/app/models/claim.py`
- Modify: `apps/api/app/models/practice.py`

- [ ] **Step 1: Write the migration**

```python
# apps/api/alembic/versions/0038_reconciliation_and_automation_config.py
"""Add reconciliation_confirmed_at to claims; add automation_config to practices

Revision ID: 0038
Revises: 0037
Create Date: 2026-07-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0038"
down_revision: str | Sequence[str] | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("reconciliation_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "practices",
        sa.Column(
            "automation_config",
            JSONB,
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("practices", "automation_config")
    op.drop_column("claims", "reconciliation_confirmed_at")
```

- [ ] **Step 2: Add `reconciliation_confirmed_at` to the Claim model**

In `apps/api/app/models/claim.py`, add after the `insurance_reviewed_at` column (around line 70):

```python
    # --- Module 8b: reconciliation confirm ---
    reconciliation_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

- [ ] **Step 3: Add `automation_config` to the Practice model**

In `apps/api/app/models/practice.py`, add after the `reminder_hours` column (around line 50). Add the `Any` import to the existing `from typing import TYPE_CHECKING` block:

```python
from typing import TYPE_CHECKING, Any
```

Then add the column:

```python
    # Per-module automation parameters. Each feature reads its key with a fallback
    # to a module-level constant. Keys are added without migrations.
    # e.g. {"era_reconciliation_mode": "confirm"}
    automation_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
```

- [ ] **Step 4: Run the migration**

```bash
cd apps/api && uv run alembic upgrade head
```

Expected: `Running upgrade 0037 -> 0038, Add reconciliation_confirmed_at to claims...`

- [ ] **Step 5: Run existing unit tests to confirm nothing broke**

```bash
cd apps/api && uv run pytest tests/services/ tests/routers/ -v --ignore=tests/integration -q
```

Expected: all existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api/alembic/versions/0038_reconciliation_and_automation_config.py \
        apps/api/app/models/claim.py \
        apps/api/app/models/practice.py
git commit -m "feat: migration 0038 — reconciliation_confirmed_at + practice.automation_config"
```

---

## Task 2: Reconciliation service — pure function tests

**Files:**
- Create: `apps/api/tests/services/test_reconciliation_core.py`

- [ ] **Step 1: Write the failing tests**

```python
# apps/api/tests/services/test_reconciliation_core.py
from app.services.reports.reconciliation import classify_for_reconciliation


def test_overpaid():
    assert classify_for_reconciliation(1100, 1000) == "overpaid"


def test_matched_exact():
    assert classify_for_reconciliation(1000, 1000) == "matched"


def test_within_tolerance_just_under():
    # 949/1000 = 94.9% — underpaid, returns None
    assert classify_for_reconciliation(949, 1000) is None


def test_within_tolerance_at_95_pct():
    # exactly 95% — NOT underpaid, within tolerance
    assert classify_for_reconciliation(950, 1000) == "within_tolerance"


def test_within_tolerance_between_95_and_100():
    assert classify_for_reconciliation(980, 1000) == "within_tolerance"


def test_no_estimate_none():
    assert classify_for_reconciliation(800, None) == "no_estimate"


def test_no_estimate_zero():
    # zero estimate treated as no estimate (avoid divide-by-zero)
    assert classify_for_reconciliation(800, 0) == "no_estimate"


def test_large_underpayment_excluded():
    assert classify_for_reconciliation(100, 1000) is None


def test_zero_paid_no_estimate():
    assert classify_for_reconciliation(0, None) == "no_estimate"
```

- [ ] **Step 2: Run tests — expect ImportError (module doesn't exist yet)**

```bash
cd apps/api && uv run pytest tests/services/test_reconciliation_core.py -v
```

Expected: `ImportError: cannot import name 'classify_for_reconciliation'`

- [ ] **Step 3: Commit the failing tests**

```bash
git add apps/api/tests/services/test_reconciliation_core.py
git commit -m "test: failing tests for reconciliation classify_for_reconciliation"
```

---

## Task 3: Reconciliation service — pure functions + DB layer

**Files:**
- Create: `apps/api/app/services/reports/reconciliation.py`

- [ ] **Step 1: Create the service with classification + DB layer**

```python
# apps/api/app/services/reports/reconciliation.py
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment_procedure import AppointmentProcedure
from app.models.claim import Claim
from app.models.copay_calculation import CopayCalculation
from app.models.insurance_plan import InsurancePlan
from app.models.ledger_entry import LedgerEntry
from app.models.patient import Patient
from app.models.practice import Practice
from app.services.reports.insurance_ar import (
    get_worklist as _get_ar_worklist,
    is_underpaid,
)

_UNDERPAY_PCT = 95  # must match insurance_ar._UNDERPAY_PCT
_PROBLEM_STATUSES = frozenset({"denied", "clearinghouse_rejected", "submission_failed"})

ReconciliationLabel = Literal["overpaid", "within_tolerance", "matched", "no_estimate"]


def classify_for_reconciliation(
    insurance_paid_cents: int,
    estimated_insurance_cents: int | None,
) -> ReconciliationLabel | None:
    """Return reconciliation label, or None if claim is underpaid (goes to insurance-ar).

    None means the claim is underpaid (paid < 95% of estimate) — it belongs
    in the Underpaid tab, not here.
    """
    if estimated_insurance_cents is None or estimated_insurance_cents <= 0:
        return "no_estimate"
    if insurance_paid_cents > estimated_insurance_cents:
        return "overpaid"
    if insurance_paid_cents == estimated_insurance_cents:
        return "matched"
    # paid < estimate — is it within tolerance or underpaid?
    if 100 * insurance_paid_cents >= _UNDERPAY_PCT * estimated_insurance_cents:
        return "within_tolerance"
    return None  # underpaid


@dataclass(frozen=True, kw_only=True)
class ReconciliationRow:
    claim_id: uuid.UUID
    appointment_id: uuid.UUID
    patient_id: uuid.UUID
    claim_number: str
    patient_name: str
    payer_id: str
    carrier_name: str
    recon_label: ReconciliationLabel
    billed_cents: int
    estimated_insurance_cents: int | None
    insurance_paid_cents: int
    variance_cents: int | None  # positive=overpaid, negative=shortfall, None=no estimate
    has_estimate: bool
    patient_balance_cents: int
    days_since_era: int
    reconciliation_confirmed_at: datetime | None


@dataclass
class ARSummaryData:
    insurance_ar_total_cents: int
    patient_ar_total_cents: int
    claims_needing_attention: int
    reconciliation_pending_count: int
    era_reconciliation_mode: Literal["auto", "confirm"]


# ---------------------------------------------------------------------------
# DB helpers (self-contained — mirrors insurance_ar private helpers)
# ---------------------------------------------------------------------------


async def _estimate_map(
    session: AsyncSession, appt_ids: set[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not appt_ids:
        return {}
    out: dict[uuid.UUID, int] = {}
    calcs = (
        await session.scalars(
            select(CopayCalculation)
            .where(CopayCalculation.appointment_id.in_(appt_ids))
            .order_by(CopayCalculation.appointment_id, CopayCalculation.created_at.desc())
        )
    ).all()
    for c in calcs:
        if c.appointment_id not in out:
            out[c.appointment_id] = int(c.total_insurance_owes_cents)
    missing = appt_ids - out.keys()
    if missing:
        rows = (
            await session.execute(
                select(
                    AppointmentProcedure.appointment_id,
                    func.sum(AppointmentProcedure.insurance_est_cents),
                )
                .where(
                    AppointmentProcedure.appointment_id.in_(missing),
                    AppointmentProcedure.insurance_est_cents.is_not(None),
                )
                .group_by(AppointmentProcedure.appointment_id)
            )
        ).all()
        for appt_id, total in rows:
            if total is not None:
                out[appt_id] = int(total)
    return out


async def _patient_name_map(
    session: AsyncSession, patient_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    if not patient_ids:
        return {}
    rows = (
        await session.execute(
            select(Patient.id, Patient.first_name, Patient.last_name).where(
                Patient.id.in_(patient_ids)
            )
        )
    ).all()
    return {pid: f"{first} {last}" for pid, first, last in rows}


async def _carrier_name_map(
    session: AsyncSession, payer_ids: set[str]
) -> dict[str, str]:
    if not payer_ids:
        return {}
    rows = (
        await session.scalars(
            select(InsurancePlan).where(InsurancePlan.payer_id.in_(payer_ids))
        )
    ).all()
    out: dict[str, str] = {}
    for ip in rows:
        out.setdefault(ip.payer_id, ip.carrier_name)
    return out


async def _patient_balance_map(
    session: AsyncSession, practice_id: uuid.UUID, patient_ids: set[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Map patient_id -> running ledger balance (sum of amount_cents). May be negative."""
    if not patient_ids:
        return {}
    rows = (
        await session.execute(
            select(LedgerEntry.patient_id, func.sum(LedgerEntry.amount_cents))
            .where(
                LedgerEntry.practice_id == practice_id,
                LedgerEntry.patient_id.in_(patient_ids),
                LedgerEntry.deleted_at.is_(None),
            )
            .group_by(LedgerEntry.patient_id)
        )
    ).all()
    return {pid: int(total) for pid, total in rows}


async def _reconciliation_mode(session: AsyncSession, practice_id: uuid.UUID) -> str:
    practice = await session.scalar(
        select(Practice).where(Practice.id == practice_id)
    )
    if practice is None:
        return "auto"
    config: dict[str, Any] = practice.automation_config or {}
    return config.get("era_reconciliation_mode", "auto")


# ---------------------------------------------------------------------------
# Public DB layer
# ---------------------------------------------------------------------------


async def get_reconciliation_worklist(
    session: AsyncSession,
    practice_id: uuid.UUID,
    *,
    confirmed: bool | None = None,
    now: datetime | None = None,
) -> list[ReconciliationRow]:
    """Return ERA-settled claims eligible for reconciliation review.

    In auto mode only overpaid/within_tolerance/no_estimate claims are returned.
    In confirm mode matched (exact) claims are also returned.
    `confirmed` filters by whether reconciliation_confirmed_at is set.
    """
    now = now or datetime.now(UTC)
    mode = await _reconciliation_mode(session, practice_id)

    stmt = select(Claim).where(
        Claim.practice_id == practice_id,
        Claim.deleted_at.is_(None),
        Claim.insurance_paid_cents.isnot(None),
        Claim.status.notin_(["draft", "appealing", *_PROBLEM_STATUSES]),
    )
    if confirmed is True:
        stmt = stmt.where(Claim.reconciliation_confirmed_at.isnot(None))
    elif confirmed is False:
        stmt = stmt.where(Claim.reconciliation_confirmed_at.is_(None))

    claims = list((await session.scalars(stmt)).all())
    if not claims:
        return []

    estimates = await _estimate_map(session, {c.appointment_id for c in claims})
    patient_names = await _patient_name_map(session, {c.patient_id for c in claims})
    carrier_names = await _carrier_name_map(session, {c.payer_id for c in claims})
    balances = await _patient_balance_map(session, practice_id, {c.patient_id for c in claims})

    rows: list[ReconciliationRow] = []
    for c in claims:
        est = estimates.get(c.appointment_id)
        paid = int(c.insurance_paid_cents)  # type: ignore[arg-type]

        # Exclude underpaid — those belong in the insurance-ar Underpaid tab
        label = classify_for_reconciliation(paid, est)
        if label is None:
            continue
        # In auto mode, skip exact-match claims (no interesting signal)
        if mode == "auto" and label == "matched":
            continue

        era_anchor = c.paid_at or c.submitted_at or c.created_at
        days_since = (now.date() - era_anchor.date()).days

        variance = None
        if est is not None:
            variance = paid - est  # positive=overpaid, negative=shortfall

        rows.append(
            ReconciliationRow(
                claim_id=c.id,
                appointment_id=c.appointment_id,
                patient_id=c.patient_id,
                claim_number=c.patient_control_number,
                patient_name=patient_names.get(c.patient_id, "Unknown"),
                payer_id=c.payer_id,
                carrier_name=carrier_names.get(c.payer_id, c.payer_id),
                recon_label=label,
                billed_cents=int(c.total_charge_cents),
                estimated_insurance_cents=est,
                insurance_paid_cents=paid,
                variance_cents=variance,
                has_estimate=est is not None,
                patient_balance_cents=balances.get(c.patient_id, 0),
                days_since_era=days_since,
                reconciliation_confirmed_at=c.reconciliation_confirmed_at,
            )
        )

    rows.sort(key=lambda r: r.days_since_era, reverse=True)
    return rows


async def confirm_reconciliation(
    session: AsyncSession,
    practice_id: uuid.UUID,
    claim_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> Claim:
    """Set reconciliation_confirmed_at on a claim. Raises LookupError or ValueError."""
    claim = await session.scalar(
        select(Claim)
        .where(
            Claim.id == claim_id,
            Claim.practice_id == practice_id,
            Claim.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if claim is None:
        raise LookupError(f"claim {claim_id} not found for practice")
    if claim.reconciliation_confirmed_at is not None:
        raise ValueError("claim already confirmed")
    # Validate the claim is actually in the reconciliation set
    est = (await _estimate_map(session, {claim.appointment_id})).get(claim.appointment_id)
    paid = claim.insurance_paid_cents
    if paid is None:
        raise ValueError("claim has no ERA payment — not eligible for reconciliation")
    if classify_for_reconciliation(int(paid), est) is None:
        raise ValueError("claim is underpaid — use the insurance-ar accept action instead")
    if claim.status in _PROBLEM_STATUSES or claim.status == "appealing":
        raise ValueError("claim is in problem/appealing state — not eligible for reconciliation")

    claim.reconciliation_confirmed_at = now or datetime.now(UTC)
    await session.commit()
    await session.refresh(claim)
    return claim


async def get_ar_summary(
    session: AsyncSession,
    practice_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> ARSummaryData:
    """Practice-level A/R summary for the billing dashboard."""
    now = now or datetime.now(UTC)

    # Insurance A/R: sum expected from awaiting + shortfall from underpaid
    ar_rows = await _get_ar_worklist(session, practice_id, now=now)
    insurance_ar_total = sum(
        r.estimated_insurance_cents or 0 for r in ar_rows if r.category == "awaiting"
    ) + sum(
        r.shortfall_cents or 0 for r in ar_rows if r.category == "underpaid"
    )
    claims_needing_attention = sum(
        1 for r in ar_rows if r.category in ("problem", "appealing")
    )

    # Patient A/R: sum of positive patient balances from ledger
    subq = (
        select(func.sum(LedgerEntry.amount_cents).label("balance"))
        .where(
            LedgerEntry.practice_id == practice_id,
            LedgerEntry.deleted_at.is_(None),
        )
        .group_by(LedgerEntry.patient_id)
        .having(func.sum(LedgerEntry.amount_cents) > 0)
        .subquery()
    )
    patient_ar_total = int(
        await session.scalar(select(func.coalesce(func.sum(subq.c.balance), 0))) or 0
    )

    # Reconciliation pending: unconfirmed interesting ERA-settled claims
    pending_rows = await get_reconciliation_worklist(
        session, practice_id, confirmed=False, now=now
    )
    reconciliation_pending_count = len(pending_rows)

    mode = await _reconciliation_mode(session, practice_id)

    return ARSummaryData(
        insurance_ar_total_cents=insurance_ar_total,
        patient_ar_total_cents=patient_ar_total,
        claims_needing_attention=claims_needing_attention,
        reconciliation_pending_count=reconciliation_pending_count,
        era_reconciliation_mode=mode,  # type: ignore[arg-type]
    )
```

- [ ] **Step 2: Run the pure function tests — expect PASS**

```bash
cd apps/api && uv run pytest tests/services/test_reconciliation_core.py -v
```

Expected: all 9 tests pass.

- [ ] **Step 3: Run the full unit + router test suite**

```bash
cd apps/api && uv run pytest tests/services/ tests/routers/ -v --ignore=tests/integration -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/services/reports/reconciliation.py
git commit -m "feat: reconciliation service — classify_for_reconciliation + worklist + AR summary"
```

---

## Task 4: Zod schemas + pnpm generate

**Files:**
- Modify: `packages/shared-types/src/schemas/reports.ts`
- Modify: `packages/shared-types/scripts/generate-pydantic.ts`
- Auto-update: `apps/api/app/schemas/generated.py`

- [ ] **Step 1: Add new schemas to `reports.ts`**

Append to `packages/shared-types/src/schemas/reports.ts` (after the existing `ClaimActionResultSchema`):

```typescript
export const ReconciliationLabelSchema = z.enum([
  "overpaid",
  "within_tolerance",
  "matched",
  "no_estimate",
]);
export type ReconciliationLabel = z.infer<typeof ReconciliationLabelSchema>;

export const ReconciliationRowSchema = z.object({
  claimId: UuidSchema,
  appointmentId: UuidSchema,
  patientId: UuidSchema,
  claimNumber: z.string(),
  patientName: z.string(),
  payerId: z.string(),
  carrierName: z.string(),
  reconLabel: ReconciliationLabelSchema,
  billedCents: z.number().int(),
  estimatedInsuranceCents: z.number().int().nullable(),
  insurancePaidCents: z.number().int(),
  varianceCents: z.number().int().nullable(),
  hasEstimate: z.boolean(),
  patientBalanceCents: z.number().int(),
  daysSinceEra: z.number().int(),
  reconciliationConfirmedAt: z.string().datetime().nullable(),
});
export type ReconciliationRow = z.infer<typeof ReconciliationRowSchema>;

export const ARSummarySchema = z.object({
  insuranceArTotalCents: z.number().int(),
  patientArTotalCents: z.number().int(),
  claimsNeedingAttention: z.number().int(),
  reconciliationPendingCount: z.number().int(),
  eraReconciliationMode: z.enum(["auto", "confirm"]),
});
export type ARSummary = z.infer<typeof ARSummarySchema>;
```

- [ ] **Step 2: Register the new schemas in `generate-pydantic.ts`**

In `packages/shared-types/scripts/generate-pydantic.ts`, find the existing import from `../src/schemas/reports.js` (around line 171) and add the new schemas:

```typescript
import {
  ARBucketsSchema,
  InsuranceARRowSchema,
  InsuranceARCarrierSummarySchema,
  InsuranceARTotalsSchema,
  InsuranceARSummarySchema,
  ClaimActionResultSchema,
  ReconciliationLabelSchema,
  ReconciliationRowSchema,
  ARSummarySchema,
} from "../src/schemas/reports.js";
```

Then in the `schemas` registry object (around line 180), add:

```typescript
  ReconciliationLabel: ReconciliationLabelSchema,
  ReconciliationRow: ReconciliationRowSchema,
  ARSummary: ARSummarySchema,
```

- [ ] **Step 3: Regenerate `generated.py`**

```bash
pnpm --filter @dental/shared-types generate
```

Expected: `apps/api/app/schemas/generated.py` updated with `ReconciliationLabel`, `ReconciliationRow`, `ARSummary` classes.

- [ ] **Step 4: Verify the generated models exist**

```bash
grep -n "class ReconciliationRow\|class ARSummary\|class ReconciliationLabel" apps/api/app/schemas/generated.py
```

Expected: three matching lines with class definitions.

- [ ] **Step 5: Commit**

```bash
git add packages/shared-types/src/schemas/reports.ts \
        packages/shared-types/scripts/generate-pydantic.ts \
        apps/api/app/schemas/generated.py
git commit -m "feat: add ReconciliationRow + ARSummary Zod schemas and regenerate Pydantic models"
```

---

## Task 5: New endpoints in reports.py

**Files:**
- Modify: `apps/api/app/routers/reports.py`

- [ ] **Step 1: Add imports at the top of reports.py**

Add to the existing imports in `apps/api/app/routers/reports.py`:

```python
from app.schemas.generated import (
    ApiError,
    ARSummary,
    ClaimActionResult,
    Error,
    InsuranceARRow,
    InsuranceARSummary,
    ReconciliationRow,
)
from app.services.reports import insurance_ar, reconciliation
```

Replace the existing separate imports of `insurance_ar` and the schema names with this combined block.

- [ ] **Step 2: Add the three new endpoints**

Append to `apps/api/app/routers/reports.py` after the existing `flag_for_appeal` endpoint:

```python
def _recon_row_to_dict(r: reconciliation.ReconciliationRow) -> dict[str, Any]:
    return {
        "claimId": r.claim_id,
        "appointmentId": r.appointment_id,
        "patientId": r.patient_id,
        "claimNumber": r.claim_number,
        "patientName": r.patient_name,
        "payerId": r.payer_id,
        "carrierName": r.carrier_name,
        "reconLabel": r.recon_label,
        "billedCents": r.billed_cents,
        "estimatedInsuranceCents": r.estimated_insurance_cents,
        "insurancePaidCents": r.insurance_paid_cents,
        "varianceCents": r.variance_cents,
        "hasEstimate": r.has_estimate,
        "patientBalanceCents": r.patient_balance_cents,
        "daysSinceEra": r.days_since_era,
        "reconciliationConfirmedAt": (
            r.reconciliation_confirmed_at.isoformat()
            if r.reconciliation_confirmed_at
            else None
        ),
    }


@router.get("/reports/reconciliation/claims", response_model=list[ReconciliationRow])
async def get_reconciliation_worklist(
    request: Request,
    confirmed: bool | None = None,
) -> list[ReconciliationRow]:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        rows = await reconciliation.get_reconciliation_worklist(
            session, practice_id, confirmed=confirmed
        )
        return [ReconciliationRow.model_validate(_recon_row_to_dict(r)) for r in rows]


@router.post(
    "/reports/reconciliation/claims/{claim_id}/confirm",
    response_model=ClaimActionResult,
)
async def confirm_reconciliation(
    claim_id: uuid.UUID, request: Request
) -> ClaimActionResult:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        try:
            claim = await reconciliation.confirm_reconciliation(
                session, practice_id, claim_id
            )
        except LookupError:
            raise _err(404, "CLAIM_NOT_FOUND", "Claim not found") from None
        except ValueError as exc:
            raise _err(409, "CONFIRM_REJECTED", str(exc)) from None
        return _action_result(claim)


@router.get("/reports/ar-summary", response_model=ARSummary)
async def get_ar_summary(request: Request) -> ARSummary:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        data = await reconciliation.get_ar_summary(session, practice_id)
        return ARSummary.model_validate(
            {
                "insuranceArTotalCents": data.insurance_ar_total_cents,
                "patientArTotalCents": data.patient_ar_total_cents,
                "claimsNeedingAttention": data.claims_needing_attention,
                "reconciliationPendingCount": data.reconciliation_pending_count,
                "eraReconciliationMode": data.era_reconciliation_mode,
            }
        )
```

- [ ] **Step 3: Run type check**

```bash
cd apps/api && uv run mypy app/routers/reports.py
```

Expected: no errors.

- [ ] **Step 4: Run existing router tests**

```bash
cd apps/api && uv run pytest tests/routers/test_reports.py -v
```

Expected: existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/routers/reports.py
git commit -m "feat: reconciliation + AR summary endpoints on reports router"
```

---

## Task 6: Endpoint tests

**Files:**
- Modify: `apps/api/tests/routers/test_reports.py`

- [ ] **Step 1: Write failing tests for the three new endpoints**

At the top of `apps/api/tests/routers/test_reports.py`, add these imports alongside the existing ones (do not duplicate `uuid` or `pytest`):

```python
from datetime import UTC, datetime
from app.services.reports.reconciliation import ReconciliationRow as ReconRow, ARSummaryData
```

Then append the test functions after the existing tests:

```python
# ── Reconciliation endpoint tests ──────────────────────────────────────────────


def _recon_row(**kw) -> ReconRow:
    defaults = dict(
        claim_id=uuid.uuid4(),
        appointment_id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        claim_number="CLM001",
        patient_name="Jane Doe",
        payer_id="DELTA",
        carrier_name="Delta Dental",
        recon_label="overpaid",
        billed_cents=100000,
        estimated_insurance_cents=80000,
        insurance_paid_cents=85000,
        variance_cents=5000,
        has_estimate=True,
        patient_balance_cents=15000,
        days_since_era=5,
        reconciliation_confirmed_at=None,
    )
    defaults.update(kw)
    return ReconRow(**defaults)


@pytest.mark.asyncio
async def test_get_reconciliation_worklist_happy_path(app):
    row = _recon_row()
    factory = _fake_session_factory()
    with (
        _auth_patches() as headers,
        patch("app.routers.reports.get_session_factory", return_value=factory),
        patch(
            "app.routers.reports.require_feature",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.routers.reports.reconciliation.get_reconciliation_worklist",
            new=AsyncMock(return_value=[row]),
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/reports/reconciliation/claims", headers=headers
            )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["reconLabel"] == "overpaid"
    assert data[0]["varianceCents"] == 5000


@pytest.mark.asyncio
async def test_get_reconciliation_worklist_confirmed_filter(app):
    factory = _fake_session_factory()
    mock_get = AsyncMock(return_value=[])
    with (
        _auth_patches() as headers,
        patch("app.routers.reports.get_session_factory", return_value=factory),
        patch("app.routers.reports.require_feature", new=AsyncMock(return_value=None)),
        patch(
            "app.routers.reports.reconciliation.get_reconciliation_worklist",
            new=mock_get,
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.get(
                "/api/v1/reports/reconciliation/claims?confirmed=false", headers=headers
            )
    mock_get.assert_called_once()
    _, kwargs = mock_get.call_args
    assert kwargs["confirmed"] is False


@pytest.mark.asyncio
async def test_confirm_reconciliation_success(app):
    claim = MagicMock()
    claim.id = uuid.uuid4()
    claim.status = "paid"
    claim.insurance_reviewed_at = None
    claim.reconciliation_confirmed_at = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
    factory = _fake_session_factory()
    with (
        _auth_patches(role="front_desk") as headers,
        patch("app.routers.reports.get_session_factory", return_value=factory),
        patch("app.routers.reports.require_feature", new=AsyncMock(return_value=None)),
        patch(
            "app.routers.reports.reconciliation.confirm_reconciliation",
            new=AsyncMock(return_value=claim),
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/v1/reports/reconciliation/claims/{claim.id}/confirm",
                headers=headers,
            )
    assert resp.status_code == 200
    assert resp.json()["claimId"] == str(claim.id)


@pytest.mark.asyncio
async def test_confirm_reconciliation_not_found(app):
    factory = _fake_session_factory()
    with (
        _auth_patches() as headers,
        patch("app.routers.reports.get_session_factory", return_value=factory),
        patch("app.routers.reports.require_feature", new=AsyncMock(return_value=None)),
        patch(
            "app.routers.reports.reconciliation.confirm_reconciliation",
            new=AsyncMock(side_effect=LookupError("not found")),
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/v1/reports/reconciliation/claims/{uuid.uuid4()}/confirm",
                headers=headers,
            )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_confirm_reconciliation_already_confirmed(app):
    factory = _fake_session_factory()
    with (
        _auth_patches() as headers,
        patch("app.routers.reports.get_session_factory", return_value=factory),
        patch("app.routers.reports.require_feature", new=AsyncMock(return_value=None)),
        patch(
            "app.routers.reports.reconciliation.confirm_reconciliation",
            new=AsyncMock(side_effect=ValueError("claim already confirmed")),
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/v1/reports/reconciliation/claims/{uuid.uuid4()}/confirm",
                headers=headers,
            )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_ar_summary_happy_path(app):
    summary = ARSummaryData(
        insurance_ar_total_cents=500000,
        patient_ar_total_cents=75000,
        claims_needing_attention=3,
        reconciliation_pending_count=2,
        era_reconciliation_mode="confirm",
    )
    factory = _fake_session_factory()
    with (
        _auth_patches() as headers,
        patch("app.routers.reports.get_session_factory", return_value=factory),
        patch("app.routers.reports.require_feature", new=AsyncMock(return_value=None)),
        patch(
            "app.routers.reports.reconciliation.get_ar_summary",
            new=AsyncMock(return_value=summary),
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/reports/ar-summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["insuranceArTotalCents"] == 500000
    assert data["reconciliationPendingCount"] == 2
    assert data["eraReconciliationMode"] == "confirm"


@pytest.mark.asyncio
async def test_reconciliation_feature_gate(app):
    factory = _fake_session_factory()
    with (
        _auth_patches() as headers,
        patch("app.routers.reports.get_session_factory", return_value=factory),
        patch(
            "app.routers.reports.require_feature",
            new=AsyncMock(side_effect=_feature_off()),
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r1 = await client.get(
                "/api/v1/reports/reconciliation/claims", headers=headers
            )
            r2 = await client.get("/api/v1/reports/ar-summary", headers=headers)
    assert r1.status_code == 403
    assert r2.status_code == 403
```

- [ ] **Step 2: Run the new tests — expect PASS (endpoints are already implemented)**

```bash
cd apps/api && uv run pytest tests/routers/test_reports.py -v -k "reconciliation or ar_summary"
```

Expected: all 7 new tests pass.

- [ ] **Step 3: Run full router test suite**

```bash
cd apps/api && uv run pytest tests/routers/test_reports.py -v
```

Expected: all tests (existing + new) pass.

- [ ] **Step 4: Run ruff + mypy**

```bash
cd apps/api && uv run ruff check . && uv run mypy app/
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add apps/api/tests/routers/test_reports.py
git commit -m "test: reconciliation + AR summary endpoint tests"
```

---

## Task 7: Frontend types + hooks

**Files:**
- Modify: `apps/web/lib/api/reports.ts`

- [ ] **Step 1: Add types and hooks**

Append to `apps/web/lib/api/reports.ts` (after the existing `centsToUsd` function):

```typescript
export type ReconciliationLabel =
  | "overpaid"
  | "within_tolerance"
  | "matched"
  | "no_estimate";

export interface ReconciliationRow {
  claimId: string;
  appointmentId: string;
  patientId: string;
  claimNumber: string;
  patientName: string;
  payerId: string;
  carrierName: string;
  reconLabel: ReconciliationLabel;
  billedCents: number;
  estimatedInsuranceCents: number | null;
  insurancePaidCents: number;
  varianceCents: number | null;
  hasEstimate: boolean;
  patientBalanceCents: number;
  daysSinceEra: number;
  reconciliationConfirmedAt: string | null;
}

export interface ARSummary {
  insuranceArTotalCents: number;
  patientArTotalCents: number;
  claimsNeedingAttention: number;
  reconciliationPendingCount: number;
  eraReconciliationMode: "auto" | "confirm";
}

export const reportsKeys = {
  all: ["reports"] as const,
  worklist: (category?: string) =>
    ["reports", "insurance-ar", "worklist", { category: category ?? null }] as const,
  summary: ["reports", "insurance-ar", "summary"] as const,
  reconciliation: (confirmed?: boolean) =>
    ["reports", "reconciliation", { confirmed: confirmed ?? null }] as const,
  arSummary: ["reports", "ar-summary"] as const,
};
```

Note: replace the existing `reportsKeys` object with the one above (it adds the two new keys).

Then add the hooks:

```typescript
export function useReconciliationWorklist(confirmed?: boolean) {
  const query =
    confirmed !== undefined ? `?confirmed=${confirmed}` : "";
  return useQuery({
    queryKey: reportsKeys.reconciliation(confirmed),
    queryFn: () =>
      apiClient.get<ReconciliationRow[]>(
        `/api/v1/reports/reconciliation/claims${query}`
      ),
  });
}

export function useConfirmReconciliation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (claimId: string) =>
      apiClient.post(
        `/api/v1/reports/reconciliation/claims/${claimId}/confirm`,
        {},
        { idempotencyKey: generateId() }
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: reportsKeys.all });
    },
  });
}

export function useARSummary() {
  return useQuery({
    queryKey: reportsKeys.arSummary,
    queryFn: () => apiClient.get<ARSummary>("/api/v1/reports/ar-summary"),
  });
}
```

- [ ] **Step 2: Run TS type check**

```bash
cd apps/web && pnpm tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/web/lib/api/reports.ts
git commit -m "feat: reconciliation + AR summary TS types and TanStack Query hooks"
```

---

## Task 8: Billing dashboard page

**Files:**
- Modify: `apps/web/app/(app)/billing/page.tsx`

- [ ] **Step 1: Replace the placeholder with the dashboard**

```typescript
// apps/web/app/(app)/billing/page.tsx
"use client";

import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { centsToUsd, useARSummary } from "@/lib/api/reports";

function SummaryCard({
  title,
  value,
  subtitle,
  href,
}: {
  title: string;
  value: string | number;
  subtitle?: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="flex flex-col gap-1 rounded-lg border border-border p-5 hover:bg-muted/40 transition-colors"
    >
      <span className="text-sm text-muted-foreground">{title}</span>
      <span className="text-2xl font-semibold tabular-nums">{value}</span>
      {subtitle && (
        <span className="text-xs text-muted-foreground">{subtitle}</span>
      )}
    </Link>
  );
}

export default function BillingPage() {
  const { data: summary, isLoading } = useARSummary();

  if (isLoading || !summary) {
    return (
      <div className="flex flex-col gap-6 p-6">
        <PageHeader title="Billing" description="Practice A/R overview" />
        <div className="h-32 animate-pulse rounded-lg bg-muted" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <PageHeader title="Billing" description="Practice A/R overview" />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryCard
          title="Insurance A/R"
          value={centsToUsd(summary.insuranceArTotalCents)}
          subtitle="Awaiting + underpaid"
          href="/billing/claims?tab=awaiting"
        />
        <SummaryCard
          title="Claims Needing Attention"
          value={summary.claimsNeedingAttention}
          subtitle="Denied · rejected · appealing"
          href="/billing/claims?tab=problem"
        />
        <SummaryCard
          title="Patient A/R"
          value={centsToUsd(summary.patientArTotalCents)}
          subtitle="Statements coming soon"
          href="/billing/claims"
        />
        {summary.eraReconciliationMode === "confirm" &&
          summary.reconciliationPendingCount > 0 && (
            <SummaryCard
              title="Reconciliation Pending"
              value={summary.reconciliationPendingCount}
              subtitle="ERA settlements to confirm"
              href="/billing/claims?tab=reconciled"
            />
          )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Run TS type check**

```bash
cd apps/web && pnpm tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/web/app/(app)/billing/page.tsx
git commit -m "feat: billing dashboard landing page with A/R summary cards"
```

---

## Task 9: Claims page Reconciled tab + insurance-ar redirect

**Files:**
- Modify: `apps/web/app/(app)/billing/claims/page.tsx`
- Modify: `apps/web/app/(app)/billing/insurance-ar/page.tsx`

- [ ] **Step 1: Rewrite the claims page with 6 tabs**

The new page merges the existing status-dropdown claims list (now the "All" tab) with the insurance-ar worklist (tabs 2–5) and adds the new Reconciled tab (tab 6).

```typescript
// apps/web/app/(app)/billing/claims/page.tsx
"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { Suspense } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useClaimsList, useResubmitClaim, useWriteOffClaim, type Claim } from "@/lib/api/claims";
import {
  centsToUsd,
  useInsuranceARWorklist,
  useAcceptUnderpayment,
  useFlagForAppeal,
  useReconciliationWorklist,
  useConfirmReconciliation,
  useARSummary,
  type ARCategory,
  type ReconciliationRow,
  type InsuranceARRow,
} from "@/lib/api/reports";

type Tab = "all" | ARCategory | "reconciled";

const TABS: { key: Tab; label: string }[] = [
  { key: "all", label: "All" },
  { key: "awaiting", label: "Awaiting" },
  { key: "underpaid", label: "Underpaid" },
  { key: "problem", label: "Problem" },
  { key: "appealing", label: "Appealing" },
  { key: "reconciled", label: "Reconciled" },
];

function statusVariant(status: Claim["status"]): "default" | "secondary" | "destructive" {
  if (["submitted", "paid", "acknowledged"].includes(status)) return "default";
  if (["clearinghouse_rejected", "submission_failed", "denied"].includes(status))
    return "destructive";
  return "secondary";
}

// ── All tab ──────────────────────────────────────────────────────────────────

function AllTab() {
  const { data, isLoading } = useClaimsList(undefined);
  const claims = data ?? [];

  if (isLoading) return <LoadingSpinner />;
  if (claims.length === 0) return <EmptyState message="No claims found." />;

  return (
    <TableShell>
      <TableHeader>
        <TableRow>
          <TableHead>Claim #</TableHead>
          <TableHead>Payer</TableHead>
          <TableHead className="text-right">Charge</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Submitted</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {claims.map((c) => (
          <TableRow key={c.id}>
            <TableCell className="font-mono text-xs">{c.patientControlNumber}</TableCell>
            <TableCell className="text-muted-foreground">{c.payerId}</TableCell>
            <TableCell className="text-right">{centsToUsd(c.totalChargeCents)}</TableCell>
            <TableCell>
              <Badge variant={statusVariant(c.status)}>{c.status.replace(/_/g, " ")}</Badge>
            </TableCell>
            <TableCell className="text-muted-foreground">
              {c.submittedAt ? c.submittedAt.slice(0, 10) : "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </TableShell>
  );
}

// ── Insurance A/R tabs (Awaiting / Underpaid / Problem / Appealing) ──────────

function ARTab({ category }: { category: ARCategory }) {
  const { data: rows, isLoading } = useInsuranceARWorklist(category);
  const accept = useAcceptUnderpayment();
  const appeal = useFlagForAppeal();
  const list = rows ?? [];

  if (isLoading) return <LoadingSpinner />;
  if (list.length === 0)
    return <EmptyState message={`No ${category.replace("_", " ")} claims.`} />;

  return (
    <TableShell>
      <TableHeader>
        <TableRow>
          <TableHead>Claim #</TableHead>
          <TableHead>Patient</TableHead>
          <TableHead>Carrier</TableHead>
          <TableHead className="text-right">Billed</TableHead>
          <TableHead className="text-right">Est. ins.</TableHead>
          <TableHead className="text-right">Paid</TableHead>
          <TableHead>Days</TableHead>
          <TableHead>Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {list.map((r) => (
          <ARRow
            key={r.claimId}
            row={r}
            onAccept={() => accept.mutate(r.claimId)}
            onAppeal={() => appeal.mutate(r.claimId)}
            accepting={accept.isPending}
            appealing={appeal.isPending}
          />
        ))}
      </TableBody>
    </TableShell>
  );
}

function ARRow({
  row,
  onAccept,
  onAppeal,
  accepting,
  appealing,
}: {
  row: InsuranceARRow;
  onAccept: () => void;
  onAppeal: () => void;
  accepting: boolean;
  appealing: boolean;
}) {
  const resubmit = useResubmitClaim(row.claimId, row.appointmentId, row.patientId);
  const writeOff = useWriteOffClaim(row.claimId, row.appointmentId, row.patientId);

  return (
    <TableRow>
      <TableCell className="font-mono text-xs">{row.claimNumber}</TableCell>
      <TableCell>{row.patientName}</TableCell>
      <TableCell className="text-muted-foreground">{row.carrierName}</TableCell>
      <TableCell className="text-right">{centsToUsd(row.billedCents)}</TableCell>
      <TableCell className="text-right">{centsToUsd(row.estimatedInsuranceCents)}</TableCell>
      <TableCell className="text-right">{centsToUsd(row.insurancePaidCents)}</TableCell>
      <TableCell className="text-muted-foreground">{row.daysOut}d</TableCell>
      <TableCell>
        {row.category === "underpaid" && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onAccept}
              disabled={accepting}
              className="text-sm text-primary underline disabled:opacity-50"
            >
              Accept
            </button>
            <button
              type="button"
              onClick={onAppeal}
              disabled={appealing}
              title="Triage flag only — does not submit to the carrier"
              className="text-sm text-muted-foreground underline disabled:opacity-50"
            >
              Flag for appeal
            </button>
          </div>
        )}
        {(row.category === "problem" || row.category === "appealing") && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => resubmit.mutate()}
              disabled={resubmit.isPending}
              className="text-sm text-primary underline disabled:opacity-50"
            >
              {resubmit.isPending ? "Resubmitting…" : "Resubmit"}
            </button>
            {(row.status === "denied" || row.status === "appealing") && (
              <button
                type="button"
                onClick={() => writeOff.mutate(undefined)}
                disabled={writeOff.isPending}
                className="text-sm text-muted-foreground underline disabled:opacity-50"
              >
                {writeOff.isPending ? "Writing off…" : "Write off"}
              </button>
            )}
          </div>
        )}
        {row.reason && (
          <p className="mt-1 text-xs text-muted-foreground">{row.reason}</p>
        )}
      </TableCell>
    </TableRow>
  );
}

// ── Reconciled tab ────────────────────────────────────────────────────────────

function ReconciledTab({ mode }: { mode: "auto" | "confirm" }) {
  const { data: unconfirmed, isLoading: loadingUnconfirmed } = useReconciliationWorklist(
    mode === "confirm" ? false : undefined
  );
  const { data: confirmed, isLoading: loadingConfirmed } = useReconciliationWorklist(
    mode === "confirm" ? true : undefined
  );
  const confirm = useConfirmReconciliation();

  const pending = unconfirmed ?? [];
  const history = confirmed ?? [];
  const allRows = mode === "auto" ? (unconfirmed ?? []) : undefined;

  if (loadingUnconfirmed || loadingConfirmed) return <LoadingSpinner />;

  if (mode === "auto") {
    if ((allRows ?? []).length === 0)
      return <EmptyState message="No ERA settlements to review." />;
    return (
      <ReconTable
        rows={allRows ?? []}
        showConfirm={false}
        onConfirm={() => {}}
        confirming={false}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {pending.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-medium">Needs review</h3>
          <ReconTable
            rows={pending}
            showConfirm
            onConfirm={(id) => confirm.mutate(id)}
            confirming={confirm.isPending}
          />
        </div>
      )}
      {history.length > 0 && (
        <div>
          {pending.length > 0 && (
            <div className="my-4 border-t border-border" />
          )}
          <h3 className="mb-2 text-sm font-medium text-muted-foreground">Recent</h3>
          <ReconTable
            rows={history}
            showConfirm={false}
            onConfirm={() => {}}
            confirming={false}
          />
        </div>
      )}
      {pending.length === 0 && history.length === 0 && (
        <EmptyState message="No ERA settlements to review." />
      )}
    </div>
  );
}

function ReconTable({
  rows,
  showConfirm,
  onConfirm,
  confirming,
}: {
  rows: ReconciliationRow[];
  showConfirm: boolean;
  onConfirm: (claimId: string) => void;
  confirming: boolean;
}) {
  return (
    <TableShell>
      <TableHeader>
        <TableRow>
          <TableHead>Claim #</TableHead>
          <TableHead>Patient</TableHead>
          <TableHead>Carrier</TableHead>
          <TableHead className="text-right">Billed</TableHead>
          <TableHead className="text-right">Est. ins.</TableHead>
          <TableHead className="text-right">Paid</TableHead>
          <TableHead className="text-right">Variance</TableHead>
          <TableHead className="text-right">Patient bal.</TableHead>
          {showConfirm && <TableHead />}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.claimId}>
            <TableCell className="font-mono text-xs">{r.claimNumber}</TableCell>
            <TableCell>{r.patientName}</TableCell>
            <TableCell className="text-muted-foreground">{r.carrierName}</TableCell>
            <TableCell className="text-right">{centsToUsd(r.billedCents)}</TableCell>
            <TableCell className="text-right">
              {centsToUsd(r.estimatedInsuranceCents)}
            </TableCell>
            <TableCell className="text-right">{centsToUsd(r.insurancePaidCents)}</TableCell>
            <TableCell className="text-right">
              {r.varianceCents !== null ? (
                <span
                  className={
                    r.varianceCents > 0
                      ? "text-green-600"
                      : r.varianceCents < 0
                        ? "text-amber-600"
                        : ""
                  }
                >
                  {r.varianceCents > 0 ? "+" : ""}
                  {centsToUsd(r.varianceCents)}
                  {r.varianceCents > 0 && (
                    <Badge className="ml-1 text-xs" variant="secondary">
                      Overpaid
                    </Badge>
                  )}
                </span>
              ) : (
                <span className="text-muted-foreground">No estimate</span>
              )}
            </TableCell>
            <TableCell className="text-right">
              <span className={r.patientBalanceCents < 0 ? "text-green-600" : ""}>
                {centsToUsd(r.patientBalanceCents)}
                {r.patientBalanceCents < 0 && (
                  <Badge className="ml-1 text-xs" variant="secondary">
                    Credit
                  </Badge>
                )}
              </span>
            </TableCell>
            {showConfirm && (
              <TableCell>
                <button
                  type="button"
                  onClick={() => onConfirm(r.claimId)}
                  disabled={confirming}
                  className="text-sm text-primary underline disabled:opacity-50"
                >
                  Confirm
                </button>
              </TableCell>
            )}
          </TableRow>
        ))}
      </TableBody>
    </TableShell>
  );
}

// ── Shared primitives ─────────────────────────────────────────────────────────

function TableShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border">
      <Table>{children}</Table>
    </div>
  );
}

function LoadingSpinner() {
  return (
    <div className="flex justify-center py-12">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-border py-16 text-center">
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

function ClaimsPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const activeTab = (searchParams.get("tab") as Tab | null) ?? "all";
  const { data: summary } = useARSummary();

  const mode = summary?.eraReconciliationMode ?? "auto";
  const pendingCount =
    mode === "confirm" ? (summary?.reconciliationPendingCount ?? 0) : 0;

  function setTab(tab: Tab) {
    router.push(`/billing/claims?tab=${tab}`);
  }

  return (
    <div className="flex flex-col gap-6 p-6">
      <PageHeader title="Claims" description="Insurance claims and A/R management." />

      <div className="flex gap-1 border-b border-border">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={[
              "relative px-4 py-2 text-sm transition-colors",
              activeTab === key
                ? "border-b-2 border-primary font-medium text-foreground"
                : "text-muted-foreground hover:text-foreground",
            ].join(" ")}
          >
            {label}
            {key === "reconciled" && pendingCount > 0 && (
              <span className="ml-1.5 rounded-full bg-primary px-1.5 py-0.5 text-xs text-primary-foreground">
                {pendingCount}
              </span>
            )}
          </button>
        ))}
      </div>

      {activeTab === "all" && <AllTab />}
      {(activeTab === "awaiting" ||
        activeTab === "underpaid" ||
        activeTab === "problem" ||
        activeTab === "appealing") && <ARTab category={activeTab} />}
      {activeTab === "reconciled" && <ReconciledTab mode={mode} />}
    </div>
  );
}

export default function ClaimsPage() {
  return (
    <Suspense>
      <ClaimsPageInner />
    </Suspense>
  );
}
```

- [ ] **Step 2: Redirect the insurance-ar page**

Replace the entire content of `apps/web/app/(app)/billing/insurance-ar/page.tsx` with:

```typescript
import { redirect } from "next/navigation";

export default function InsuranceARPage() {
  redirect("/billing/claims?tab=awaiting");
}
```

- [ ] **Step 3: Run TS type check**

```bash
cd apps/web && pnpm tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add apps/web/app/(app)/billing/claims/page.tsx \
        apps/web/app/(app)/billing/insurance-ar/page.tsx
git commit -m "feat: unified 6-tab claims page with Reconciled tab; redirect insurance-ar"
```

---

## Self-review notes

After all tasks are complete, run the full backend test suite one final time:

```bash
cd apps/api && uv run pytest tests/services/ tests/routers/ -v --ignore=tests/integration -q
cd apps/api && uv run ruff check . && uv run mypy app/
```

**Integration tests** (require a real DB — ask before running):
`tests/integration/` — do not run these without being asked.

**Manual smoke checks** (no automated tests for frontend):
1. Navigate to `/billing` — confirm 3 cards render with numbers (may be $0.00 in dev)
2. Navigate to `/billing/claims?tab=awaiting` — confirm awaiting claims show
3. Navigate to `/billing/claims?tab=reconciled` — confirm tab renders (may be empty)
4. Navigate to `/billing/insurance-ar` — confirm redirect lands on `/billing/claims?tab=awaiting`
5. In auto mode: Reconciled tab shows no Confirm buttons, no badge
6. To test confirm mode: set `automation_config = {"era_reconciliation_mode": "confirm"}` on a practice via psql, then verify badge appears and Confirm button shows on reconciliation rows
