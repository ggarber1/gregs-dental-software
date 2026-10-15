# Patient Aging + Statements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give front-desk staff a patient A/R aging worklist and the ability to preview, email, and download PDF billing statements for patients with an outstanding balance.

**Architecture:** Aging is a ledger-derived report: live, un-reversed `ledger_entries` are loaded per patient and bucketed in Python by charge age (0–30 / 31–60 / 61–90 / 90+), with payments and adjustments reported as a single credits total. One pure bucketing function feeds both the worklist endpoint (in the existing `reports` router) and the statement PDF. Statements are rendered from a Jinja2 HTML template through WeasyPrint, emailed via SES `SendRawEmail` with the PDF attached, and every delivery is recorded in a new append-only `patient_statements` table. PDFs are never stored; they are regenerated on demand.

**Tech Stack:** FastAPI · SQLAlchemy 2 async · Alembic · Pydantic v2 (generated from Zod) · Jinja2 · WeasyPrint · boto3/SES · Next.js 15 · TanStack Query · Tailwind · vitest · pytest

**Spec:** `docs/superpowers/specs/2026-08-05-patient-aging-statements-design.md`

---

## Decisions that differ from the spec (made during planning, verified against the code — do not re-litigate)

1. **Aging service lives in `app/services/reports/patient_aging.py`, not `app/services/statements/aging.py`.** It is a report served by the existing `reports` router beside `insurance_ar.py` and `reconciliation.py`, and it reuses that module's `age_bucket()` and `Buckets`. Consolidating beats adding a parallel layer.

2. **`GET /reports/patient-aging` goes in the existing `app/routers/reports.py`.** That router's module constant `_FEATURE` is `claims_submission`; this endpoint gates on a second constant `_LEDGER_FEATURE = "billing_ledger"` per the spec's flag decision.

3. **Mutations return JSON only; PDF bytes are served from GET endpoints.** `IdempotencyMiddleware` (`app/middleware/idempotency.py:96-112`) buffers every mutation response and calls `body.decode()` on it. A PDF body raises `UnicodeDecodeError`, which the bare `except Exception` swallows, then the already-drained response is returned with an empty body. GET requests bypass the middleware entirely. So:
   - `POST /patients/{id}/statements` records the row, sends the email if asked, returns `PatientStatement` JSON.
   - `GET /patients/{id}/statements/{statement_id}/pdf` returns bytes for a recorded statement.
   - `GET /patients/{id}/statements/preview` returns bytes and records nothing.
   The web "Download" flow is POST then GET.

4. **Aging is bucketed in Python, not in one SQL query.** The worklist runs four small queries (balances above threshold → entries for those patients → names/emails → last statement per patient) and buckets with the same pure function the PDF uses. One aging implementation, deterministic tests with an injectable clock, and the pattern matches `insurance_ar._patient_name_map`. Per-practice patient A/R is a few hundred rows.

5. **Buckets reuse the existing `ARBuckets` shape (`b0_30` / `b31_60` / `b61_90` / `b90_plus`)** instead of the spec's `current_cents` / `days_31_60_cents` names, for both the API row and the `aging_snapshot` JSON. It is an already-registered Zod schema, keeps both A/R screens speaking the same language, and avoids `--snake-case-field` mangling names that start with digits.

6. **Reversed entries and their reversals are excluded** from aging buckets and from the statement's itemized table (spec §4.1 item 6 requires it for the table; applying it to buckets stops a reversal posted today from showing as a negative "current" amount). Net balance is unchanged because a reversal pair sums to zero. The filter is shared via `app/services/ledger/balance.py`.

7. **The worklist returns a flat list, not a paginated envelope.** Every other worklist (`/reports/insurance-ar/claims`, `/reports/reconciliation/claims`) returns a flat list, and the spec's own example response is a bare array.

8. **Threshold is inclusive:** a patient appears when `balance >= min_balance_cents` (default 500), so a $5.00 balance shows under the default filter. "Show all" on the page sends `min_balance_cents=1`.

9. **Ledger tab uses three inline buttons (Preview / Email statement / Download PDF), not a send dialog.** Same capability, one fewer component. Disabled states use the native `title` attribute; the app has no global `TooltipProvider` and Radix tooltips do not fire on disabled buttons.

10. **WeasyPrint is imported lazily inside `html_to_pdf()`.** It needs native Pango/HarfBuzz libraries that are absent on the CI runner and on a fresh macOS checkout. The HTML render is a pure function that is fully unit-tested; the WeasyPrint hop is mocked in router and integration tests and exercised by one `importorskip` test wherever the native libs exist.

11. **`send_statement_email` lives in `app/services/statements/service.py`, not `pdf.py`.** `pdf.py` stays pure rendering; the SES call sits with the other I/O in the orchestration module.

12. **Web tests cover exported pure helpers only.** `apps/web/vitest.config.ts` runs in the `node` environment with no jsdom or testing-library, so pages are not rendered in tests. Helpers (`statementFilename`, `lastStatementLabel`, `apiClient.getBlob`) get unit tests; pages are verified by `pnpm lint` and `pnpm type-check`.

---

## File Structure

**Shared schemas (Zod → Pydantic)**
- Create `packages/shared-types/src/schemas/statements.ts` — delivery method, aging row, statement, request
- Modify `packages/shared-types/src/index.ts` — export the module
- Modify `packages/shared-types/scripts/generate-pydantic.ts` — import + register
- Regenerate `apps/api/app/schemas/generated.py` (never hand-edited)

**API — data**
- Create `apps/api/app/models/patient_statement.py` — `PatientStatement` ORM model
- Modify `apps/api/app/models/__init__.py` — register for Alembic
- Create `apps/api/alembic/versions/0039_patient_statements.py`
- Modify `apps/api/tests/integration/conftest.py` — add `patient_statements` to `_TRUNCATE_TABLES`

**API — services**
- Modify `apps/api/app/services/ledger/balance.py` — `unreversed_entry_where()` + `get_unreversed_entries()`
- Create `apps/api/app/services/reports/patient_aging.py` — `AgingBreakdown`, `bucket_ledger_entries()`, `PatientAgingRow`, `get_patient_aging_worklist()`
- Create `apps/api/app/services/statements/__init__.py`
- Create `apps/api/app/services/statements/pdf.py` — context builder, Jinja2 render, WeasyPrint wrapper
- Create `apps/api/app/services/statements/templates/statement.html`
- Create `apps/api/app/services/statements/service.py` — `create_statement`, `list_statements`, `get_statement`, `render_statement_pdf`, `send_statement_email`
- Modify `apps/api/app/services/email.py` — `send_email_with_attachment()`

**API — routers**
- Modify `apps/api/app/routers/reports.py` — `GET /reports/patient-aging`
- Create `apps/api/app/routers/statements.py` — create / list / preview / pdf
- Modify `apps/api/app/main.py` — mount the router

**API — packaging**
- Modify `apps/api/pyproject.toml` + `uv.lock` — add `jinja2`, `weasyprint`
- Modify `apps/api/Dockerfile` — native libs in the runtime stage

**API — tests**
- Create `apps/api/tests/services/test_patient_aging_core.py`
- Create `apps/api/tests/services/test_statement_pdf.py`
- Create `apps/api/tests/services/test_statement_email.py`
- Create `apps/api/tests/routers/test_statements.py`
- Modify `apps/api/tests/routers/test_reports.py`
- Create `apps/api/tests/integration/test_patient_aging_service.py`
- Create `apps/api/tests/integration/test_statements_endpoints.py`

**Web**
- Modify `apps/web/lib/api-client.ts` — `apiClient.getBlob()`
- Modify `apps/web/__tests__/lib/api-client.test.ts`
- Create `apps/web/lib/api/statements.ts` — types, hooks, pure helpers
- Create `apps/web/__tests__/lib/api/statements.test.ts`
- Create `apps/web/app/(app)/billing/patient-aging/page.tsx`
- Modify `apps/web/app/(app)/billing/page.tsx` — wire the Patient A/R tile
- Modify `apps/web/components/patients/LedgerTab.tsx` — statement buttons + history

**Docs**
- Modify `longterm_build_plan.md` — mark the slice BUILT

**Conventions used throughout**
- API commands run from `apps/api` with `uv run …`. Web/shared-types commands run from the repo root with `pnpm …`.
- All new Python is mypy `strict` and ruff line-length 100.
- Services take `now: datetime | None = None` and do `now = now or datetime.now(UTC)` so tests can freeze time.
- Money is integer cents, signed: charges positive, payments/adjustments negative.

---

## Task 1: Shared schemas for aging + statements

**Files:**
- Create: `packages/shared-types/src/schemas/statements.ts`
- Modify: `packages/shared-types/src/index.ts`
- Modify: `packages/shared-types/scripts/generate-pydantic.ts`
- Regenerated: `apps/api/app/schemas/generated.py`

- [ ] **Step 1: Write the Zod schemas**

Create `packages/shared-types/src/schemas/statements.ts`:

```ts
import { z } from "zod";
import { UuidSchema } from "./common.js";
import { ARBucketsSchema } from "./reports.js";

export const StatementDeliveryMethodSchema = z.enum(["email", "download"]);
export type StatementDeliveryMethod = z.infer<typeof StatementDeliveryMethodSchema>;

/**
 * One patient with an outstanding balance. Buckets hold gross charge amounts by
 * age of the charge. Payments and adjustments are not attributed to a bucket;
 * they are reported as a single signed creditsCents total (normally negative).
 */
export const PatientAgingRowSchema = z.object({
  patientId: UuidSchema,
  patientName: z.string(),
  email: z.string().nullable(),
  balanceCents: z.number().int(),
  buckets: ARBucketsSchema,
  creditsCents: z.number().int(),
  oldestChargeAt: z.string().datetime().nullable(),
  lastStatementAt: z.string().datetime().nullable(),
  lastStatementMethod: StatementDeliveryMethodSchema.nullable(),
});
export type PatientAgingRow = z.infer<typeof PatientAgingRowSchema>;

/** Append-only delivery record. `buckets` is the aging snapshot at generation time. */
export const PatientStatementSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  patientId: UuidSchema,
  deliveryMethod: StatementDeliveryMethodSchema,
  balanceCents: z.number().int(),
  buckets: ARBucketsSchema,
  generatedAt: z.string().datetime(),
  deliveredAt: z.string().datetime().nullable(),
  generatedBy: z.string(),
});
export type PatientStatement = z.infer<typeof PatientStatementSchema>;

export const GenerateStatementRequestSchema = z.object({
  deliveryMethod: StatementDeliveryMethodSchema,
});
export type GenerateStatementRequest = z.infer<typeof GenerateStatementRequestSchema>;
```

- [ ] **Step 2: Export the module**

Append to `packages/shared-types/src/index.ts` after the `./schemas/ledger.js` line:

```ts
export * from "./schemas/statements.js";
```

(`reports.js` is deliberately not in `index.ts` today; leave that alone. `statements.ts` imports `ARBucketsSchema` from `./reports.js` directly, which works regardless.)

- [ ] **Step 3: Register with the Pydantic generator**

In `packages/shared-types/scripts/generate-pydantic.ts`, add after the `from "../src/schemas/reports.js";` import block:

```ts
import {
  StatementDeliveryMethodSchema,
  PatientAgingRowSchema,
  PatientStatementSchema,
  GenerateStatementRequestSchema,
} from "../src/schemas/statements.js";
```

and in the `schemas` registry, after the `ARSummary: ARSummarySchema,` line:

```ts
  // Patient Aging + Statements
  StatementDeliveryMethod: StatementDeliveryMethodSchema,
  PatientAgingRow: PatientAgingRowSchema,
  PatientStatement: PatientStatementSchema,
  GenerateStatementRequest: GenerateStatementRequestSchema,
```

- [ ] **Step 4: Regenerate**

From the repo root:

```bash
pnpm generate
```

Expected: the shared-types task prints a success line and `apps/api/app/schemas/generated.py` changes.

- [ ] **Step 5: Verify the generated models**

From `apps/api`:

```bash
uv run python -c "
from app.schemas.generated import PatientAgingRow, PatientStatement, GenerateStatementRequest
print(sorted(PatientAgingRow.model_fields))
print(sorted(PatientStatement.model_fields))
print(sorted(GenerateStatementRequest.model_fields))
"
```

Expected: the first list contains `balance_cents, buckets, credits_cents, email, last_statement_at, last_statement_method, oldest_charge_at, patient_id, patient_name`; the second contains `balance_cents, buckets, delivered_at, delivery_method, generated_at, generated_by, id, patient_id, practice_id`; the third is `['delivery_method']`.

The nested buckets class may be emitted under a suffixed name (`Buckets2` or similar). That is fine: every router builds these models with `model_validate(dict)` keyed by camelCase aliases and never constructs the nested class directly.

- [ ] **Step 6: Commit**

```bash
git add packages/shared-types apps/api/app/schemas/generated.py
git commit -m "feat(statements): add aging + statement shared schemas"
```

---

## Task 2: `patient_statements` table

**Files:**
- Create: `apps/api/app/models/patient_statement.py`
- Modify: `apps/api/app/models/__init__.py`
- Create: `apps/api/alembic/versions/0039_patient_statements.py`
- Modify: `apps/api/tests/integration/conftest.py`

- [ ] **Step 1: Write the ORM model**

Create `apps/api/app/models/patient_statement.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin

DELIVERY_METHODS = ("email", "download")


class PatientStatement(Base, PHIMixin):
    """One generated billing statement (emailed or downloaded). Append-only.

    No PDF is stored — it is regenerated on demand from the ledger. `aging_snapshot`
    preserves the bucket totals the patient saw at delivery time, keyed like
    ARBuckets: {"b0_30", "b31_60", "b61_90", "b90_plus"}.
    """

    __tablename__ = "patient_statements"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    delivery_method: Mapped[str] = mapped_column(String(20), nullable=False)
    balance_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    aging_snapshot: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # When SES accepted the send. Null for downloads.
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    generated_by: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "delivery_method IN ('email', 'download')",
            name="ck_patient_statements_delivery_method",
        ),
        Index(
            "ix_patient_statements_patient_generated",
            "practice_id",
            "patient_id",
            "generated_at",
        ),
        Index("ix_patient_statements_practice_generated", "practice_id", "generated_at"),
    )
```

(Indexes are ascending. Postgres scans them backwards for `ORDER BY generated_at DESC`, so a DESC index buys nothing here.)

- [ ] **Step 2: Register the model**

In `apps/api/app/models/__init__.py`, add in alphabetical position (after the `PatientInsurance` line):

```python
from app.models.patient_statement import PatientStatement as PatientStatement
```

- [ ] **Step 3: Write the migration**

Create `apps/api/alembic/versions/0039_patient_statements.py`:

```python
"""Patient statements (Module 8b) — append-only delivery record

Revision ID: 0039
Revises: 0038
Create Date: 2026-09-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0039"
down_revision: str | Sequence[str] | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "patient_statements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delivery_method", sa.String(20), nullable=False),
        sa.Column("balance_cents", sa.Integer, nullable=False),
        sa.Column("aging_snapshot", postgresql.JSONB, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_by", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_by", sa.String(255), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "delivery_method IN ('email', 'download')",
            name="ck_patient_statements_delivery_method",
        ),
    )
    op.create_index(
        "ix_patient_statements_patient_generated",
        "patient_statements",
        ["practice_id", "patient_id", "generated_at"],
    )
    op.create_index(
        "ix_patient_statements_practice_generated",
        "patient_statements",
        ["practice_id", "generated_at"],
    )


def downgrade() -> None:
    op.drop_table("patient_statements")
```

- [ ] **Step 4: Add the table to the integration truncate list**

In `apps/api/tests/integration/conftest.py`, `_TRUNCATE_TABLES` starts with `"ledger_entries",`. Insert `"patient_statements",` as the new first element:

```python
_TRUNCATE_TABLES = (
    "patient_statements",
    "ledger_entries",
    ...
```

- [ ] **Step 5: Round-trip the migration**

From `apps/api` (local Postgres running):

```bash
uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head
```

Expected: three `Running upgrade/downgrade` lines, no errors.

- [ ] **Step 6: Lint and type-check**

```bash
uv run ruff check . && uv run mypy app/
```

Expected: `All checks passed!` and `Success: no issues found`.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/models apps/api/alembic/versions/0039_patient_statements.py apps/api/tests/integration/conftest.py
git commit -m "feat(statements): add patient_statements table (migration 0039)"
```

---

## Task 3: Shared "unreversed entries" ledger filter

`balance.py` only filters `deleted_at`; reversal pairs stay in the list and net to zero. Aging needs both sides of a reversal excluded (see decision 6). `posting._live_charges_by_proc` already has the right WHERE clause; this task lifts it into `balance.py` so aging and the PDF share it.

**Files:**
- Modify: `apps/api/app/services/ledger/balance.py`
- Test: `apps/api/tests/integration/test_patient_aging_service.py` (created here, extended in Task 5)

- [ ] **Step 1: Write the failing integration test**

Create `apps/api/tests/integration/test_patient_aging_service.py`:

```python
"""Integration tests for the patient aging worklist (Module 8b)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry
from app.models.patient import Patient
from app.models.practice import Practice
from app.services.ledger.balance import get_unreversed_entries

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


async def _seed_practice(session: AsyncSession) -> Practice:
    practice = Practice(id=uuid.uuid4(), name="Aging Test Practice")
    session.add(practice)
    await session.commit()
    return practice


async def _seed_patient(
    session: AsyncSession,
    practice_id: uuid.UUID,
    *,
    first: str = "Pat",
    last: str = "Aging",
    email: str | None = "pat@example.test",
) -> Patient:
    patient = Patient(
        id=uuid.uuid4(),
        practice_id=practice_id,
        first_name=first,
        last_name=last,
        date_of_birth=datetime(1990, 1, 1).date(),
        email=email,
    )
    session.add(patient)
    await session.commit()
    return patient


async def _post(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    *,
    entry_type: str,
    amount_cents: int,
    days_ago: int,
    reverses: uuid.UUID | None = None,
) -> LedgerEntry:
    entry = LedgerEntry(
        id=uuid.uuid4(),
        practice_id=practice_id,
        patient_id=patient_id,
        entry_type=entry_type,
        amount_cents=amount_cents,
        reverses_entry_id=reverses,
        posted_at=_NOW - timedelta(days=days_ago),
    )
    session.add(entry)
    await session.commit()
    return entry


class TestUnreversedEntries:
    async def test_excludes_both_sides_of_a_reversal(self, db_session: AsyncSession):
        practice = await _seed_practice(db_session)
        patient = await _seed_patient(db_session, practice.id)
        kept = await _post(
            db_session, practice.id, patient.id, entry_type="charge", amount_cents=10000, days_ago=5
        )
        wrong = await _post(
            db_session, practice.id, patient.id, entry_type="charge", amount_cents=5000, days_ago=4
        )
        await _post(
            db_session,
            practice.id,
            patient.id,
            entry_type="charge",
            amount_cents=-5000,
            days_ago=1,
            reverses=wrong.id,
        )

        entries = await get_unreversed_entries(db_session, practice.id, {patient.id})

        assert [e.id for e in entries] == [kept.id]

    async def test_returns_oldest_first_across_patients(self, db_session: AsyncSession):
        practice = await _seed_practice(db_session)
        a = await _seed_patient(db_session, practice.id, first="A")
        b = await _seed_patient(db_session, practice.id, first="B")
        newer = await _post(
            db_session, practice.id, a.id, entry_type="charge", amount_cents=100, days_ago=1
        )
        older = await _post(
            db_session, practice.id, b.id, entry_type="charge", amount_cents=100, days_ago=9
        )

        entries = await get_unreversed_entries(db_session, practice.id, {a.id, b.id})

        assert [e.id for e in entries] == [older.id, newer.id]
```

- [ ] **Step 2: Run it to verify it fails**

```bash
uv run pytest -m integration tests/integration/test_patient_aging_service.py -v
```

Expected: FAIL with `ImportError: cannot import name 'get_unreversed_entries'`.

- [ ] **Step 3: Implement the filter**

In `apps/api/app/services/ledger/balance.py`, change the imports to:

```python
from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry
```

and append at the end of the file:

```python
def unreversed_entry_where() -> list[ColumnElement[bool]]:
    """WHERE clauses selecting live entries that are neither a reversal nor reversed.

    A reversal pair (original + mirror) nets to zero, so excluding both sides leaves
    balances unchanged while keeping stale charges out of age buckets and statements.
    """
    reversed_ids = select(LedgerEntry.reverses_entry_id).where(
        LedgerEntry.reverses_entry_id.isnot(None),
        LedgerEntry.deleted_at.is_(None),
    )
    return [
        LedgerEntry.deleted_at.is_(None),
        LedgerEntry.reverses_entry_id.is_(None),
        LedgerEntry.id.notin_(reversed_ids),
    ]


async def get_unreversed_entries(
    session: AsyncSession, practice_id: uuid.UUID, patient_ids: Iterable[uuid.UUID]
) -> list[LedgerEntry]:
    """Live, un-reversed entries for the given patients, oldest-first."""
    ids = list(patient_ids)
    if not ids:
        return []
    rows = (
        await session.scalars(
            select(LedgerEntry)
            .where(
                LedgerEntry.practice_id == practice_id,
                LedgerEntry.patient_id.in_(ids),
                *unreversed_entry_where(),
            )
            .order_by(LedgerEntry.posted_at, LedgerEntry.id)
        )
    ).all()
    return list(rows)
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
uv run pytest -m integration tests/integration/test_patient_aging_service.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Lint, type-check, and run the existing ledger tests**

```bash
uv run ruff check . && uv run mypy app/ && uv run pytest tests/services/test_ledger_balance.py -q
```

Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/ledger/balance.py apps/api/tests/integration/test_patient_aging_service.py
git commit -m "feat(ledger): shared un-reversed entry filter for aging + statements"
```

---

## Task 4: Aging buckets (pure function)

**Files:**
- Create: `apps/api/app/services/reports/patient_aging.py`
- Test: `apps/api/tests/services/test_patient_aging_core.py`

- [ ] **Step 1: Write the failing unit tests**

Create `apps/api/tests/services/test_patient_aging_core.py`:

```python
"""Pure-function tests for patient aging buckets. No DB."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.reports.patient_aging import AgingBreakdown, bucket_ledger_entries

_NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def _entry(entry_type: str, amount: int, days_ago: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        entry_type=entry_type,
        amount_cents=amount,
        posted_at=_NOW - timedelta(days=days_ago),
    )


def test_charges_land_in_the_bucket_for_their_age():
    entries = [
        _entry("charge", 5000, days_ago=0),
        _entry("charge", 4000, days_ago=45),
        _entry("charge", 3000, days_ago=75),
        _entry("charge", 2000, days_ago=120),
    ]
    aging = bucket_ledger_entries(entries, now=_NOW)
    assert aging.buckets.b0_30 == 5000
    assert aging.buckets.b31_60 == 4000
    assert aging.buckets.b61_90 == 3000
    assert aging.buckets.b90_plus == 2000
    assert aging.credits_cents == 0
    assert aging.balance_cents == 14000


def test_bucket_boundaries_are_inclusive_at_30_60_90():
    entries = [
        _entry("charge", 1, days_ago=30),
        _entry("charge", 10, days_ago=31),
        _entry("charge", 100, days_ago=60),
        _entry("charge", 1000, days_ago=61),
        _entry("charge", 10000, days_ago=90),
        _entry("charge", 100000, days_ago=91),
    ]
    aging = bucket_ledger_entries(entries, now=_NOW)
    assert aging.buckets.b0_30 == 1
    assert aging.buckets.b31_60 == 110
    assert aging.buckets.b61_90 == 11000
    assert aging.buckets.b90_plus == 100000


def test_payments_and_adjustments_are_credits_not_bucketed():
    entries = [
        _entry("charge", 10000, days_ago=100),
        _entry("insurance_payment", -6000, days_ago=50),
        _entry("patient_payment", -1000, days_ago=2),
        _entry("adjustment", -500, days_ago=1),
    ]
    aging = bucket_ledger_entries(entries, now=_NOW)
    assert aging.buckets.b90_plus == 10000
    assert aging.buckets.b0_30 == 0
    assert aging.credits_cents == -7500
    assert aging.balance_cents == 2500


def test_all_same_day_is_all_current():
    entries = [_entry("charge", 100, days_ago=0), _entry("charge", 200, days_ago=0)]
    aging = bucket_ledger_entries(entries, now=_NOW)
    assert aging.buckets.b0_30 == 300
    assert aging.buckets.b31_60 == 0
    assert aging.buckets.b61_90 == 0
    assert aging.buckets.b90_plus == 0


def test_oldest_charge_at_ignores_credits():
    entries = [
        _entry("patient_payment", -100, days_ago=200),
        _entry("charge", 100, days_ago=40),
        _entry("charge", 100, days_ago=10),
    ]
    aging = bucket_ledger_entries(entries, now=_NOW)
    assert aging.oldest_charge_at == _NOW - timedelta(days=40)


def test_empty_ledger_is_zero_everywhere():
    aging = bucket_ledger_entries([], now=_NOW)
    assert aging == AgingBreakdown.empty()


def test_credit_balance_is_negative():
    entries = [_entry("charge", 100, days_ago=1), _entry("patient_payment", -300, days_ago=0)]
    aging = bucket_ledger_entries(entries, now=_NOW)
    assert aging.balance_cents == -200
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/services/test_patient_aging_core.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.reports.patient_aging'`.

- [ ] **Step 3: Implement the pure function**

Create `apps/api/app/services/reports/patient_aging.py`:

```python
"""Patient A/R aging (Module 8b).

Charges are bucketed by the age of their posted_at date; payments and adjustments
are not attributed to a bucket and are reported as one signed credits total. This
is the standard small-practice statement layout and avoids FIFO attribution.

`bucket_ledger_entries` is pure and shared by the worklist endpoint and the PDF.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from app.services.reports.insurance_ar import Buckets, age_bucket

DEFAULT_MIN_BALANCE_CENTS = 500

SortBy = Literal["balance", "oldest_charge", "last_statement"]


class _EntryLike(Protocol):
    """The three LedgerEntry attributes aging reads. Lets tests pass plain objects."""

    entry_type: str
    amount_cents: int
    posted_at: datetime


@dataclass(frozen=True)
class AgingBreakdown:
    buckets: Buckets = field(default_factory=Buckets)
    credits_cents: int = 0
    balance_cents: int = 0
    oldest_charge_at: datetime | None = None

    @classmethod
    def empty(cls) -> AgingBreakdown:
        return cls()

    def snapshot(self) -> dict[str, int]:
        """Bucket totals keyed like ARBuckets — stored on patient_statements."""
        b = self.buckets
        return {"b0_30": b.b0_30, "b31_60": b.b31_60, "b61_90": b.b61_90, "b90_plus": b.b90_plus}


def _days_between(anchor: datetime, now: datetime) -> int:
    return (now.date() - anchor.date()).days


def bucket_ledger_entries(entries: Sequence[_EntryLike], *, now: datetime) -> AgingBreakdown:
    """Pure. Entries should already exclude reversal pairs (see
    `ledger.balance.unreversed_entry_where`)."""
    buckets = Buckets()
    credits = 0
    oldest: datetime | None = None
    for e in entries:
        if e.entry_type != "charge":
            credits += e.amount_cents
            continue
        bucket = age_bucket(_days_between(e.posted_at, now))
        if bucket == "0-30":
            buckets.b0_30 += e.amount_cents
        elif bucket == "31-60":
            buckets.b31_60 += e.amount_cents
        elif bucket == "61-90":
            buckets.b61_90 += e.amount_cents
        else:
            buckets.b90_plus += e.amount_cents
        if oldest is None or e.posted_at < oldest:
            oldest = e.posted_at
    charges = buckets.b0_30 + buckets.b31_60 + buckets.b61_90 + buckets.b90_plus
    return AgingBreakdown(
        buckets=buckets,
        credits_cents=credits,
        balance_cents=charges + credits,
        oldest_charge_at=oldest,
    )
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/services/test_patient_aging_core.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Lint and type-check**

```bash
uv run ruff check . && uv run mypy app/
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/reports/patient_aging.py apps/api/tests/services/test_patient_aging_core.py
git commit -m "feat(reports): pure aging bucketer for patient A/R"
```

---

## Task 5: Aging worklist query

**Files:**
- Modify: `apps/api/app/services/reports/patient_aging.py`
- Test: `apps/api/tests/integration/test_patient_aging_service.py`

- [ ] **Step 1: Write the failing integration tests**

Append to `apps/api/tests/integration/test_patient_aging_service.py`. Add to the imports at the top:

```python
from app.models.patient_statement import PatientStatement
from app.services.reports.patient_aging import get_patient_aging_worklist
```

Then append:

```python
class TestPatientAgingWorklist:
    async def test_buckets_ordering_and_exclusions(self, db_session: AsyncSession):
        practice = await _seed_practice(db_session)
        big = await _seed_patient(db_session, practice.id, first="Big", last="Balance")
        small = await _seed_patient(db_session, practice.id, first="Small", last="Balance")
        zero = await _seed_patient(db_session, practice.id, first="Zero", last="Balance")
        credit = await _seed_patient(db_session, practice.id, first="Credit", last="Balance")

        # big: 100 current + 200 (31-60) + 300 (61-90) + 400 (90+), minus 50 paid = 950
        await _post(db_session, practice.id, big.id, entry_type="charge", amount_cents=100, days_ago=1)
        await _post(db_session, practice.id, big.id, entry_type="charge", amount_cents=200, days_ago=40)
        await _post(db_session, practice.id, big.id, entry_type="charge", amount_cents=300, days_ago=70)
        await _post(db_session, practice.id, big.id, entry_type="charge", amount_cents=400, days_ago=100)
        await _post(
            db_session, practice.id, big.id, entry_type="patient_payment", amount_cents=-50, days_ago=0
        )
        # small: 600 current
        await _post(db_session, practice.id, small.id, entry_type="charge", amount_cents=600, days_ago=3)
        # zero: charged and fully paid
        await _post(db_session, practice.id, zero.id, entry_type="charge", amount_cents=700, days_ago=3)
        await _post(
            db_session, practice.id, zero.id, entry_type="patient_payment", amount_cents=-700, days_ago=1
        )
        # credit: overpaid
        await _post(db_session, practice.id, credit.id, entry_type="charge", amount_cents=100, days_ago=3)
        await _post(
            db_session, practice.id, credit.id, entry_type="patient_payment", amount_cents=-300, days_ago=1
        )

        rows = await get_patient_aging_worklist(db_session, practice.id, now=_NOW)

        assert [r.patient_id for r in rows] == [big.id, small.id]
        b = rows[0]
        assert b.patient_name == "Big Balance"
        assert b.email == "pat@example.test"
        assert b.aging.buckets.b0_30 == 100
        assert b.aging.buckets.b31_60 == 200
        assert b.aging.buckets.b61_90 == 300
        assert b.aging.buckets.b90_plus == 400
        assert b.aging.credits_cents == -50
        assert b.aging.balance_cents == 950
        assert b.aging.oldest_charge_at == _NOW - timedelta(days=100)
        assert b.last_statement_at is None
        assert b.last_statement_method is None

    async def test_min_balance_is_inclusive(self, db_session: AsyncSession):
        practice = await _seed_practice(db_session)
        exact = await _seed_patient(db_session, practice.id, first="Exact")
        under = await _seed_patient(db_session, practice.id, first="Under")
        await _post(db_session, practice.id, exact.id, entry_type="charge", amount_cents=500, days_ago=1)
        await _post(db_session, practice.id, under.id, entry_type="charge", amount_cents=499, days_ago=1)

        default_rows = await get_patient_aging_worklist(db_session, practice.id, now=_NOW)
        all_rows = await get_patient_aging_worklist(
            db_session, practice.id, min_balance_cents=1, now=_NOW
        )

        assert [r.patient_id for r in default_rows] == [exact.id]
        assert {r.patient_id for r in all_rows} == {exact.id, under.id}

    async def test_reversal_pair_does_not_age(self, db_session: AsyncSession):
        practice = await _seed_practice(db_session)
        patient = await _seed_patient(db_session, practice.id)
        await _post(db_session, practice.id, patient.id, entry_type="charge", amount_cents=1000, days_ago=2)
        wrong = await _post(
            db_session, practice.id, patient.id, entry_type="charge", amount_cents=9000, days_ago=120
        )
        await _post(
            db_session,
            practice.id,
            patient.id,
            entry_type="charge",
            amount_cents=-9000,
            days_ago=0,
            reverses=wrong.id,
        )

        rows = await get_patient_aging_worklist(db_session, practice.id, now=_NOW)

        assert len(rows) == 1
        assert rows[0].aging.buckets.b90_plus == 0
        assert rows[0].aging.buckets.b0_30 == 1000
        assert rows[0].aging.balance_cents == 1000

    async def test_sort_modes(self, db_session: AsyncSession):
        practice = await _seed_practice(db_session)
        never = await _seed_patient(db_session, practice.id, first="Never")
        recent = await _seed_patient(db_session, practice.id, first="Recent")
        stale = await _seed_patient(db_session, practice.id, first="Stale")
        await _post(db_session, practice.id, never.id, entry_type="charge", amount_cents=1000, days_ago=10)
        await _post(db_session, practice.id, recent.id, entry_type="charge", amount_cents=3000, days_ago=95)
        await _post(db_session, practice.id, stale.id, entry_type="charge", amount_cents=2000, days_ago=50)
        for pid, days in ((recent.id, 2), (stale.id, 30)):
            db_session.add(
                PatientStatement(
                    id=uuid.uuid4(),
                    practice_id=practice.id,
                    patient_id=pid,
                    delivery_method="email",
                    balance_cents=1,
                    aging_snapshot={"b0_30": 1, "b31_60": 0, "b61_90": 0, "b90_plus": 0},
                    generated_at=_NOW - timedelta(days=days),
                    delivered_at=_NOW - timedelta(days=days),
                    generated_by="test",
                )
            )
        await db_session.commit()

        by_balance = await get_patient_aging_worklist(db_session, practice.id, now=_NOW)
        by_oldest = await get_patient_aging_worklist(
            db_session, practice.id, sort_by="oldest_charge", now=_NOW
        )
        by_statement = await get_patient_aging_worklist(
            db_session, practice.id, sort_by="last_statement", now=_NOW
        )

        assert [r.patient_id for r in by_balance] == [recent.id, stale.id, never.id]
        assert [r.patient_id for r in by_oldest] == [recent.id, stale.id, never.id]
        assert [r.patient_id for r in by_statement] == [never.id, stale.id, recent.id]
        assert by_balance[0].last_statement_at == _NOW - timedelta(days=2)
        assert by_balance[0].last_statement_method == "email"

    async def test_scoped_to_practice_and_skips_deleted_patients(self, db_session: AsyncSession):
        practice = await _seed_practice(db_session)
        other = await _seed_practice(db_session)
        mine = await _seed_patient(db_session, practice.id, first="Mine")
        theirs = await _seed_patient(db_session, other.id, first="Theirs")
        gone = await _seed_patient(db_session, practice.id, first="Gone")
        gone.deleted_at = _NOW
        await db_session.commit()
        for pid, prac in ((mine.id, practice.id), (theirs.id, other.id), (gone.id, practice.id)):
            await _post(db_session, prac, pid, entry_type="charge", amount_cents=1000, days_ago=1)

        rows = await get_patient_aging_worklist(db_session, practice.id, now=_NOW)

        assert [r.patient_id for r in rows] == [mine.id]
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest -m integration tests/integration/test_patient_aging_service.py -v
```

Expected: FAIL with `ImportError: cannot import name 'get_patient_aging_worklist'`.

- [ ] **Step 3: Implement the worklist**

In `apps/api/app/services/reports/patient_aging.py`, replace the import block with:

```python
from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry
from app.models.patient import Patient
from app.models.patient_statement import PatientStatement
from app.services.ledger.balance import get_unreversed_entries, unreversed_entry_where
from app.services.reports.insurance_ar import Buckets, age_bucket
```

and append to the end of the module:

```python
@dataclass(frozen=True, kw_only=True)
class PatientAgingRow:
    patient_id: uuid.UUID
    patient_name: str
    email: str | None
    aging: AgingBreakdown
    last_statement_at: datetime | None
    last_statement_method: str | None


async def _patient_contact_map(
    session: AsyncSession, practice_id: uuid.UUID, patient_ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, str | None]]:
    """patient_id -> (display name, email) for live patients in this practice.

    Projects only the columns needed — avoids loading full PHI rows.
    """
    rows = (
        await session.execute(
            select(Patient.id, Patient.first_name, Patient.last_name, Patient.email).where(
                Patient.id.in_(patient_ids),
                Patient.practice_id == practice_id,
                Patient.deleted_at.is_(None),
            )
        )
    ).all()
    return {pid: (f"{first} {last}", email) for pid, first, last, email in rows}


async def _last_statement_map(
    session: AsyncSession, practice_id: uuid.UUID, patient_ids: set[uuid.UUID]
) -> dict[uuid.UUID, tuple[datetime, str]]:
    """patient_id -> (generated_at, delivery_method) of the most recent statement."""
    rows = (
        await session.execute(
            select(
                PatientStatement.patient_id,
                PatientStatement.generated_at,
                PatientStatement.delivery_method,
            )
            .where(
                PatientStatement.practice_id == practice_id,
                PatientStatement.patient_id.in_(patient_ids),
                PatientStatement.deleted_at.is_(None),
            )
            .order_by(PatientStatement.patient_id, PatientStatement.generated_at.desc())
            .distinct(PatientStatement.patient_id)
        )
    ).all()
    return {pid: (generated_at, method) for pid, generated_at, method in rows}


def _sort_key(sort_by: SortBy) -> Any:
    if sort_by == "oldest_charge":
        # Oldest debt first; rows with no charge (all-credit) last.
        return lambda r: (
            (0, r.aging.oldest_charge_at.timestamp())
            if r.aging.oldest_charge_at
            else (1, 0.0)
        )
    if sort_by == "last_statement":
        # Never-billed first, then the longest since last statement.
        return lambda r: (
            (1, r.last_statement_at.timestamp()) if r.last_statement_at else (0, 0.0)
        )
    return lambda r: -r.aging.balance_cents


async def get_patient_aging_worklist(
    session: AsyncSession,
    practice_id: uuid.UUID,
    *,
    min_balance_cents: int = DEFAULT_MIN_BALANCE_CENTS,
    sort_by: SortBy = "balance",
    now: datetime | None = None,
) -> list[PatientAgingRow]:
    """Every live patient owing at least `min_balance_cents`, with aging breakdown
    and last-statement metadata. Patients with a zero or credit balance never appear."""
    now = now or datetime.now(UTC)
    threshold = max(min_balance_cents, 1)

    balance_rows = (
        await session.execute(
            select(LedgerEntry.patient_id, func.sum(LedgerEntry.amount_cents))
            .where(LedgerEntry.practice_id == practice_id, *unreversed_entry_where())
            .group_by(LedgerEntry.patient_id)
            .having(func.sum(LedgerEntry.amount_cents) >= threshold)
        )
    ).all()
    patient_ids = {pid for pid, _ in balance_rows}
    if not patient_ids:
        return []

    contacts = await _patient_contact_map(session, practice_id, patient_ids)
    patient_ids = {pid for pid in patient_ids if pid in contacts}
    if not patient_ids:
        return []

    by_patient: dict[uuid.UUID, list[LedgerEntry]] = defaultdict(list)
    for entry in await get_unreversed_entries(session, practice_id, patient_ids):
        by_patient[entry.patient_id].append(entry)
    last = await _last_statement_map(session, practice_id, patient_ids)

    rows: list[PatientAgingRow] = []
    for pid in patient_ids:
        name, email = contacts[pid]
        stmt = last.get(pid)
        rows.append(
            PatientAgingRow(
                patient_id=pid,
                patient_name=name,
                email=email,
                aging=bucket_ledger_entries(by_patient[pid], now=now),
                last_statement_at=stmt[0] if stmt else None,
                last_statement_method=stmt[1] if stmt else None,
            )
        )
    rows.sort(key=_sort_key(sort_by))
    return rows
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest -m integration tests/integration/test_patient_aging_service.py -v
```

Expected: 7 passed (2 from Task 3 + 5 new).

- [ ] **Step 5: Lint and type-check**

```bash
uv run ruff check . && uv run mypy app/
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/reports/patient_aging.py apps/api/tests/integration/test_patient_aging_service.py
git commit -m "feat(reports): patient aging worklist query"
```

---

## Task 6: `GET /reports/patient-aging`

**Files:**
- Modify: `apps/api/app/routers/reports.py`
- Test: `apps/api/tests/routers/test_reports.py`

- [ ] **Step 1: Write the failing router tests**

Append to `apps/api/tests/routers/test_reports.py`. Add to the imports at the top of the file:

```python
from app.services.reports.patient_aging import AgingBreakdown, PatientAgingRow
```

Then append at the end:

```python
# ── GET /reports/patient-aging ────────────────────────────────────────────────


def _aging_row(**overrides):
    base = dict(
        patient_id=uuid.uuid4(),
        patient_name="Jane Smith",
        email="jane@example.com",
        aging=AgingBreakdown(
            buckets=Buckets(b0_30=5000, b31_60=5000, b61_90=3000, b90_plus=2000),
            credits_cents=-1000,
            balance_cents=14000,
            oldest_charge_at=datetime(2026, 5, 1, tzinfo=UTC),
        ),
        last_statement_at=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        last_statement_method="email",
    )
    base.update(overrides)
    return PatientAgingRow(**base)


@pytest.mark.asyncio
async def test_patient_aging_returns_rows_with_buckets():
    from app.main import app

    row = _aging_row()
    with _auth_patches() as headers, patch(
        "app.routers.reports.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.reports.patient_aging.get_patient_aging_worklist",
        new=AsyncMock(return_value=[row]),
    ) as worklist, patch(
        "app.routers.reports.get_session_factory", return_value=_fake_session_factory()
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/reports/patient-aging?sort_by=last_statement&min_balance_cents=1",
                headers=headers,
            )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["patientId"] == str(row.patient_id)
    assert body[0]["patientName"] == "Jane Smith"
    assert body[0]["balanceCents"] == 14000
    assert body[0]["creditsCents"] == -1000
    assert body[0]["buckets"] == {"b0_30": 5000, "b31_60": 5000, "b61_90": 3000, "b90_plus": 2000}
    assert body[0]["lastStatementMethod"] == "email"
    assert body[0]["lastStatementAt"].startswith("2026-07-01T10:00:00")
    kwargs = worklist.call_args.kwargs
    assert kwargs["sort_by"] == "last_statement"
    assert kwargs["min_balance_cents"] == 1


@pytest.mark.asyncio
async def test_patient_aging_null_statement_fields():
    from app.main import app

    row = _aging_row(last_statement_at=None, last_statement_method=None, email=None)
    with _auth_patches() as headers, patch(
        "app.routers.reports.require_feature", new=AsyncMock(return_value=None)
    ), patch(
        "app.routers.reports.patient_aging.get_patient_aging_worklist",
        new=AsyncMock(return_value=[row]),
    ), patch(
        "app.routers.reports.get_session_factory", return_value=_fake_session_factory()
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/reports/patient-aging", headers=headers)

    assert resp.status_code == 200, resp.text
    assert resp.json()[0]["lastStatementAt"] is None
    assert resp.json()[0]["lastStatementMethod"] is None
    assert resp.json()[0]["email"] is None


@pytest.mark.asyncio
async def test_patient_aging_gated_on_billing_ledger():
    from app.main import app

    with _auth_patches() as headers, patch(
        "app.routers.reports.require_feature", new=AsyncMock(side_effect=_feature_off())
    ) as gate, patch(
        "app.routers.reports.get_session_factory", return_value=_fake_session_factory()
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/reports/patient-aging", headers=headers)

    assert resp.status_code == 403
    assert gate.call_args.args[2] == "billing_ledger"


@pytest.mark.asyncio
async def test_patient_aging_rejects_bad_sort():
    from app.main import app

    with _auth_patches() as headers, patch(
        "app.routers.reports.get_session_factory", return_value=_fake_session_factory()
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/reports/patient-aging?sort_by=name", headers=headers)

    assert resp.status_code == 422
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/routers/test_reports.py -k patient_aging -v
```

Expected: 4 FAIL (404 Not Found — route does not exist yet).

- [ ] **Step 3: Add the endpoint**

In `apps/api/app/routers/reports.py`:

Change the `fastapi` import to:

```python
from fastapi import APIRouter, HTTPException, Query, Request
```

Add `PatientAgingRow` to the `app.schemas.generated` import list (alphabetical, after `InsuranceARSummary`).

Change the services import to:

```python
from app.services.reports import insurance_ar, patient_aging, reconciliation
```

Below `_FEATURE = "claims_submission"` add:

```python
# Patient aging is ledger-derived, not claims-derived, so it gates on the ledger flag.
_LEDGER_FEATURE = "billing_ledger"
```

Add a serializer after `_buckets_to_dict`:

```python
def _aging_row_to_dict(r: patient_aging.PatientAgingRow) -> dict[str, Any]:
    return {
        "patientId": r.patient_id,
        "patientName": r.patient_name,
        "email": r.email,
        "balanceCents": r.aging.balance_cents,
        "buckets": _buckets_to_dict(r.aging.buckets),
        "creditsCents": r.aging.credits_cents,
        "oldestChargeAt": r.aging.oldest_charge_at,
        "lastStatementAt": r.last_statement_at,
        "lastStatementMethod": r.last_statement_method,
    }
```

Append the endpoint at the end of the file:

```python
@router.get("/reports/patient-aging", response_model=list[PatientAgingRow])
async def get_patient_aging(
    request: Request,
    sort_by: patient_aging.SortBy = "balance",
    min_balance_cents: int = Query(patient_aging.DEFAULT_MIN_BALANCE_CENTS, ge=0),
) -> list[PatientAgingRow]:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _LEDGER_FEATURE)
        rows = await patient_aging.get_patient_aging_worklist(
            session, practice_id, min_balance_cents=min_balance_cents, sort_by=sort_by
        )
        return [PatientAgingRow.model_validate(_aging_row_to_dict(r)) for r in rows]
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/routers/test_reports.py -v
```

Expected: all pass, including the 4 new tests.

- [ ] **Step 5: Lint and type-check**

```bash
uv run ruff check . && uv run mypy app/
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/routers/reports.py apps/api/tests/routers/test_reports.py
git commit -m "feat(reports): GET /reports/patient-aging"
```

---

## Task 7: PDF dependencies and native libraries

WeasyPrint needs Pango and HarfBuzz at import time. The runtime container currently installs no apt packages at all. Locally, macOS needs Homebrew `pango`; without it the WeasyPrint import fails, which is why Task 8 imports it lazily and why only one test exercises the real renderer.

**Files:**
- Modify: `apps/api/pyproject.toml`, `apps/api/uv.lock`
- Modify: `apps/api/Dockerfile`

- [ ] **Step 1: Add the Python packages**

From `apps/api`:

```bash
uv add jinja2 weasyprint
```

Expected: `pyproject.toml` gains `"jinja2>=3.1.0"` and `"weasyprint>=62.0"` (or newer) in `dependencies`, and `uv.lock` updates.

- [ ] **Step 2: Install native libs locally (macOS)**

```bash
brew install pango
uv run python -c "import weasyprint; print(weasyprint.__version__)"
```

Expected: a version number. If the import fails with `cannot load library 'libgobject-2.0-0'`, re-run with `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` and add that export to your shell profile. If you cannot get it working, continue: every test that touches WeasyPrint is either mocked or `importorskip`.

- [ ] **Step 3: Add the native libs to the runtime image**

In `apps/api/Dockerfile`, in the runtime stage, replace:

```dockerfile
# Non-root user for security
RUN groupadd -r app && useradd -r -g app app
```

with:

```dockerfile
# WeasyPrint (statement PDFs) needs Pango + HarfBuzz + a base font at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libharfbuzz-subset0 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN groupadd -r app && useradd -r -g app app
```

- [ ] **Step 4: Build the image and prove the import works inside it**

From `apps/api`:

```bash
docker build -t dental-api:pdf-check . && docker run --rm dental-api:pdf-check python -c "import weasyprint; print('ok', weasyprint.__version__)"
```

Expected: `ok <version>`.

- [ ] **Step 5: Commit**

```bash
git add apps/api/pyproject.toml apps/api/uv.lock apps/api/Dockerfile
git commit -m "build(api): add jinja2 + weasyprint and Pango runtime libs"
```

---

## Task 8: Statement HTML template and renderer

**Files:**
- Create: `apps/api/app/services/statements/__init__.py` (empty)
- Create: `apps/api/app/services/statements/pdf.py`
- Create: `apps/api/app/services/statements/templates/statement.html`
- Test: `apps/api/tests/services/test_statement_pdf.py`

- [ ] **Step 1: Write the failing unit tests**

Create `apps/api/tests/services/test_statement_pdf.py`:

```python
"""Statement rendering: pure HTML render is fully tested; WeasyPrint is optional."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.reports.insurance_ar import Buckets
from app.services.reports.patient_aging import AgingBreakdown, bucket_ledger_entries
from app.services.statements.pdf import (
    StatementContext,
    build_context,
    render_statement_html,
    usd,
)

_NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def _practice(**overrides):
    base = dict(
        name="Sunrise Dental",
        address_line1="1 Main St",
        address_line2=None,
        city="Boston",
        state="MA",
        zip="02110",
        phone="+16175550100",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _patient(**overrides):
    base = dict(
        id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        first_name="Jane",
        last_name="Smith",
        address_line1="9 Elm Rd",
        address_line2="Apt 2",
        city="Cambridge",
        state="MA",
        zip="02139",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _entry(entry_type: str, amount: int, days_ago: int, memo: str | None = None, method=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        entry_type=entry_type,
        amount_cents=amount,
        posted_at=_NOW - timedelta(days=days_ago),
        memo=memo,
        payment_method=method,
        reverses_entry_id=None,
    )


def test_usd_formats_cents_with_grouping_and_sign():
    assert usd(0) == "$0.00"
    assert usd(5) == "$0.05"
    assert usd(123456) == "$1,234.56"
    assert usd(-250) == "-$2.50"


def test_build_context_lines_and_running_balance():
    entries = [
        _entry("charge", 10000, days_ago=100, memo="D1110 Prophylaxis"),
        _entry("insurance_payment", -6000, days_ago=50),
        _entry("patient_payment", -1000, days_ago=2, method="card"),
    ]
    aging = bucket_ledger_entries(entries, now=_NOW)

    ctx = build_context(
        _practice(), _patient(), entries, aging, statement_date=date(2026, 9, 18)
    )

    assert isinstance(ctx, StatementContext)
    assert ctx.practice_name == "Sunrise Dental"
    assert ctx.practice_address_lines == ["1 Main St", "Boston, MA 02110"]
    assert ctx.patient_name == "Jane Smith"
    assert ctx.patient_address_lines == ["9 Elm Rd", "Apt 2", "Cambridge, MA 02139"]
    assert ctx.account_number == "12345678"
    assert [line.description for line in ctx.lines] == [
        "Charge — D1110 Prophylaxis",
        "Insurance payment",
        "Patient payment (Card)",
    ]
    assert [line.charge_cents for line in ctx.lines] == [10000, None, None]
    assert [line.credit_cents for line in ctx.lines] == [None, 6000, 1000]
    assert [line.running_balance_cents for line in ctx.lines] == [10000, 4000, 3000]
    assert ctx.aging.balance_cents == 3000


def test_build_context_handles_missing_addresses():
    ctx = build_context(
        _practice(address_line1=None, city=None, state=None, zip=None, phone=None),
        _patient(address_line1=None, address_line2=None, city=None, state=None, zip=None),
        [],
        AgingBreakdown.empty(),
        statement_date=date(2026, 9, 18),
    )
    assert ctx.practice_address_lines == []
    assert ctx.patient_address_lines == []
    assert ctx.practice_phone is None


def test_render_html_contains_key_content():
    entries = [_entry("charge", 12345, days_ago=45, memo="D0120 Exam")]
    aging = bucket_ledger_entries(entries, now=_NOW)
    ctx = build_context(_practice(), _patient(), entries, aging, statement_date=date(2026, 9, 18))

    html = render_statement_html(ctx)

    assert "Sunrise Dental" in html
    assert "Jane Smith" in html
    assert "D0120 Exam" in html
    assert "$123.45" in html  # amount due and the 31-60 bucket
    assert "September 18, 2026" in html
    assert "+16175550100" in html
    assert "Thank you for choosing Sunrise Dental" in html
    assert "pay_url" not in html  # the Jinja comment placeholder must not leak


def test_render_html_escapes_user_content():
    entries = [_entry("charge", 100, days_ago=1, memo="<script>alert(1)</script>")]
    aging = bucket_ledger_entries(entries, now=_NOW)
    ctx = build_context(
        _practice(name="Evil & Co"), _patient(), entries, aging, statement_date=date(2026, 9, 18)
    )

    html = render_statement_html(ctx)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "Evil &amp; Co" in html


def test_html_to_pdf_produces_a_pdf_when_weasyprint_is_available():
    pytest.importorskip("weasyprint")
    from app.services.statements.pdf import html_to_pdf

    ctx = build_context(
        _practice(),
        _patient(),
        [],
        AgingBreakdown(buckets=Buckets(b0_30=100), balance_cents=100),
        statement_date=date(2026, 9, 18),
    )
    pdf = html_to_pdf(render_statement_html(ctx))
    assert pdf.startswith(b"%PDF-")
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/services/test_statement_pdf.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.statements'`.

- [ ] **Step 3: Create the package and the template**

Create `apps/api/app/services/statements/__init__.py` as an empty file.

Create `apps/api/app/services/statements/templates/statement.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Statement — {{ ctx.practice_name }}</title>
<style>
  @page { size: Letter; margin: 0.75in; }
  body { font-family: "DejaVu Sans", Helvetica, Arial, sans-serif; font-size: 10.5pt; color: #111; }
  .header { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #222; padding-bottom: 10px; }
  .practice h1 { font-size: 18pt; margin: 0 0 4px 0; }
  .practice p, .patient p { margin: 0; line-height: 1.35; }
  .logo { width: 120px; height: 48px; border: 1px dashed #bbb; color: #bbb; font-size: 8pt; display: flex; align-items: center; justify-content: center; }
  .meta { margin-top: 24px; display: flex; justify-content: space-between; }
  .patient { margin-top: 18px; }  /* window-envelope position: left, ~1.5in from top */
  table { width: 100%; border-collapse: collapse; margin-top: 18px; }
  th, td { padding: 6px 8px; border-bottom: 1px solid #ddd; text-align: left; }
  th { background: #f2f2f2; font-size: 9pt; text-transform: uppercase; letter-spacing: 0.03em; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  .aging td, .aging th { text-align: center; }
  .aging td.due { font-weight: bold; font-size: 12pt; }
  .cta { margin: 18px 0; padding: 10px 12px; background: #f7f7f7; border-left: 4px solid #222; }
  .footer { margin-top: 28px; border-top: 1px solid #ddd; padding-top: 8px; font-size: 9pt; color: #555; text-align: center; }
</style>
</head>
<body>

<div class="header">
  <div class="practice">
    <h1>{{ ctx.practice_name }}</h1>
    {% for line in ctx.practice_address_lines %}<p>{{ line }}</p>{% endfor %}
    {% if ctx.practice_phone %}<p>{{ ctx.practice_phone }}</p>{% endif %}
  </div>
  <div class="logo">logo</div>
</div>

<div class="meta">
  <div class="patient">
    <p><strong>{{ ctx.patient_name }}</strong></p>
    {% for line in ctx.patient_address_lines %}<p>{{ line }}</p>{% endfor %}
  </div>
  <div>
    <p><strong>Statement Date:</strong> {{ ctx.statement_date.strftime("%B %-d, %Y") }}</p>
    <p><strong>Account:</strong> {{ ctx.account_number }}</p>
  </div>
</div>

<table class="aging">
  <thead>
    <tr>
      <th>Current</th><th>31–60 Days</th><th>61–90 Days</th><th>90+ Days</th>
      <th>Payments &amp; Credits</th><th>Amount Due</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>{{ ctx.aging.buckets.b0_30 | usd }}</td>
      <td>{{ ctx.aging.buckets.b31_60 | usd }}</td>
      <td>{{ ctx.aging.buckets.b61_90 | usd }}</td>
      <td>{{ ctx.aging.buckets.b90_plus | usd }}</td>
      <td>{{ ctx.aging.credits_cents | usd }}</td>
      <td class="due">{{ ctx.aging.balance_cents | usd }}</td>
    </tr>
  </tbody>
</table>

<div class="cta">
  Please contact our office{% if ctx.practice_phone %} at {{ ctx.practice_phone }}{% endif %} to arrange payment.
  {# pay_url: add payment URL here when patient portal launches #}
</div>

<table>
  <thead>
    <tr>
      <th>Date</th><th>Description</th>
      <th class="num">Charges</th><th class="num">Credits</th><th class="num">Balance</th>
    </tr>
  </thead>
  <tbody>
    {% for line in ctx.lines %}
    <tr>
      <td>{{ line.posted_on.isoformat() }}</td>
      <td>{{ line.description }}</td>
      <td class="num">{% if line.charge_cents is not none %}{{ line.charge_cents | usd }}{% endif %}</td>
      <td class="num">{% if line.credit_cents is not none %}{{ line.credit_cents | usd }}{% endif %}</td>
      <td class="num">{{ line.running_balance_cents | usd }}</td>
    </tr>
    {% else %}
    <tr><td colspan="5">No activity on this account.</td></tr>
    {% endfor %}
  </tbody>
</table>

<div class="footer">
  {% if ctx.practice_phone %}Questions? Call {{ ctx.practice_phone }}. {% endif %}
  Thank you for choosing {{ ctx.practice_name }}.
</div>

</body>
</html>
```

- [ ] **Step 4: Write the renderer**

Create `apps/api/app/services/statements/pdf.py`:

```python
"""Statement rendering: ledger → template context → HTML → PDF.

`build_context` and `render_statement_html` are pure. `html_to_pdf` imports
WeasyPrint lazily because it needs native Pango/HarfBuzz libraries that are not
present on every dev machine or the CI runner.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.services.reports.patient_aging import AgingBreakdown

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_ENTRY_TYPE_LABEL = {
    "charge": "Charge",
    "insurance_payment": "Insurance payment",
    "patient_payment": "Patient payment",
    "adjustment": "Adjustment",
}
_PAYMENT_METHOD_LABEL = {
    "cash": "Cash",
    "check": "Check",
    "card": "Card",
    "external_terminal": "External terminal",
    "other": "Other",
}


class _PracticeLike(Protocol):
    name: str
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    zip: str | None
    phone: str | None


class _PatientLike(Protocol):
    id: object
    first_name: str
    last_name: str
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    zip: str | None


class _EntryLike(Protocol):
    entry_type: str
    amount_cents: int
    posted_at: datetime
    memo: str | None
    payment_method: str | None


@dataclass(frozen=True)
class StatementLine:
    posted_on: date
    description: str
    charge_cents: int | None
    credit_cents: int | None
    running_balance_cents: int


@dataclass(frozen=True)
class StatementContext:
    practice_name: str
    practice_address_lines: list[str]
    practice_phone: str | None
    patient_name: str
    patient_address_lines: list[str]
    account_number: str
    statement_date: date
    aging: AgingBreakdown
    lines: list[StatementLine]


def usd(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


def _address_lines(
    line1: str | None, line2: str | None, city: str | None, state: str | None, zip_: str | None
) -> list[str]:
    lines = [line for line in (line1, line2) if line]
    city_state = ", ".join(part for part in (city, state) if part)
    last = " ".join(part for part in (city_state, zip_) if part)
    if last:
        lines.append(last)
    return lines


def _describe(entry: _EntryLike) -> str:
    parts = [_ENTRY_TYPE_LABEL.get(entry.entry_type, entry.entry_type)]
    if entry.entry_type == "patient_payment" and entry.payment_method:
        label = _PAYMENT_METHOD_LABEL.get(entry.payment_method, entry.payment_method)
        parts.append(f"({label})")
    if entry.memo:
        parts.append(f"— {entry.memo}")
    return " ".join(parts)


def build_context(
    practice: _PracticeLike,
    patient: _PatientLike,
    entries: Sequence[_EntryLike],
    aging: AgingBreakdown,
    *,
    statement_date: date,
) -> StatementContext:
    """Pure. `entries` must be oldest-first and already exclude reversal pairs."""
    lines: list[StatementLine] = []
    running = 0
    for entry in entries:
        running += entry.amount_cents
        lines.append(
            StatementLine(
                posted_on=entry.posted_at.date(),
                description=_describe(entry),
                charge_cents=entry.amount_cents if entry.amount_cents > 0 else None,
                credit_cents=-entry.amount_cents if entry.amount_cents < 0 else None,
                running_balance_cents=running,
            )
        )
    return StatementContext(
        practice_name=practice.name,
        practice_address_lines=_address_lines(
            practice.address_line1, practice.address_line2, practice.city, practice.state, practice.zip
        ),
        practice_phone=practice.phone,
        patient_name=f"{patient.first_name} {patient.last_name}",
        patient_address_lines=_address_lines(
            patient.address_line1, patient.address_line2, patient.city, patient.state, patient.zip
        ),
        account_number=str(patient.id)[:8],
        statement_date=statement_date,
        aging=aging,
        lines=lines,
    )


_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)
_env.filters["usd"] = usd


def render_statement_html(ctx: StatementContext) -> str:
    return _env.get_template("statement.html").render(ctx=ctx)


def html_to_pdf(html: str) -> bytes:
    """Render HTML to PDF bytes. Imported lazily — see module docstring."""
    from weasyprint import HTML

    result: bytes = HTML(string=html).write_pdf()
    return result
```

- [ ] **Step 5: Run to verify pass**

```bash
uv run pytest tests/services/test_statement_pdf.py -v
```

Expected: 6 passed, or 5 passed + 1 skipped if WeasyPrint's native libs are missing locally.

- [ ] **Step 6: Lint and type-check**

```bash
uv run ruff check . && uv run mypy app/
```

Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/services/statements apps/api/tests/services/test_statement_pdf.py
git commit -m "feat(statements): statement HTML template + renderer"
```

---

## Task 9: Email a PDF attachment via SES

`send_email()` uses the SES `SendEmail` action, which cannot carry attachments. Attachments need `SendRawEmail` with a MIME document. This adds a sibling function; the reminder path is untouched.

**Files:**
- Modify: `apps/api/app/services/email.py`
- Test: `apps/api/tests/services/test_statement_email.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/services/test_statement_email.py`:

```python
"""SES raw-email attachment sending. boto3 is mocked."""

from __future__ import annotations

import email
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from app.services.email import send_email_with_attachment


def _settings(from_address: str = "billing@sunrise.test", config_set: str = ""):
    return SimpleNamespace(
        ses_from_address=from_address,
        ses_configuration_set=config_set,
        aws_region="us-east-1",
        aws_endpoint_url=None,
    )


async def _send(**overrides):
    kwargs = dict(
        to="jane@example.com",
        subject="Statement from Sunrise Dental",
        html_body="<p>Your statement is attached.</p>",
        text_body="Your statement is attached.",
        attachment_bytes=b"%PDF-1.7 fake",
        attachment_filename="statement-2026-09-18.pdf",
    )
    kwargs.update(overrides)
    return await send_email_with_attachment(**kwargs)


async def test_builds_mime_with_pdf_attachment():
    client = MagicMock()
    client.send_raw_email.return_value = {"MessageId": "msg-123"}
    with (
        patch("app.services.email.get_settings", return_value=_settings(config_set="cs-1")),
        patch("app.services.email.boto3.client", return_value=client),
    ):
        message_id = await _send()

    assert message_id == "msg-123"
    kwargs = client.send_raw_email.call_args.kwargs
    assert kwargs["Source"] == "billing@sunrise.test"
    assert kwargs["Destinations"] == ["jane@example.com"]
    assert kwargs["ConfigurationSetName"] == "cs-1"
    parsed = email.message_from_bytes(kwargs["RawMessage"]["Data"])
    assert parsed["Subject"] == "Statement from Sunrise Dental"
    assert parsed["From"] == "billing@sunrise.test"
    assert parsed["To"] == "jane@example.com"
    attachments = [p for p in parsed.walk() if p.get_filename() == "statement-2026-09-18.pdf"]
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == "application/pdf"
    assert attachments[0].get_payload(decode=True) == b"%PDF-1.7 fake"
    bodies = {p.get_content_type() for p in parsed.walk() if not p.is_multipart()}
    assert {"text/plain", "text/html"} <= bodies


async def test_skips_when_ses_unconfigured():
    with (
        patch("app.services.email.get_settings", return_value=_settings(from_address="")),
        patch("app.services.email.boto3.client") as boto,
    ):
        result = await _send()
    assert result is None
    boto.assert_not_called()


async def test_raises_runtime_error_on_ses_failure():
    client = MagicMock()
    client.send_raw_email.side_effect = ClientError(
        {"Error": {"Code": "MessageRejected", "Message": "nope"}}, "SendRawEmail"
    )
    with (
        patch("app.services.email.get_settings", return_value=_settings()),
        patch("app.services.email.boto3.client", return_value=client),
        pytest.raises(RuntimeError, match="SES send_raw_email failed"),
    ):
        await _send()
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/services/test_statement_email.py -v
```

Expected: FAIL with `ImportError: cannot import name 'send_email_with_attachment'`.

- [ ] **Step 3: Implement**

In `apps/api/app/services/email.py`, add to the imports:

```python
from email.message import EmailMessage
```

and append at the end of the file:

```python
async def send_email_with_attachment(
    *,
    to: str,
    subject: str,
    html_body: str,
    text_body: str,
    attachment_bytes: bytes,
    attachment_filename: str,
    attachment_maintype: str = "application",
    attachment_subtype: str = "pdf",
) -> str | None:
    """Send a MIME email with one attachment via SES SendRawEmail.

    Same contract as `send_email`: returns the SES MessageId, or None in dev
    (no-send) mode; raises RuntimeError on SES errors.
    """
    settings = get_settings()

    if not settings.ses_from_address:
        logger.info(
            "Email send skipped (SES not configured). To=%s Subject=%s Attachment=%s",
            to,
            subject,
            attachment_filename,
        )
        return None

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.ses_from_address
    msg["To"] = to
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    msg.add_attachment(
        attachment_bytes,
        maintype=attachment_maintype,
        subtype=attachment_subtype,
        filename=attachment_filename,
    )

    client = boto3.client(
        "ses",
        region_name=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url or None,
    )
    kwargs: dict[str, object] = {
        "Source": settings.ses_from_address,
        "Destinations": [to],
        "RawMessage": {"Data": msg.as_bytes()},
    }
    if settings.ses_configuration_set:
        kwargs["ConfigurationSetName"] = settings.ses_configuration_set

    try:
        response = client.send_raw_email(**kwargs)
    except (BotoCoreError, ClientError) as exc:
        raise RuntimeError(f"SES send_raw_email failed: {exc}") from exc

    message_id: str = response["MessageId"]
    logger.info("Email with attachment sent to %s (SES MessageId=%s)", to, message_id)
    return message_id
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/services/test_statement_email.py tests/workers/test_reminder_delivery.py -v
```

Expected: all pass (the reminder tests prove `send_email` is untouched).

- [ ] **Step 5: Lint and type-check**

```bash
uv run ruff check . && uv run mypy app/
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/email.py apps/api/tests/services/test_statement_email.py
git commit -m "feat(email): send_email_with_attachment via SES SendRawEmail"
```

---

## Task 10: Statement orchestration service

Ties Tasks 3, 4, 8 and 9 together. Router stays thin: it maps the exceptions raised here to HTTP codes.

**Files:**
- Create: `apps/api/app/services/statements/service.py`
- Test: `apps/api/tests/integration/test_statements_endpoints.py` (service-level tests created here; HTTP tests added in Task 12)

- [ ] **Step 1: Write the failing integration tests**

Create `apps/api/tests/integration/test_statements_endpoints.py`:

```python
"""Integration tests for statement generation (service + HTTP)."""

from __future__ import annotations

import datetime
import uuid
from datetime import UTC, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry
from app.models.patient import Patient
from app.models.patient_statement import PatientStatement
from app.models.practice import Practice
from app.models.user import PracticeUser, User
from app.services.statements import service as statements
from tests.integration.conftest import mut

pytestmark = pytest.mark.integration

_NOW = datetime.datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
_FAKE_PDF = b"%PDF-1.7 fake statement"

# Patch targets — both are imported by name into the service module.
_P_PDF = "app.services.statements.service.html_to_pdf"
_P_SEND = "app.services.statements.service.send_email_with_attachment"

# Auth patch targets (mirrored from test_ledger_endpoints.py)
_P_HEADER = "app.middleware.auth.jwt.get_unverified_header"
_P_KEY = "app.middleware.auth._get_public_key"
_P_DECODE = "app.middleware.auth.jwt.decode"


async def _seed(
    session: AsyncSession,
    *,
    ledger_enabled: bool = True,
    role: str = "admin",
    email: str | None = "pat@example.test",
):
    practice = Practice(
        id=uuid.uuid4(),
        name="Statement Test Practice",
        phone="+16175550100",
        address_line1="1 Main St",
        city="Boston",
        state="MA",
        zip="02110",
        features={"billing_ledger": ledger_enabled},
    )
    session.add(practice)

    cognito_sub = f"stmt-sub-{uuid.uuid4().hex}"
    user = User(
        id=uuid.uuid4(),
        cognito_sub=cognito_sub,
        email=f"stmt-staff-{uuid.uuid4().hex[:6]}@test.local",
        full_name="Statement Staff",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    session.add(PracticeUser(practice_id=practice.id, user_id=user.id, role=role, is_active=True))

    patient = Patient(
        id=uuid.uuid4(),
        practice_id=practice.id,
        first_name="Pat",
        last_name="Statement",
        date_of_birth=datetime.date(1990, 1, 1),
        email=email,
        address_line1="9 Elm Rd",
        city="Cambridge",
        state="MA",
        zip="02139",
    )
    session.add(patient)
    await session.commit()
    return practice, user, cognito_sub, patient


async def _post(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    *,
    entry_type: str = "charge",
    amount_cents: int,
    days_ago: int = 1,
    reverses: uuid.UUID | None = None,
) -> LedgerEntry:
    entry = LedgerEntry(
        id=uuid.uuid4(),
        practice_id=practice_id,
        patient_id=patient_id,
        entry_type=entry_type,
        amount_cents=amount_cents,
        reverses_entry_id=reverses,
        posted_at=_NOW - timedelta(days=days_ago),
    )
    session.add(entry)
    await session.commit()
    return entry


async def _statement_rows(session: AsyncSession, patient_id: uuid.UUID) -> list[PatientStatement]:
    rows = await session.scalars(
        select(PatientStatement)
        .where(PatientStatement.patient_id == patient_id)
        .order_by(PatientStatement.generated_at)
    )
    return list(rows)


def _decoded(user, cognito_sub, groups=("admin",)):
    return {"sub": cognito_sub, "email": user.email, "cognito:groups": list(groups)}


def _auth_patches(decoded):
    return (
        patch(_P_HEADER, return_value={"kid": "test-kid"}),
        patch(_P_KEY, new=AsyncMock(return_value="fake-public-key")),
        patch(_P_DECODE, return_value=decoded),
    )


# ── Service ───────────────────────────────────────────────────────────────────


class TestCreateStatementService:
    async def test_email_sends_pdf_and_records_delivered(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=10000, days_ago=45)
        await _post(
            db_session, practice.id, patient.id, entry_type="patient_payment", amount_cents=-2500
        )

        send = AsyncMock(return_value="ses-msg-1")
        with patch(_P_PDF, return_value=_FAKE_PDF), patch(_P_SEND, send):
            row = await statements.create_statement(
                db_session,
                practice.id,
                patient.id,
                delivery_method="email",
                generated_by="user-sub-1",
                now=_NOW,
            )

        assert row.delivery_method == "email"
        assert row.balance_cents == 7500
        assert row.aging_snapshot == {"b0_30": 0, "b31_60": 10000, "b61_90": 0, "b90_plus": 0}
        assert row.generated_at == _NOW
        assert row.delivered_at == _NOW
        assert row.generated_by == "user-sub-1"
        kwargs = send.call_args.kwargs
        assert kwargs["to"] == "pat@example.test"
        assert kwargs["subject"] == "Statement from Statement Test Practice"
        assert kwargs["attachment_bytes"] == _FAKE_PDF
        assert kwargs["attachment_filename"] == "statement-2026-09-18.pdf"
        assert "$75.00" in kwargs["text_body"]
        assert len(await _statement_rows(db_session, patient.id)) == 1

    async def test_download_records_without_sending(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)

        send = AsyncMock()
        with patch(_P_PDF) as pdf, patch(_P_SEND, send):
            row = await statements.create_statement(
                db_session,
                practice.id,
                patient.id,
                delivery_method="download",
                generated_by="user-sub-1",
                now=_NOW,
            )

        assert row.delivery_method == "download"
        assert row.delivered_at is None
        send.assert_not_called()
        pdf.assert_not_called()

    async def test_zero_balance_rejected(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)
        await _post(
            db_session, practice.id, patient.id, entry_type="patient_payment", amount_cents=-600
        )

        with pytest.raises(statements.NoOutstandingBalance):
            await statements.create_statement(
                db_session, practice.id, patient.id, delivery_method="download", generated_by="u"
            )
        assert await _statement_rows(db_session, patient.id) == []

    async def test_email_without_address_rejected(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session, email=None)
        await _post(db_session, practice.id, patient.id, amount_cents=600)

        with pytest.raises(statements.NoPatientEmail):
            await statements.create_statement(
                db_session, practice.id, patient.id, delivery_method="email", generated_by="u"
            )
        assert await _statement_rows(db_session, patient.id) == []

    async def test_ses_failure_records_nothing(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)

        with (
            patch(_P_PDF, return_value=_FAKE_PDF),
            patch(_P_SEND, AsyncMock(side_effect=RuntimeError("SES send_raw_email failed"))),
            pytest.raises(RuntimeError),
        ):
            await statements.create_statement(
                db_session, practice.id, patient.id, delivery_method="email", generated_by="u"
            )
        assert await _statement_rows(db_session, patient.id) == []

    async def test_email_opt_out_is_ignored_for_statements(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        patient.email_opt_out = True
        await db_session.commit()
        await _post(db_session, practice.id, patient.id, amount_cents=600)

        send = AsyncMock(return_value="ses-msg-2")
        with patch(_P_PDF, return_value=_FAKE_PDF), patch(_P_SEND, send):
            await statements.create_statement(
                db_session, practice.id, patient.id, delivery_method="email", generated_by="u"
            )
        send.assert_awaited_once()

    async def test_wrong_practice_is_lookup_error(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        other, _, _, _ = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)

        with pytest.raises(LookupError):
            await statements.create_statement(
                db_session, other.id, patient.id, delivery_method="download", generated_by="u"
            )


class TestListAndRenderService:
    async def test_list_is_most_recent_first_and_practice_scoped(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        other, _, _, _ = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)
        with patch(_P_PDF, return_value=_FAKE_PDF), patch(_P_SEND, AsyncMock(return_value="m")):
            first = await statements.create_statement(
                db_session, practice.id, patient.id, delivery_method="download",
                generated_by="u", now=_NOW - timedelta(days=1),
            )
            second = await statements.create_statement(
                db_session, practice.id, patient.id, delivery_method="email",
                generated_by="u", now=_NOW,
            )

        mine = await statements.list_statements(db_session, practice.id, patient.id)
        theirs = await statements.list_statements(db_session, other.id, patient.id)

        assert [s.id for s in mine] == [second.id, first.id]
        assert theirs == []
        assert await statements.get_statement(db_session, other.id, patient.id, first.id) is None
        found = await statements.get_statement(db_session, practice.id, patient.id, first.id)
        assert found is not None and found.id == first.id

    async def test_render_uses_live_ledger_and_excludes_reversals(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=1000, days_ago=2)
        wrong = await _post(db_session, practice.id, patient.id, amount_cents=9000, days_ago=3)
        await _post(db_session, practice.id, patient.id, amount_cents=-9000, reverses=wrong.id)

        captured: dict[str, str] = {}

        def fake_pdf(html: str) -> bytes:
            captured["html"] = html
            return _FAKE_PDF

        with patch(_P_PDF, side_effect=fake_pdf):
            pdf = await statements.render_statement_pdf(
                db_session, practice.id, patient.id, statement_date=_NOW.date()
            )

        assert pdf == _FAKE_PDF
        assert "$10.00" in captured["html"]
        assert "$90.00" not in captured["html"]
        assert "Pat Statement" in captured["html"]

    async def test_render_preview_requires_balance(self, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        with pytest.raises(statements.NoOutstandingBalance):
            await statements.render_statement_pdf(
                db_session, practice.id, patient.id, statement_date=_NOW.date(), require_balance=True
            )
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest -m integration tests/integration/test_statements_endpoints.py -v
```

Expected: FAIL with `ImportError: cannot import name 'service' from 'app.services.statements'`.

- [ ] **Step 3: Implement the service**

Create `apps/api/app/services/statements/service.py`:

```python
"""Statement orchestration: load ledger → aging → PDF → email/record.

Raises domain exceptions the router maps to HTTP codes:
  LookupError          → 404 patient not in this practice
  NoOutstandingBalance → 400
  NoPatientEmail       → 400
  RuntimeError         → 502 (SES failure, from send_email_with_attachment)
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry
from app.models.patient import Patient
from app.models.patient_statement import PatientStatement
from app.models.practice import Practice
from app.services.email import send_email_with_attachment
from app.services.ledger.balance import get_unreversed_entries
from app.services.reports.patient_aging import AgingBreakdown, bucket_ledger_entries
from app.services.statements.pdf import build_context, html_to_pdf, render_statement_html, usd


class NoOutstandingBalance(ValueError):
    pass


class NoPatientEmail(ValueError):
    pass


def statement_filename(statement_date: date) -> str:
    return f"statement-{statement_date.isoformat()}.pdf"


async def _load_practice_and_patient(
    session: AsyncSession, practice_id: uuid.UUID, patient_id: uuid.UUID
) -> tuple[Practice, Patient]:
    patient = await session.scalar(
        select(Patient).where(
            Patient.id == patient_id,
            Patient.practice_id == practice_id,
            Patient.deleted_at.is_(None),
        )
    )
    if patient is None:
        raise LookupError("Patient not found in this practice")
    practice = await session.scalar(select(Practice).where(Practice.id == practice_id))
    if practice is None:
        raise LookupError("Practice not found")
    return practice, patient


async def _build(
    session: AsyncSession, practice_id: uuid.UUID, patient_id: uuid.UUID, *, now: datetime
) -> tuple[Practice, Patient, list[LedgerEntry], AgingBreakdown]:
    practice, patient = await _load_practice_and_patient(session, practice_id, patient_id)
    entries = await get_unreversed_entries(session, practice_id, [patient_id])
    return practice, patient, entries, bucket_ledger_entries(entries, now=now)


def _render(
    practice: Practice,
    patient: Patient,
    entries: list[LedgerEntry],
    aging: AgingBreakdown,
    statement_date: date,
) -> bytes:
    ctx = build_context(practice, patient, entries, aging, statement_date=statement_date)
    return html_to_pdf(render_statement_html(ctx))


async def render_statement_pdf(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    *,
    statement_date: date,
    require_balance: bool = False,
    now: datetime | None = None,
) -> bytes:
    """PDF bytes for the patient's current ledger, stamped with `statement_date`.

    `require_balance=True` is the preview rule (spec: no statement without a balance).
    Re-downloads of a recorded statement pass False so they still work after payment.
    """
    now = now or datetime.now(UTC)
    practice, patient, entries, aging = await _build(session, practice_id, patient_id, now=now)
    if require_balance and aging.balance_cents <= 0:
        raise NoOutstandingBalance("No outstanding balance.")
    return _render(practice, patient, entries, aging, statement_date)


async def send_statement_email(
    practice: Practice, patient: Patient, pdf: bytes, *, statement_date: date, balance_cents: int
) -> str | None:
    # email_opt_out is deliberately NOT checked here. That flag governs marketing and
    # appointment reminders (see reminder_worker._deliver_email); a billing statement is
    # a transactional communication about money the patient owes.
    assert patient.email  # guarded by create_statement
    phone = f" at {practice.phone}" if practice.phone else ""
    text = (
        f"Your statement from {practice.name} is attached.\n\n"
        f"Amount due: {usd(balance_cents)}\n\n"
        f"Please contact our office{phone} to arrange payment.\n"
    )
    html = (
        f"<p>Your statement from {practice.name} is attached.</p>"
        f"<p><strong>Amount due: {usd(balance_cents)}</strong></p>"
        f"<p>Please contact our office{phone} to arrange payment.</p>"
    )
    return await send_email_with_attachment(
        to=patient.email,
        subject=f"Statement from {practice.name}",
        html_body=html,
        text_body=text,
        attachment_bytes=pdf,
        attachment_filename=statement_filename(statement_date),
    )


async def create_statement(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    *,
    delivery_method: str,
    generated_by: str,
    now: datetime | None = None,
) -> PatientStatement:
    """Generate (and for `email`, deliver) a statement, then record it.

    Nothing is written if validation or SES fails. For `download` no PDF is rendered
    here — the client fetches bytes from the GET endpoint after this returns.
    """
    now = now or datetime.now(UTC)
    practice, patient, entries, aging = await _build(session, practice_id, patient_id, now=now)
    if aging.balance_cents <= 0:
        raise NoOutstandingBalance("No outstanding balance.")
    if delivery_method == "email" and not patient.email:
        raise NoPatientEmail("Patient has no email address on file.")

    delivered_at: datetime | None = None
    if delivery_method == "email":
        pdf = _render(practice, patient, entries, aging, now.date())
        await send_statement_email(
            practice, patient, pdf, statement_date=now.date(), balance_cents=aging.balance_cents
        )
        delivered_at = now

    row = PatientStatement(
        id=uuid.uuid4(),
        practice_id=practice_id,
        patient_id=patient_id,
        delivery_method=delivery_method,
        balance_cents=aging.balance_cents,
        aging_snapshot=aging.snapshot(),
        generated_at=now,
        delivered_at=delivered_at,
        generated_by=generated_by,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_statements(
    session: AsyncSession, practice_id: uuid.UUID, patient_id: uuid.UUID
) -> list[PatientStatement]:
    rows = await session.scalars(
        select(PatientStatement)
        .where(
            PatientStatement.practice_id == practice_id,
            PatientStatement.patient_id == patient_id,
            PatientStatement.deleted_at.is_(None),
        )
        .order_by(PatientStatement.generated_at.desc(), PatientStatement.id)
    )
    return list(rows)


async def get_statement(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    statement_id: uuid.UUID,
) -> PatientStatement | None:
    return await session.scalar(
        select(PatientStatement).where(
            PatientStatement.id == statement_id,
            PatientStatement.practice_id == practice_id,
            PatientStatement.patient_id == patient_id,
            PatientStatement.deleted_at.is_(None),
        )
    )
```

(`delivered_at` is set even when `send_email_with_attachment` returns `None` in dev no-send mode; the send was logged, not rejected. A raised `RuntimeError` is the only failure path and it happens before anything is added to the session.)

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest -m integration tests/integration/test_statements_endpoints.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Lint and type-check**

```bash
uv run ruff check . && uv run mypy app/
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/statements/service.py apps/api/tests/integration/test_statements_endpoints.py
git commit -m "feat(statements): create/list/render statement service"
```

---

## Task 11: Statements router

**Files:**
- Create: `apps/api/app/routers/statements.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/routers/test_statements.py`

- [ ] **Step 1: Write the failing router tests**

Create `apps/api/tests/routers/test_statements.py`:

```python
"""Unit tests for /api/v1/patients/{id}/statements*. Auth, DB and services are mocked."""

from __future__ import annotations

import uuid
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.services.statements import service as statements

_PRACTICE_ID = uuid.uuid4()
_PATIENT_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()
_SUB = "cognito-sub-test"
_JWT_CLAIMS = {"sub": _SUB, "email": "staff@clinic.com", "cognito:groups": []}
_BASE = f"/api/v1/patients/{_PATIENT_ID}/statements"
_PDF = b"%PDF-1.7 fake"


@contextmanager
def _auth_patches(practice_id: uuid.UUID | None = _PRACTICE_ID, role: str = "front_desk"):
    membership_result = (_USER_ID, role) if practice_id is not None else None
    headers: dict[str, str] = {"Authorization": "Bearer fake.jwt.token"}
    if practice_id is not None:
        headers["X-Practice-ID"] = str(practice_id)
    with (
        patch("jose.jwt.get_unverified_header", return_value={"kid": "fake-kid"}),
        patch("app.middleware.auth._get_public_key", new=AsyncMock(return_value=object())),
        patch("jose.jwt.decode", return_value=_JWT_CLAIMS),
        patch(
            "app.middleware.auth._resolve_practice_membership",
            new=AsyncMock(return_value=membership_result),
        ),
        patch(
            "app.middleware.idempotency.get_redis",
            return_value=AsyncMock(get=AsyncMock(return_value=None), setex=AsyncMock()),
        ),
    ):
        yield headers


def _mut(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid.uuid4())}


def _feature_off() -> HTTPException:
    return HTTPException(status_code=403, detail={"error": {"code": "FEATURE_NOT_ENABLED"}})


def _fake_session_factory():
    session = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=cm)


def _statement(**overrides):
    base = dict(
        id=uuid.uuid4(),
        practice_id=_PRACTICE_ID,
        patient_id=_PATIENT_ID,
        delivery_method="email",
        balance_cents=7500,
        aging_snapshot={"b0_30": 0, "b31_60": 7500, "b61_90": 0, "b90_plus": 0},
        generated_at=datetime(2026, 9, 18, 12, 0, tzinfo=UTC),
        delivered_at=datetime(2026, 9, 18, 12, 0, tzinfo=UTC),
        generated_by=_SUB,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@contextmanager
def _router_patches(**service_overrides):
    """Patch the feature gate, the session factory, and any named service functions
    (looked up as attributes of the `statements` module imported by the router)."""
    with ExitStack() as stack:
        stack.enter_context(
            patch("app.routers.statements.require_feature", new=AsyncMock(return_value=None))
        )
        stack.enter_context(
            patch(
                "app.routers.statements.get_session_factory",
                return_value=_fake_session_factory(),
            )
        )
        for name, value in service_overrides.items():
            stack.enter_context(patch(f"app.routers.statements.statements.{name}", new=value))
        yield service_overrides


async def _client():
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_create_email_statement_returns_201_json():
    row = _statement()
    create = AsyncMock(return_value=row)
    with _auth_patches() as headers, _router_patches(create_statement=create):
        async with await _client() as client:
            resp = await client.post(
                _BASE, headers=_mut(headers), json={"deliveryMethod": "email"}
            )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] == str(row.id)
    assert body["deliveryMethod"] == "email"
    assert body["balanceCents"] == 7500
    assert body["buckets"] == {"b0_30": 0, "b31_60": 7500, "b61_90": 0, "b90_plus": 0}
    assert body["deliveredAt"].startswith("2026-09-18T12:00:00")
    assert body["generatedBy"] == _SUB
    kwargs = create.call_args.kwargs
    assert kwargs["delivery_method"] == "email"
    assert kwargs["generated_by"] == _SUB


@pytest.mark.asyncio
async def test_create_download_statement_has_null_delivered_at():
    row = _statement(delivery_method="download", delivered_at=None)
    with _auth_patches() as headers, _router_patches(create_statement=AsyncMock(return_value=row)):
        async with await _client() as client:
            resp = await client.post(
                _BASE, headers=_mut(headers), json={"deliveryMethod": "download"}
            )
    assert resp.status_code == 201, resp.text
    assert resp.json()["deliveredAt"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (statements.NoOutstandingBalance("No outstanding balance."), 400, "NO_OUTSTANDING_BALANCE"),
        (statements.NoPatientEmail("Patient has no email address on file."), 400, "PATIENT_HAS_NO_EMAIL"),
        (LookupError("nope"), 404, "PATIENT_NOT_FOUND"),
        (RuntimeError("SES send_raw_email failed: boom"), 502, "EMAIL_DELIVERY_FAILED"),
    ],
)
async def test_create_statement_error_mapping(exc, status, code):
    with _auth_patches() as headers, _router_patches(
        create_statement=AsyncMock(side_effect=exc)
    ):
        async with await _client() as client:
            resp = await client.post(_BASE, headers=_mut(headers), json={"deliveryMethod": "email"})
    assert resp.status_code == status, resp.text
    assert resp.json()["error"]["code"] == code


@pytest.mark.asyncio
async def test_create_statement_rejects_bad_delivery_method():
    with _auth_patches() as headers, _router_patches(create_statement=AsyncMock()):
        async with await _client() as client:
            resp = await client.post(_BASE, headers=_mut(headers), json={"deliveryMethod": "fax"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_statement_requires_write_role():
    with _auth_patches(role="read_only") as headers, _router_patches(create_statement=AsyncMock()):
        async with await _client() as client:
            resp = await client.post(_BASE, headers=_mut(headers), json={"deliveryMethod": "email"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "INSUFFICIENT_ROLE"


@pytest.mark.asyncio
async def test_list_statements():
    rows = [_statement(), _statement(delivery_method="download", delivered_at=None)]
    with _auth_patches() as headers, _router_patches(list_statements=AsyncMock(return_value=rows)):
        async with await _client() as client:
            resp = await client.get(_BASE, headers=headers)
    assert resp.status_code == 200, resp.text
    assert [s["deliveryMethod"] for s in resp.json()] == ["email", "download"]


@pytest.mark.asyncio
async def test_list_statements_gated_on_billing_ledger():
    from app.main import app

    with _auth_patches() as headers, patch(
        "app.routers.statements.require_feature", new=AsyncMock(side_effect=_feature_off())
    ) as gate, patch(
        "app.routers.statements.get_session_factory", return_value=_fake_session_factory()
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(_BASE, headers=headers)
    assert resp.status_code == 403
    assert gate.call_args.args[2] == "billing_ledger"


@pytest.mark.asyncio
async def test_preview_returns_inline_pdf_and_records_nothing():
    render = AsyncMock(return_value=_PDF)
    create = AsyncMock()
    with _auth_patches() as headers, _router_patches(
        render_statement_pdf=render, create_statement=create
    ):
        async with await _client() as client:
            resp = await client.get(f"{_BASE}/preview", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["content-disposition"].startswith("inline;")
    assert resp.content == _PDF
    assert render.call_args.kwargs["require_balance"] is True
    create.assert_not_called()


@pytest.mark.asyncio
async def test_preview_without_balance_is_400():
    with _auth_patches() as headers, _router_patches(
        render_statement_pdf=AsyncMock(side_effect=statements.NoOutstandingBalance("x"))
    ):
        async with await _client() as client:
            resp = await client.get(f"{_BASE}/preview", headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "NO_OUTSTANDING_BALANCE"


@pytest.mark.asyncio
async def test_statement_pdf_download_uses_recorded_date():
    row = _statement(delivery_method="download", delivered_at=None)
    render = AsyncMock(return_value=_PDF)
    with _auth_patches() as headers, _router_patches(
        get_statement=AsyncMock(return_value=row), render_statement_pdf=render
    ):
        async with await _client() as client:
            resp = await client.get(f"{_BASE}/{row.id}/pdf", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["content-disposition"] == 'attachment; filename="statement-2026-09-18.pdf"'
    assert resp.content == _PDF
    assert render.call_args.kwargs["statement_date"] == row.generated_at.date()
    assert render.call_args.kwargs["require_balance"] is False


@pytest.mark.asyncio
async def test_statement_pdf_unknown_id_is_404():
    with _auth_patches() as headers, _router_patches(get_statement=AsyncMock(return_value=None)):
        async with await _client() as client:
            resp = await client.get(f"{_BASE}/{uuid.uuid4()}/pdf", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "STATEMENT_NOT_FOUND"
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/routers/test_statements.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.routers.statements'` (raised by the patch target).

- [ ] **Step 3: Write the router**

Create `apps/api/app/routers/statements.py`:

```python
"""Patient billing statements (Module 8b).

PDF bytes are only ever served from GET endpoints. IdempotencyMiddleware buffers and
text-decodes every mutation response body, so a POST that returned a PDF would reach
the client empty. The download flow is therefore POST (record) → GET (bytes).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from app.core.db import get_session_factory
from app.core.features import require_feature
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import ApiError, Error, GenerateStatementRequest, PatientStatement
from app.services.statements import service as statements

router = APIRouter(prefix="/api/v1", tags=["statements"])
_FEATURE = "billing_ledger"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True),
    )


def _statement_to_dict(row: Any) -> dict[str, Any]:
    snap = row.aging_snapshot
    return {
        "id": row.id,
        "practiceId": row.practice_id,
        "patientId": row.patient_id,
        "deliveryMethod": row.delivery_method,
        "balanceCents": row.balance_cents,
        "buckets": {
            "b0_30": snap.get("b0_30", 0),
            "b31_60": snap.get("b31_60", 0),
            "b61_90": snap.get("b61_90", 0),
            "b90_plus": snap.get("b90_plus", 0),
        },
        "generatedAt": row.generated_at,
        "deliveredAt": row.delivered_at,
        "generatedBy": row.generated_by,
    }


def _pdf_response(pdf: bytes, *, filename: str, inline: bool) -> Response:
    disposition = "inline" if inline else "attachment"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.get("/patients/{patient_id}/statements", response_model=list[PatientStatement])
async def list_patient_statements(request: Request, patient_id: uuid.UUID) -> list[PatientStatement]:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        rows = await statements.list_statements(session, practice_id, patient_id)
        return [PatientStatement.model_validate(_statement_to_dict(r)) for r in rows]


@router.post(
    "/patients/{patient_id}/statements", response_model=PatientStatement, status_code=201
)
async def create_patient_statement(
    request: Request, patient_id: uuid.UUID, body: GenerateStatementRequest
) -> PatientStatement:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", None) or "system"
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        try:
            row = await statements.create_statement(
                session,
                practice_id,
                patient_id,
                delivery_method=str(body.delivery_method.value),
                generated_by=user_sub,
            )
        except LookupError as exc:
            raise _err(404, "PATIENT_NOT_FOUND", "Patient not found in this practice") from exc
        except statements.NoOutstandingBalance as exc:
            raise _err(400, "NO_OUTSTANDING_BALANCE", str(exc)) from exc
        except statements.NoPatientEmail as exc:
            raise _err(400, "PATIENT_HAS_NO_EMAIL", str(exc)) from exc
        except RuntimeError as exc:
            raise _err(502, "EMAIL_DELIVERY_FAILED", "Statement email could not be sent") from exc
        return PatientStatement.model_validate(_statement_to_dict(row))


@router.get("/patients/{patient_id}/statements/preview", response_class=Response)
async def preview_patient_statement(request: Request, patient_id: uuid.UUID) -> Response:
    """Current statement as PDF. Records nothing."""
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        today = datetime.now(UTC).date()
        try:
            pdf = await statements.render_statement_pdf(
                session, practice_id, patient_id, statement_date=today, require_balance=True
            )
        except LookupError as exc:
            raise _err(404, "PATIENT_NOT_FOUND", "Patient not found in this practice") from exc
        except statements.NoOutstandingBalance as exc:
            raise _err(400, "NO_OUTSTANDING_BALANCE", str(exc)) from exc
    return _pdf_response(pdf, filename=statements.statement_filename(today), inline=True)


@router.get("/patients/{patient_id}/statements/{statement_id}/pdf", response_class=Response)
async def download_patient_statement(
    request: Request, patient_id: uuid.UUID, statement_id: uuid.UUID
) -> Response:
    """PDF for a recorded statement, regenerated from the live ledger and stamped with
    the recorded generation date."""
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        row = await statements.get_statement(session, practice_id, patient_id, statement_id)
        if row is None:
            raise _err(404, "STATEMENT_NOT_FOUND", "Statement not found")
        statement_date = row.generated_at.date()
        try:
            pdf = await statements.render_statement_pdf(
                session, practice_id, patient_id, statement_date=statement_date, require_balance=False
            )
        except LookupError as exc:
            raise _err(404, "PATIENT_NOT_FOUND", "Patient not found in this practice") from exc
    return _pdf_response(pdf, filename=statements.statement_filename(statement_date), inline=False)
```

- [ ] **Step 4: Mount the router**

In `apps/api/app/main.py`, add `statements,` to the `from app.routers import (...)` block in alphabetical position (after `reports,`), and add after `app.include_router(ledger.router)`:

```python
    app.include_router(statements.router)
```

- [ ] **Step 5: Run to verify pass**

```bash
uv run pytest tests/routers/test_statements.py -v
```

Expected: 14 passed (including the 4 parametrized cases).

- [ ] **Step 6: Lint, type-check, full unit suite**

```bash
uv run ruff check . && uv run mypy app/ && uv run pytest -q
```

Expected: clean; all non-integration tests pass.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/routers/statements.py apps/api/app/main.py apps/api/tests/routers/test_statements.py
git commit -m "feat(statements): statements router (create / list / preview / pdf)"
```

---

## Task 12: End-to-end HTTP integration tests

Proves the whole stack against real Postgres: auth middleware, feature flag, idempotency, tenant scoping, and the aging worklist reflecting a sent statement.

**Files:**
- Modify: `apps/api/tests/integration/test_statements_endpoints.py`

- [ ] **Step 1: Append the HTTP tests**

Append to `apps/api/tests/integration/test_statements_endpoints.py`:

```python
# ── HTTP ──────────────────────────────────────────────────────────────────────


def _headers(practice: Practice) -> dict[str, str]:
    return {"Authorization": "Bearer test-token", "X-Practice-ID": str(practice.id)}


class TestStatementsHttp:
    async def test_email_then_history_then_aging(self, client, db_session: AsyncSession):
        practice, user, sub, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=12000, days_ago=40)
        headers = _headers(practice)
        base = f"/api/v1/patients/{patient.id}/statements"
        h, k, d = _auth_patches(_decoded(user, sub))

        send = AsyncMock(return_value="ses-msg-http")
        with h, k, d, patch(_P_PDF, return_value=_FAKE_PDF), patch(_P_SEND, send):
            create = await client.post(base, headers=mut(headers), json={"deliveryMethod": "email"})
            assert create.status_code == 201, create.text
            body = create.json()
            assert body["deliveryMethod"] == "email"
            assert body["balanceCents"] == 12000
            assert body["buckets"]["b31_60"] == 12000
            assert body["deliveredAt"] is not None
            assert body["generatedBy"] == sub
            send.assert_awaited_once()

            history = await client.get(base, headers=headers)
            assert history.status_code == 200, history.text
            assert [s["id"] for s in history.json()] == [body["id"]]

            aging = await client.get("/api/v1/reports/patient-aging", headers=headers)
            assert aging.status_code == 200, aging.text
            rows = aging.json()
            assert len(rows) == 1
            assert rows[0]["patientId"] == str(patient.id)
            assert rows[0]["lastStatementMethod"] == "email"
            assert rows[0]["lastStatementAt"] == body["generatedAt"]

    async def test_download_flow_post_then_get_pdf(self, client, db_session: AsyncSession):
        practice, user, sub, patient = await _seed(db_session, email=None)
        await _post(db_session, practice.id, patient.id, amount_cents=600)
        headers = _headers(practice)
        base = f"/api/v1/patients/{patient.id}/statements"
        h, k, d = _auth_patches(_decoded(user, sub))

        with h, k, d, patch(_P_PDF, return_value=_FAKE_PDF):
            create = await client.post(
                base, headers=mut(headers), json={"deliveryMethod": "download"}
            )
            assert create.status_code == 201, create.text
            assert create.json()["deliveredAt"] is None
            statement_id = create.json()["id"]

            pdf = await client.get(f"{base}/{statement_id}/pdf", headers=headers)
            assert pdf.status_code == 200, pdf.text
            assert pdf.headers["content-type"] == "application/pdf"
            assert pdf.headers["content-disposition"].startswith("attachment;")
            assert pdf.content == _FAKE_PDF

            preview = await client.get(f"{base}/preview", headers=headers)
            assert preview.status_code == 200, preview.text
            assert preview.headers["content-disposition"].startswith("inline;")

        assert len(await _statement_rows(db_session, patient.id)) == 1  # preview recorded nothing

    async def test_validation_errors(self, client, db_session: AsyncSession):
        practice, user, sub, patient = await _seed(db_session, email=None)
        headers = _headers(practice)
        base = f"/api/v1/patients/{patient.id}/statements"
        h, k, d = _auth_patches(_decoded(user, sub))

        with h, k, d:
            no_balance = await client.post(
                base, headers=mut(headers), json={"deliveryMethod": "download"}
            )
            assert no_balance.status_code == 400
            assert no_balance.json()["error"]["code"] == "NO_OUTSTANDING_BALANCE"

            await _post(db_session, practice.id, patient.id, amount_cents=600)
            no_email = await client.post(base, headers=mut(headers), json={"deliveryMethod": "email"})
            assert no_email.status_code == 400
            assert no_email.json()["error"]["code"] == "PATIENT_HAS_NO_EMAIL"

            missing_key = await client.post(base, headers=headers, json={"deliveryMethod": "download"})
            assert missing_key.status_code == 422

    async def test_ses_failure_is_502_and_records_nothing(self, client, db_session: AsyncSession):
        practice, user, sub, patient = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)
        headers = _headers(practice)
        h, k, d = _auth_patches(_decoded(user, sub))

        with (
            h, k, d,
            patch(_P_PDF, return_value=_FAKE_PDF),
            patch(_P_SEND, AsyncMock(side_effect=RuntimeError("SES send_raw_email failed"))),
        ):
            resp = await client.post(
                f"/api/v1/patients/{patient.id}/statements",
                headers=mut(headers),
                json={"deliveryMethod": "email"},
            )
        assert resp.status_code == 502, resp.text
        assert resp.json()["error"]["code"] == "EMAIL_DELIVERY_FAILED"
        assert await _statement_rows(db_session, patient.id) == []

    async def test_other_practice_cannot_see_or_bill_patient(self, client, db_session: AsyncSession):
        practice, _, _, patient = await _seed(db_session)
        other, other_user, other_sub, _ = await _seed(db_session)
        await _post(db_session, practice.id, patient.id, amount_cents=600)
        headers = _headers(other)
        base = f"/api/v1/patients/{patient.id}/statements"
        h, k, d = _auth_patches(_decoded(other_user, other_sub))

        with h, k, d:
            create = await client.post(
                base, headers=mut(headers), json={"deliveryMethod": "download"}
            )
            assert create.status_code == 404
            assert create.json()["error"]["code"] == "PATIENT_NOT_FOUND"
            history = await client.get(base, headers=headers)
            assert history.status_code == 200
            assert history.json() == []
            preview = await client.get(f"{base}/preview", headers=headers)
            assert preview.status_code == 404

    async def test_feature_flag_off_is_403(self, client, db_session: AsyncSession):
        practice, user, sub, patient = await _seed(db_session, ledger_enabled=False)
        headers = _headers(practice)
        h, k, d = _auth_patches(_decoded(user, sub))

        with h, k, d:
            history = await client.get(f"/api/v1/patients/{patient.id}/statements", headers=headers)
            aging = await client.get("/api/v1/reports/patient-aging", headers=headers)
        assert history.status_code == 403
        assert history.json()["error"]["code"] == "FEATURE_NOT_ENABLED"
        assert aging.status_code == 403
```

- [ ] **Step 2: Run the full integration suite**

```bash
uv run pytest -m integration -q
```

Expected: all pass, including the 6 new HTTP tests.

- [ ] **Step 3: Lint**

```bash
uv run ruff check .
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add apps/api/tests/integration/test_statements_endpoints.py
git commit -m "test(statements): end-to-end HTTP integration coverage"
```

---

## Task 13: Web API client (`getBlob` + statements hooks)

The API is on a different origin and reads the bearer token from a header, so a plain `<a href>` or `window.open()` cannot download a PDF. The client must `fetch` with the same headers and hand the browser a Blob.

**Files:**
- Modify: `apps/web/lib/api-client.ts`
- Modify: `apps/web/__tests__/lib/api-client.test.ts`
- Create: `apps/web/lib/api/statements.ts`
- Create: `apps/web/__tests__/lib/api/statements.test.ts`

- [ ] **Step 1: Write the failing `getBlob` tests**

Append to `apps/web/__tests__/lib/api-client.test.ts`:

```ts
describe("apiClient.getBlob", () => {
  beforeEach(() => {
    mockGetAccessToken.mockReturnValue("tok-123");
    mockGetPracticeId.mockReturnValue("practice-1");
  });

  it("sends auth headers without a JSON content-type and returns a Blob", async () => {
    const bytes = new Uint8Array([0x25, 0x50, 0x44, 0x46]); // %PDF
    const response = new Response(bytes, {
      status: 200,
      headers: { "Content-Type": "application/pdf" },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    const blob = await apiClient.getBlob("/api/v1/patients/p1/statements/preview");

    expect(blob.type).toBe("application/pdf");
    expect(blob.size).toBe(4);
    const [url, init] = vi.mocked(fetch).mock.calls[0]!;
    expect(url).toBe(`${API_BASE}/api/v1/patients/p1/statements/preview`);
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer tok-123");
    expect(headers["X-Practice-ID"]).toBe("practice-1");
    expect(headers["Content-Type"]).toBeUndefined();
  });

  it("throws ApiError with the JSON error body on failure", async () => {
    mockFetch(400, { error: { code: "NO_OUTSTANDING_BALANCE", message: "No outstanding balance." } });

    await expect(apiClient.getBlob("/api/v1/x")).rejects.toMatchObject({
      status: 400,
      body: { error: { code: "NO_OUTSTANDING_BALANCE" } },
    });
  });
});
```

- [ ] **Step 2: Run to verify failure**

From the repo root:

```bash
pnpm --filter @dental/web test -- __tests__/lib/api-client.test.ts
```

Expected: 2 new tests FAIL with `apiClient.getBlob is not a function`.

- [ ] **Step 3: Implement `getBlob`**

In `apps/web/lib/api-client.ts`, extract the header block out of `request()` into a shared helper and add a blob path. Replace the body of `request()` from `const headers: Record<string, string> = {` down to the end of the `if (options.idempotencyKey)` block with:

```ts
  const headers = authHeaders({ "Content-Type": "application/json" });
  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }
```

Add above `request()`:

```ts
function authHeaders(base: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = { ...base };
  const token = getAccessToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const practiceId = getPracticeId();
  if (practiceId) {
    headers["X-Practice-ID"] = practiceId;
  }
  return headers;
}

async function throwApiError(response: Response): Promise<never> {
  // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
  const errorBody: unknown = await response
    .json()
    .catch(() => ({ error: { code: "UNKNOWN", message: response.statusText } }));
  throw new ApiError(response.status, errorBody);
}

/** GET a binary resource (PDF) with the same auth headers as JSON requests. */
async function requestBlob(path: string): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "GET",
    headers: authHeaders(),
  });
  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined") {
      window.location.href = "/login";
      return new Blob();
    }
    return throwApiError(response);
  }
  return response.blob();
}
```

In `request()`, replace the three-line error-body parse + `throw new ApiError(...)` with `return throwApiError(response);`.

Add to the `apiClient` object:

```ts
  getBlob: (path: string) => requestBlob(path),
```

- [ ] **Step 4: Run to verify pass**

```bash
pnpm --filter @dental/web test -- __tests__/lib/api-client.test.ts
```

Expected: all pass (existing tests still green).

- [ ] **Step 5: Write the failing statements helper tests**

Create `apps/web/__tests__/lib/api/statements.test.ts`:

```ts
import { describe, it, expect } from "vitest";

import { lastStatementLabel, statementFilename } from "@/lib/api/statements";

describe("statementFilename", () => {
  it("uses the date part of the ISO timestamp", () => {
    expect(statementFilename("2026-09-18T12:00:00Z")).toBe("statement-2026-09-18.pdf");
  });
});

describe("lastStatementLabel", () => {
  const now = new Date("2026-09-18T15:00:00Z");

  it("is Never for null", () => {
    expect(lastStatementLabel(null, now)).toBe("Never");
  });

  it("is Today within the same calendar day", () => {
    expect(lastStatementLabel("2026-09-18T01:00:00Z", now)).toBe("Today");
  });

  it("singular and plural days", () => {
    expect(lastStatementLabel("2026-09-17T12:00:00Z", now)).toBe("1 day ago");
    expect(lastStatementLabel("2026-09-15T12:00:00Z", now)).toBe("3 days ago");
  });

  it("switches to weeks after 13 days", () => {
    expect(lastStatementLabel("2026-09-04T12:00:00Z", now)).toBe("2 weeks ago");
  });

  it("switches to months after 8 weeks", () => {
    expect(lastStatementLabel("2026-06-01T12:00:00Z", now)).toBe("3 months ago");
  });
});
```

- [ ] **Step 6: Run to verify failure**

```bash
pnpm --filter @dental/web test -- __tests__/lib/api/statements.test.ts
```

Expected: FAIL, cannot resolve `@/lib/api/statements`.

- [ ] **Step 7: Write the statements client**

Create `apps/web/lib/api/statements.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { apiClient, ApiError, generateId } from "@/lib/api-client";
import type { ARBuckets } from "@/lib/api/reports";

// ── Types (hand-written, mirroring packages/shared-types/src/schemas/statements.ts) ──

export type StatementDeliveryMethod = "email" | "download";
export type AgingSortBy = "balance" | "oldest_charge" | "last_statement";

export interface PatientAgingRow {
  patientId: string;
  patientName: string;
  email: string | null;
  balanceCents: number;
  buckets: ARBuckets;
  creditsCents: number;
  oldestChargeAt: string | null;
  lastStatementAt: string | null;
  lastStatementMethod: StatementDeliveryMethod | null;
}

export interface PatientStatement {
  id: string;
  practiceId: string;
  patientId: string;
  deliveryMethod: StatementDeliveryMethod;
  balanceCents: number;
  buckets: ARBuckets;
  generatedAt: string;
  deliveredAt: string | null;
  generatedBy: string;
}

export const DEFAULT_MIN_BALANCE_CENTS = 500;

// ── Pure helpers ──────────────────────────────────────────────────────────────

export function statementFilename(generatedAtIso: string): string {
  return `statement-${generatedAtIso.slice(0, 10)}.pdf`;
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** "Never" | "Today" | "N days ago" | "N weeks ago" | "N months ago" */
export function lastStatementLabel(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "Never";
  const then = new Date(iso);
  const days = Math.floor((now.getTime() - then.getTime()) / DAY_MS);
  if (days <= 0 || now.toISOString().slice(0, 10) === then.toISOString().slice(0, 10)) {
    return "Today";
  }
  if (days < 14) return days === 1 ? "1 day ago" : `${days} days ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 9) return `${weeks} weeks ago`;
  const months = Math.floor(days / 30);
  return months === 1 ? "1 month ago" : `${months} months ago`;
}

function apiErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const body = err.body as { error?: { message?: string } } | null;
    return body?.error?.message ?? `Unexpected error (${err.status})`;
  }
  return "Something went wrong. Please try again.";
}

/** Hand a Blob to the browser as a file download. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Open a Blob in a new tab (PDF preview). */
export function openBlob(blob: Blob): void {
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const statementKeys = {
  all: ["statements"] as const,
  patient: (patientId: string) => ["statements", patientId] as const,
  aging: (sortBy: AgingSortBy, minBalanceCents: number) =>
    ["reports", "patient-aging", { sortBy, minBalanceCents }] as const,
};

const AGING_PREFIX = ["reports", "patient-aging"] as const;

// ── Hooks ─────────────────────────────────────────────────────────────────────

export function usePatientAgingWorklist(params: {
  sortBy: AgingSortBy;
  minBalanceCents: number;
}) {
  const search = new URLSearchParams({
    sort_by: params.sortBy,
    min_balance_cents: String(params.minBalanceCents),
  });
  return useQuery({
    queryKey: statementKeys.aging(params.sortBy, params.minBalanceCents),
    queryFn: () =>
      apiClient.get<PatientAgingRow[]>(`/api/v1/reports/patient-aging?${search.toString()}`),
  });
}

export function usePatientStatements(patientId: string) {
  return useQuery({
    queryKey: statementKeys.patient(patientId),
    queryFn: () => apiClient.get<PatientStatement[]>(`/api/v1/patients/${patientId}/statements`),
    enabled: Boolean(patientId),
  });
}

export function fetchStatementPreview(patientId: string): Promise<Blob> {
  return apiClient.getBlob(`/api/v1/patients/${patientId}/statements/preview`);
}

/**
 * POST a statement. For `download`, follows up with a GET for the bytes and
 * triggers the browser save (the API never returns a PDF from a mutation).
 */
export function useSendStatement(patientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (deliveryMethod: StatementDeliveryMethod) => {
      const statement = await apiClient.post<PatientStatement>(
        `/api/v1/patients/${patientId}/statements`,
        { deliveryMethod },
        { idempotencyKey: generateId() },
      );
      if (deliveryMethod === "download") {
        const blob = await apiClient.getBlob(
          `/api/v1/patients/${patientId}/statements/${statement.id}/pdf`,
        );
        saveBlob(blob, statementFilename(statement.generatedAt));
      }
      return statement;
    },
    onSuccess: (statement) => {
      toast.success(
        statement.deliveryMethod === "email" ? "Statement emailed." : "Statement downloaded.",
      );
      void qc.invalidateQueries({ queryKey: statementKeys.patient(patientId) });
      void qc.invalidateQueries({ queryKey: AGING_PREFIX });
    },
    onError: (err) => {
      toast.error(apiErrorMessage(err));
    },
  });
}
```

- [ ] **Step 8: Run to verify pass, then lint and type-check**

```bash
pnpm --filter @dental/web test -- __tests__/lib/api/statements.test.ts && pnpm lint && pnpm type-check
```

Expected: 7 tests pass; lint and type-check clean.

- [ ] **Step 9: Commit**

```bash
git add apps/web/lib/api-client.ts apps/web/__tests__/lib/api-client.test.ts apps/web/lib/api/statements.ts apps/web/__tests__/lib/api/statements.test.ts
git commit -m "feat(web): statements API client + blob download helper"
```

---

## Task 14: Patient aging page + billing tile

**Files:**
- Create: `apps/web/app/(app)/billing/patient-aging/page.tsx`
- Modify: `apps/web/app/(app)/billing/page.tsx`

- [ ] **Step 1: Write the page**

Create `apps/web/app/(app)/billing/patient-aging/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useState } from "react";

import { PageHeader } from "@/components/layout/PageHeader";
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { centsToUsd } from "@/lib/api/reports";
import {
  DEFAULT_MIN_BALANCE_CENTS,
  lastStatementLabel,
  usePatientAgingWorklist,
  useSendStatement,
  type AgingSortBy,
  type PatientAgingRow,
} from "@/lib/api/statements";

const SORT_OPTIONS: { value: AgingSortBy; label: string }[] = [
  { value: "balance", label: "Total balance" },
  { value: "oldest_charge", label: "Oldest charge" },
  { value: "last_statement", label: "Last statement" },
];

const ACTION_CLASS = "text-sm text-primary underline disabled:opacity-50 disabled:no-underline";

function AgingRowActions({ row }: { row: PatientAgingRow }) {
  const send = useSendStatement(row.patientId);
  const emailTitle = row.email ? `Email to ${row.email}` : "Patient has no email on file";
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        className={ACTION_CLASS}
        disabled={!row.email || send.isPending}
        title={emailTitle}
        onClick={() => send.mutate("email")}
      >
        {send.isPending && send.variables === "email" ? "Sending…" : "Send email"}
      </button>
      <button
        type="button"
        className={ACTION_CLASS}
        disabled={send.isPending}
        title="Download PDF for mailing"
        onClick={() => send.mutate("download")}
      >
        {send.isPending && send.variables === "download" ? "Preparing…" : "Download PDF"}
      </button>
    </div>
  );
}

function LoadingSpinner() {
  return (
    <div className="flex justify-center py-16">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-border py-16 text-center text-sm text-muted-foreground">
      {message}
    </div>
  );
}

export default function PatientAgingPage() {
  const [sortBy, setSortBy] = useState<AgingSortBy>("balance");
  const [showAll, setShowAll] = useState(false);
  const minBalanceCents = showAll ? 1 : DEFAULT_MIN_BALANCE_CENTS;
  const { data, isLoading, isError } = usePatientAgingWorklist({ sortBy, minBalanceCents });
  const rows = data ?? [];

  const totals = rows.reduce(
    (acc, r) => ({
      b0_30: acc.b0_30 + r.buckets.b0_30,
      b31_60: acc.b31_60 + r.buckets.b31_60,
      b61_90: acc.b61_90 + r.buckets.b61_90,
      b90_plus: acc.b90_plus + r.buckets.b90_plus,
      balance: acc.balance + r.balanceCents,
    }),
    { b0_30: 0, b31_60: 0, b61_90: 0, b90_plus: 0, balance: 0 },
  );

  return (
    <div className="flex flex-col gap-6 p-6">
      <Link href="/billing" className="text-sm text-muted-foreground hover:text-foreground">
        ← Billing
      </Link>
      <PageHeader
        title="Patient A/R"
        description="Patients with an outstanding balance, aged by charge date"
        actions={
          <>
            <label className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Sort</span>
              <select
                className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as AgingSortBy)}
              >
                {SORT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={showAll}
                onChange={(e) => setShowAll(e.target.checked)}
              />
              <span>Show balances under {centsToUsd(DEFAULT_MIN_BALANCE_CENTS)}</span>
            </label>
          </>
        }
      />

      {isLoading && <LoadingSpinner />}
      {!isLoading && isError && <EmptyState message="Could not load patient A/R." />}
      {!isLoading && !isError && rows.length === 0 && (
        <EmptyState message="No patients with an outstanding balance." />
      )}

      {!isLoading && !isError && rows.length > 0 && (
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Patient</TableHead>
                <TableHead className="text-right">Current</TableHead>
                <TableHead className="text-right">31–60</TableHead>
                <TableHead className="text-right">61–90</TableHead>
                <TableHead className="text-right">90+</TableHead>
                <TableHead className="text-right">Credits</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead>Last statement</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.patientId}>
                  <TableCell>
                    <Link href={`/patients/${row.patientId}`} className="font-medium hover:underline">
                      {row.patientName}
                    </Link>
                    {!row.email && (
                      <span className="ml-2 text-xs text-muted-foreground">no email</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{centsToUsd(row.buckets.b0_30)}</TableCell>
                  <TableCell className="text-right tabular-nums">{centsToUsd(row.buckets.b31_60)}</TableCell>
                  <TableCell className="text-right tabular-nums">{centsToUsd(row.buckets.b61_90)}</TableCell>
                  <TableCell className="text-right tabular-nums">{centsToUsd(row.buckets.b90_plus)}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {centsToUsd(row.creditsCents)}
                  </TableCell>
                  <TableCell className="text-right font-semibold tabular-nums">
                    {centsToUsd(row.balanceCents)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {lastStatementLabel(row.lastStatementAt)}
                    {row.lastStatementMethod && (
                      <span className="ml-1 text-xs">
                        ({row.lastStatementMethod === "email" ? "email" : "download"})
                      </span>
                    )}
                  </TableCell>
                  <TableCell>
                    <AgingRowActions row={row} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter>
              <TableRow>
                <TableCell>{rows.length} patients</TableCell>
                <TableCell className="text-right tabular-nums">{centsToUsd(totals.b0_30)}</TableCell>
                <TableCell className="text-right tabular-nums">{centsToUsd(totals.b31_60)}</TableCell>
                <TableCell className="text-right tabular-nums">{centsToUsd(totals.b61_90)}</TableCell>
                <TableCell className="text-right tabular-nums">{centsToUsd(totals.b90_plus)}</TableCell>
                <TableCell />
                <TableCell className="text-right tabular-nums">{centsToUsd(totals.balance)}</TableCell>
                <TableCell colSpan={2} />
              </TableRow>
            </TableFooter>
          </Table>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Wire the billing tile**

In `apps/web/app/(app)/billing/page.tsx`, change the Patient A/R card from:

```tsx
          <SummaryCard
            title="Patient A/R"
            value={centsToUsd(summary.patientArTotalCents)}
            subtitle="Statements coming soon"
            href="/billing/claims"
          />
```

to:

```tsx
          <SummaryCard
            title="Patient A/R"
            value={centsToUsd(summary.patientArTotalCents)}
            subtitle="Outstanding patient balances"
            href="/billing/patient-aging"
          />
```

- [ ] **Step 3: Lint and type-check**

```bash
pnpm lint && pnpm type-check
```

Expected: clean.

- [ ] **Step 4: Click through locally**

With the API and web dev servers running and a practice that has ledger charges, open `/billing`, click the Patient A/R tile, confirm the table renders, sort and "show all" refetch, "Download PDF" saves a file named `statement-<date>.pdf`, and "Send email" on a patient with an email shows the success toast.

- [ ] **Step 5: Commit**

```bash
git add "apps/web/app/(app)/billing/patient-aging/page.tsx" "apps/web/app/(app)/billing/page.tsx"
git commit -m "feat(web): patient aging worklist page + billing tile"
```

---

## Task 15: Ledger tab statement actions + history

**Files:**
- Modify: `apps/web/components/patients/LedgerTab.tsx`

- [ ] **Step 1: Add imports**

In `apps/web/components/patients/LedgerTab.tsx`, add after the existing `@/lib/api/ledger` import block:

```ts
import { usePatient } from "@/lib/api/patients";
import {
  fetchStatementPreview,
  lastStatementLabel,
  openBlob,
  usePatientStatements,
  useSendStatement,
} from "@/lib/api/statements";
import { toast } from "sonner";
```

- [ ] **Step 2: Add the actions and history components**

Insert above `function BalanceBadge`:

```tsx
const STATEMENT_BUTTON_CLASS =
  "rounded-md border border-input px-3 py-1.5 text-sm hover:bg-accent disabled:opacity-50 disabled:pointer-events-none";

function StatementActions({
  patientId,
  balanceCents,
  email,
}: {
  patientId: string;
  balanceCents: number;
  email: string | null | undefined;
}) {
  const send = useSendStatement(patientId);
  const [previewing, setPreviewing] = useState(false);
  const hasBalance = balanceCents > 0;
  const balanceTitle = hasBalance ? undefined : "No outstanding balance";

  const preview = async () => {
    setPreviewing(true);
    try {
      openBlob(await fetchStatementPreview(patientId));
    } catch {
      toast.error("Could not generate the statement preview.");
    } finally {
      setPreviewing(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        className={STATEMENT_BUTTON_CLASS}
        disabled={!hasBalance || previewing}
        title={balanceTitle ?? "Open a PDF preview in a new tab"}
        onClick={() => void preview()}
      >
        {previewing ? "Generating…" : "Preview statement"}
      </button>
      <button
        type="button"
        className={STATEMENT_BUTTON_CLASS}
        disabled={!hasBalance || !email || send.isPending}
        title={balanceTitle ?? (email ? `Email statement to ${email}` : "Patient has no email on file")}
        onClick={() => send.mutate("email")}
      >
        {send.isPending && send.variables === "email" ? "Sending…" : "Email statement"}
      </button>
      <button
        type="button"
        className={STATEMENT_BUTTON_CLASS}
        disabled={!hasBalance || send.isPending}
        title={balanceTitle ?? "Download PDF for mailing"}
        onClick={() => send.mutate("download")}
      >
        {send.isPending && send.variables === "download" ? "Preparing…" : "Download PDF"}
      </button>
    </div>
  );
}

function StatementHistory({ patientId }: { patientId: string }) {
  const [open, setOpen] = useState(false);
  const { data, isLoading } = usePatientStatements(patientId);
  const statements = data ?? [];

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <button
        type="button"
        className="flex w-full items-center justify-between text-left"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <h3 className="text-sm font-semibold">
          Statement history
          {!isLoading && (
            <span className="ml-2 font-normal text-muted-foreground">({statements.length})</span>
          )}
        </h3>
        <span className="text-xs text-muted-foreground">{open ? "Hide" : "Show"}</span>
      </button>

      {open && statements.length === 0 && !isLoading && (
        <p className="text-sm text-muted-foreground">No statements have been sent.</p>
      )}

      {open && statements.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
                <th className="px-3 py-2">Date</th>
                <th className="px-3 py-2">Delivery</th>
                <th className="px-3 py-2 text-right">Balance</th>
                <th className="px-3 py-2">Sent by</th>
              </tr>
            </thead>
            <tbody>
              {statements.map((s) => (
                <tr key={s.id} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 text-muted-foreground">
                    {s.generatedAt.slice(0, 10)}
                    <span className="ml-2 text-xs">({lastStatementLabel(s.generatedAt)})</span>
                  </td>
                  <td className="px-3 py-2">{s.deliveryMethod === "email" ? "Email" : "Downloaded"}</td>
                  <td className="px-3 py-2 text-right">{centsToUsd(s.balanceCents)}</td>
                  <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                    {s.generatedBy}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Wire them into `LedgerTab`**

In `export function LedgerTab`, add after the `usePatientLedger` line:

```tsx
  const { data: patient } = usePatient(patientId);
```

Replace the header block:

```tsx
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">Ledger</h2>
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Balance</span>
            <BalanceBadge balanceCents={balanceCents} />
          </div>
        </div>
```

with:

```tsx
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold">Ledger</h2>
          <div className="flex flex-wrap items-center gap-3">
            <StatementActions
              patientId={patientId}
              balanceCents={balanceCents}
              email={patient?.email}
            />
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Balance</span>
              <BalanceBadge balanceCents={balanceCents} />
            </div>
          </div>
        </div>
```

Then, after the ledger card's closing `</div>` (immediately before the "Record payment" card), insert:

```tsx
      <StatementHistory patientId={patientId} />
```

- [ ] **Step 4: Lint and type-check**

```bash
pnpm lint && pnpm type-check
```

Expected: clean. (`centsToUsd` and `useState` are already imported in this file.)

- [ ] **Step 5: Click through locally**

Open a patient with a balance → Ledger tab: Preview opens a PDF in a new tab; Email statement is disabled with a tooltip when the patient has no email; Download PDF saves a file; the Statement history section lists the new rows after each action. Open a patient with a zero balance: all three buttons disabled with the "No outstanding balance" title.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/patients/LedgerTab.tsx
git commit -m "feat(web): statement actions + history on the patient Ledger tab"
```

---

## Task 16: Documentation, full verification, PR

**Files:**
- Modify: `longterm_build_plan.md`

- [ ] **Step 1: Run the complete verification sweep**

From `apps/api`:

```bash
uv run ruff check . && uv run mypy app/ && uv run pytest -q && uv run pytest -m integration -q
```

From the repo root:

```bash
pnpm lint && pnpm type-check && pnpm --filter @dental/web test
```

Migration round-trip, from `apps/api`:

```bash
uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head
```

Every command must pass. If one fails, fix the code. Do not weaken an assertion or skip a check.

- [ ] **Step 2: Update the roadmap**

In `longterm_build_plan.md`, under the Module 8 bullet, add a third slice line after the "8b second slice" line:

```markdown
  - **8b third slice — Patient Aging + Statements — ✅ BUILT.** Migration 0039 (`patient_statements`: append-only delivery record + point-in-time aging snapshot keyed like ARBuckets). `GET /reports/patient-aging` (gated on `billing_ledger`) lists every live patient owing ≥ $5 (default; `min_balance_cents` query param), charges bucketed 0–30 / 31–60 / 61–90 / 90+ by `posted_at`, payments/adjustments as one credits total (no FIFO attribution), reversal pairs excluded; sorts by balance / oldest charge / last statement. Statements are always manual, never batch: `POST /patients/{id}/statements` (`email` → Jinja2 → WeasyPrint PDF attached via SES `SendRawEmail`; `download` → records only) returns JSON; bytes come from `GET …/statements/{id}/pdf` and `GET …/statements/preview` because IdempotencyMiddleware text-decodes mutation bodies. `email_opt_out` is intentionally ignored (transactional). New `/billing/patient-aging` page (sort, show-all, per-row Send email / Download PDF, totals footer) + Preview / Email / Download buttons and collapsible statement history on the patient Ledger tab. Runtime image now installs Pango/HarfBuzz for WeasyPrint. Spec: `specs/2026-08-05-patient-aging-statements-design.md`; plan: `plans/2026-09-08-patient-aging-statements.md`. **8b+ remainder:** overpayment/refund handling, guarantor/family billing, QuickBooks export, Stripe card processing, batch statement sends, payment URL on statements (needs patient portal).
```

Also edit the end of the "8b second slice" line: change `**8b+ remainder:** patient aging + statements, overpayment/refund handling, QuickBooks export, Stripe card processing.` to `**8b+ remainder:** see third slice below.`

In the "Needs UI / Manual Testing" section, add a subsection before "### Claim recovery & appeals (PR #62)":

```markdown
### Patient Aging + Statements

- **Aging page:** `/billing` → Patient A/R tile → table renders; sort dropdown and "show balances under $5.00" refetch; totals footer sums the visible rows
- **Download PDF:** saves `statement-<date>.pdf`; open it and confirm letterhead, patient address block, aging summary, itemized table, and running balance match the Ledger tab
- **Send email:** requires SES configured (`SES_FROM_ADDRESS`) — verify at staging; locally the send is logged and the statement is still recorded with `delivered_at` set
- **Ledger tab:** Preview opens a PDF in a new tab; buttons disabled with tooltips for no balance / no email; statement history expands and lists each action
- **Write-off then late ERA payment (credit balance):** patient disappears from the aging worklist (balance ≤ 0); refund workflow remains unbuilt (8b+)
```

- [ ] **Step 3: Commit**

```bash
git add longterm_build_plan.md
git commit -m "docs: mark 8b patient aging + statements BUILT"
```

- [ ] **Step 4: Open the PR**

```bash
git push -u origin HEAD
gh pr create --title "Module 8b — Patient Aging + Statements" --body "$(cat <<'EOF'
## Summary
- Patient A/R aging worklist: `GET /reports/patient-aging` (gated on `billing_ledger`), charges bucketed 0–30/31–60/61–90/90+, credits as one total, reversal pairs excluded, three sort modes
- PDF billing statements: Jinja2 template → WeasyPrint, emailed via SES `SendRawEmail` with the PDF attached or downloaded for mailing; every delivery recorded in the new append-only `patient_statements` table (migration 0039)
- New `/billing/patient-aging` page; Preview / Email / Download buttons + statement history on the patient Ledger tab

## Design notes
- Mutations return JSON only; PDF bytes are served from GET endpoints because `IdempotencyMiddleware` text-decodes mutation bodies
- `email_opt_out` is deliberately not checked: a statement is transactional, unlike reminders
- WeasyPrint is imported lazily; the runtime image installs Pango/HarfBuzz; tests mock the render except one `importorskip` test

## Test plan
- [ ] `uv run ruff check .` · `uv run mypy app/` clean
- [ ] Unit tests (aging bucketer, HTML renderer, SES attachment, reports + statements routers)
- [ ] Integration tests (aging worklist, statement service, HTTP end-to-end, tenant scoping, feature flag)
- [ ] Migration 0039 up / down / up
- [ ] `pnpm lint` · `pnpm type-check` · web unit tests
- [ ] Docker image builds and `import weasyprint` succeeds inside it
- [ ] Live SES statement email — verify at staging

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Tick each box in the PR body only after the corresponding command has actually been run in Step 1.
