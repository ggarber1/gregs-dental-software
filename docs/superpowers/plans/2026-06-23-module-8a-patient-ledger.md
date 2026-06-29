# Module 8a — Patient Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a per-patient financial ledger — immutable charge / payment / adjustment entries with a running balance — that auto-posts charges at appointment checkout and insurance payments from the ERA, plus front-desk patient-payment and manual-adjustment entry.

**Architecture:** One append-only table `ledger_entries` (PHIMixin, integer signed cents). A `ledger` service splits into `posting.py` (charge reconciliation, insurance posting, patient payment, manual adjustment, reversal) and `balance.py` (balance + running-balance read). A feature-gated `ledger` router exposes read + payment + adjustment + reverse. Two integration hooks: appointment `→ completed` (and post-completion procedure edits) reconcile charges; the ERA poll posts insurance entries when a remittance matches a claim. Corrections are reversing entries, never UPDATE/DELETE.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic (Postgres), Pydantic schemas generated from Zod (`packages/shared-types` → `app/schemas/generated.py` via `pnpm generate`), pytest (`-m integration`, Postgres-backed), Next.js + React Query frontend.

**Spec:** `docs/superpowers/specs/2026-06-23-module-8a-patient-ledger-design.md`

---

## Testing notes (read first)

- Ledger posting/balance/router tests are **DB-backed → integration tests** (`pytestmark = pytest.mark.integration`). They need Postgres at `localhost:5432` (`dental/dental`); the suite drops/recreates `dental_test` and runs Alembic. Bring the DB up with `docker compose up -d postgres` before running.
- Per `CLAUDE.md`, **integration tests should be run with Greg's go-ahead** — confirm the DB is up / it's OK to run before executing the `pytest -m integration` steps.
- One pure helper (`annotate_running_balance`) has a **non-integration** unit test you can and should run yourself.
- Lint must match CI: run `ruff check .` and `mypy app` from `apps/api` (the whole tree, not just `app tests`).

---

## File structure

**Create:**
- `apps/api/app/models/ledger_entry.py` — `LedgerEntry` model
- `apps/api/alembic/versions/0034_ledger_entries.py` — migration
- `apps/api/app/services/ledger/__init__.py`
- `apps/api/app/services/ledger/posting.py` — posting + reversal functions
- `apps/api/app/services/ledger/balance.py` — balance + running-balance read
- `apps/api/app/routers/ledger.py` — endpoints
- `packages/shared-types/src/schemas/ledger.ts` — Zod schemas
- `apps/api/tests/services/test_ledger_balance.py` — pure unit test
- `apps/api/tests/integration/test_ledger_service.py` — posting/balance integration
- `apps/api/tests/integration/test_ledger_endpoints.py` — router integration
- `apps/web/lib/api/ledger.ts` — React Query hooks
- `apps/web/components/patients/LedgerTab.tsx` — ledger UI

**Modify:**
- `apps/api/app/models/__init__.py` — register `LedgerEntry`
- `apps/api/app/main.py` — `include_router(ledger.router)`
- `apps/api/app/routers/appointments.py` — hook charge reconcile on `→ completed`
- `apps/api/app/services/era/service.py` — hook insurance posting after claim match
- `apps/api/tests/integration/conftest.py` — add `ledger_entries` to truncate list
- `packages/shared-types/src/index.ts` — export `./schemas/ledger.js`
- `apps/web/app/(app)/patients/[patientId]/page.tsx` — add `"ledger"` tab
- `longterm_build_plan.md` + `docs/superpowers/specs/phase3-build-order.md` — mark 8a built

---

## Task 1: `LedgerEntry` model + migration

**Files:**
- Create: `apps/api/app/models/ledger_entry.py`
- Modify: `apps/api/app/models/__init__.py`
- Create: `apps/api/alembic/versions/0034_ledger_entries.py`
- Modify: `apps/api/tests/integration/conftest.py`
- Test: `apps/api/tests/integration/test_ledger_service.py` (smoke insert)

- [ ] **Step 1: Write the model**

`apps/api/app/models/ledger_entry.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin

ENTRY_TYPES = ("charge", "insurance_payment", "patient_payment", "adjustment")
PAYMENT_METHODS = ("cash", "check", "card", "external_terminal", "other")


class LedgerEntry(Base, PHIMixin):
    """One immutable financial event on a patient's ledger.

    Money is integer cents, **signed**: charge is positive (patient owes more);
    payments and adjustments are negative (patient owes less). Corrections are made
    by posting a reversing entry (`reverses_entry_id` set, sign flipped) — rows are
    never UPDATEd or hard-deleted. Running balance = SUM(amount_cents) per patient.
    """

    __tablename__ = "ledger_entries"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Reserved for future family/guarantor billing (Module 8b); unused in 8a.
    guarantor_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    appointment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    appointment_procedure_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    claim_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    remittance_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reverses_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    payment_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    memo: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_by: Mapped[str] = mapped_column(String(255), nullable=False, server_default="system")
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('charge', 'insurance_payment', 'patient_payment', 'adjustment')",
            name="ck_ledger_entries_entry_type",
        ),
        CheckConstraint(
            "payment_method IS NULL OR ("
            "entry_type = 'patient_payment' AND payment_method IN "
            "('cash', 'check', 'card', 'external_terminal', 'other'))",
            name="ck_ledger_entries_payment_method",
        ),
        Index("ix_ledger_entries_patient_posted", "patient_id", "posted_at"),
        Index("ix_ledger_entries_practice_deleted", "practice_id", "deleted_at"),
        Index(
            "ix_ledger_entries_proc_charge",
            "appointment_procedure_id",
            postgresql_where="entry_type = 'charge'",
        ),
        Index("ix_ledger_entries_appointment", "appointment_id"),
    )
```

- [ ] **Step 2: Register the model for Alembic metadata**

In `apps/api/app/models/__init__.py`, add (keep alphabetical-ish, after `intake_form`):

```python
from app.models.ledger_entry import LedgerEntry as LedgerEntry
```

- [ ] **Step 3: Write the migration**

`apps/api/alembic/versions/0034_ledger_entries.py`:

```python
"""Patient ledger (Module 8a) — append-only ledger_entries

Revision ID: 0034
Revises: 0033
Create Date: 2026-06-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0034"
down_revision: str | Sequence[str] | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("guarantor_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entry_type", sa.String(20), nullable=False),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("appointment_procedure_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("remittance_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reverses_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payment_method", sa.String(20), nullable=True),
        sa.Column("memo", sa.Text, nullable=True),
        sa.Column("posted_by", sa.String(255), nullable=False, server_default="system"),
        sa.Column(
            "posted_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_by", sa.String(255), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "entry_type IN ('charge', 'insurance_payment', 'patient_payment', 'adjustment')",
            name="ck_ledger_entries_entry_type",
        ),
        sa.CheckConstraint(
            "payment_method IS NULL OR ("
            "entry_type = 'patient_payment' AND payment_method IN "
            "('cash', 'check', 'card', 'external_terminal', 'other'))",
            name="ck_ledger_entries_payment_method",
        ),
    )
    op.create_index(
        "ix_ledger_entries_patient_posted", "ledger_entries", ["patient_id", "posted_at"]
    )
    op.create_index(
        "ix_ledger_entries_practice_deleted", "ledger_entries", ["practice_id", "deleted_at"]
    )
    op.create_index(
        "ix_ledger_entries_proc_charge",
        "ledger_entries",
        ["appointment_procedure_id"],
        postgresql_where=sa.text("entry_type = 'charge'"),
    )
    op.create_index("ix_ledger_entries_appointment", "ledger_entries", ["appointment_id"])


def downgrade() -> None:
    op.drop_table("ledger_entries")
```

- [ ] **Step 4: Add `ledger_entries` to the integration truncate list**

In `apps/api/tests/integration/conftest.py`, add `"ledger_entries",` as the FIRST entry of `_TRUNCATE_TABLES` (it has no dependents; truncate it first):

```python
_TRUNCATE_TABLES = (
    "ledger_entries",
    "unmatched_era_payments",
    ...
```

- [ ] **Step 5: Write a smoke test that the table accepts an insert**

`apps/api/tests/integration/test_ledger_service.py` (start the file):

```python
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_ledger_entry_inserts(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    db_session.add(
        LedgerEntry(
            id=uuid.uuid4(),
            practice_id=practice_id,
            patient_id=patient_id,
            entry_type="charge",
            amount_cents=25000,
        )
    )
    await db_session.commit()
    row = await db_session.scalar(
        select(LedgerEntry).where(LedgerEntry.patient_id == patient_id)
    )
    assert row is not None
    assert row.amount_cents == 25000
    assert row.posted_by == "system"
```

- [ ] **Step 6: Run migration + smoke test** (integration — confirm DB is up / OK to run)

Run: `cd apps/api && pytest tests/integration/test_ledger_service.py -v`
Expected: PASS (the session-scoped fixture runs Alembic to head, creating `ledger_entries`).

- [ ] **Step 7: Lint**

Run: `cd apps/api && ruff check . && mypy app`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/models/ledger_entry.py apps/api/app/models/__init__.py \
  apps/api/alembic/versions/0034_ledger_entries.py \
  apps/api/tests/integration/conftest.py apps/api/tests/integration/test_ledger_service.py
git commit -m "feat(8a): ledger_entries model + migration"
```

---

## Task 2: Zod schemas → generated Pydantic

**Files:**
- Create: `packages/shared-types/src/schemas/ledger.ts`
- Modify: `packages/shared-types/src/index.ts`
- Generated (do NOT hand-edit): `apps/api/app/schemas/generated.py`

- [ ] **Step 1: Write the Zod schemas**

`packages/shared-types/src/schemas/ledger.ts`:

```typescript
import { z } from "zod";
import { UuidSchema } from "./common.js";

export const LedgerEntryTypeSchema = z.enum([
  "charge",
  "insurance_payment",
  "patient_payment",
  "adjustment",
]);
export type LedgerEntryType = z.infer<typeof LedgerEntryTypeSchema>;

export const LedgerPaymentMethodSchema = z.enum([
  "cash",
  "check",
  "card",
  "external_terminal",
  "other",
]);
export type LedgerPaymentMethod = z.infer<typeof LedgerPaymentMethodSchema>;

export const LedgerEntrySchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  patientId: UuidSchema,
  entryType: LedgerEntryTypeSchema,
  amountCents: z.number().int(),
  runningBalanceCents: z.number().int(),
  appointmentId: UuidSchema.nullable(),
  appointmentProcedureId: UuidSchema.nullable(),
  claimId: UuidSchema.nullable(),
  remittanceId: UuidSchema.nullable(),
  reversesEntryId: UuidSchema.nullable(),
  paymentMethod: LedgerPaymentMethodSchema.nullable(),
  memo: z.string().nullable(),
  postedBy: z.string(),
  postedAt: z.string().datetime(),
});
export type LedgerEntry = z.infer<typeof LedgerEntrySchema>;

export const PatientLedgerSchema = z.object({
  patientId: UuidSchema,
  balanceCents: z.number().int(),
  entries: z.array(LedgerEntrySchema),
});
export type PatientLedger = z.infer<typeof PatientLedgerSchema>;

export const RecordPaymentRequestSchema = z.object({
  amountCents: z.number().int().positive(),
  paymentMethod: LedgerPaymentMethodSchema,
  memo: z.string().nullable().optional(),
});
export type RecordPaymentRequest = z.infer<typeof RecordPaymentRequestSchema>;

export const AddAdjustmentRequestSchema = z.object({
  amountCents: z.number().int(),
  memo: z.string().min(1),
});
export type AddAdjustmentRequest = z.infer<typeof AddAdjustmentRequestSchema>;

export const ReverseEntryRequestSchema = z.object({
  memo: z.string().nullable().optional(),
});
export type ReverseEntryRequest = z.infer<typeof ReverseEntryRequestSchema>;
```

- [ ] **Step 2: Export from the package index**

In `packages/shared-types/src/index.ts`, append:

```typescript
export * from "./schemas/ledger.js";
```

- [ ] **Step 3: Regenerate Pydantic schemas**

Run: `pnpm generate` (from repo root).
Expected: `apps/api/app/schemas/generated.py` now contains `LedgerEntry`, `PatientLedger`, `RecordPaymentRequest`, `AddAdjustmentRequest`, `ReverseEntryRequest`. Verify:

Run: `cd apps/api && python -c "from app.schemas.generated import PatientLedger, RecordPaymentRequest, AddAdjustmentRequest, ReverseEntryRequest, LedgerEntry; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Lint + commit**

Run: `cd apps/api && ruff check . && mypy app`

```bash
git add packages/shared-types/src/schemas/ledger.ts packages/shared-types/src/index.ts \
  apps/api/app/schemas/generated.py
git commit -m "feat(8a): ledger Zod schemas + generated types"
```

---

## Task 3: `balance.py` — running balance + ledger read

**Files:**
- Create: `apps/api/app/services/ledger/__init__.py` (empty)
- Create: `apps/api/app/services/ledger/balance.py`
- Test: `apps/api/tests/services/test_ledger_balance.py` (pure unit — run yourself)
- Test: add to `apps/api/tests/integration/test_ledger_service.py`

- [ ] **Step 1: Write the pure-unit failing test**

`apps/api/tests/services/test_ledger_balance.py`:

```python
import uuid
from types import SimpleNamespace

from app.services.ledger.balance import annotate_running_balance


def _entry(amount: int):
    return SimpleNamespace(id=uuid.uuid4(), amount_cents=amount)


def test_running_balance_accumulates_in_order():
    entries = [_entry(25000), _entry(-20000), _entry(-3000), _entry(-2000)]
    annotated = annotate_running_balance(entries)
    assert [rb for _, rb in annotated] == [25000, 5000, 2000, 0]


def test_running_balance_allows_credit():
    entries = [_entry(5000), _entry(-8000)]
    annotated = annotate_running_balance(entries)
    assert annotated[-1][1] == -3000  # patient overpaid -> credit balance
```

- [ ] **Step 2: Run it — verify it fails**

Run: `cd apps/api && pytest tests/services/test_ledger_balance.py -v`
Expected: FAIL (`ModuleNotFoundError` / `annotate_running_balance` undefined).

- [ ] **Step 3: Implement `balance.py`**

`apps/api/app/services/ledger/__init__.py`: empty file.

`apps/api/app/services/ledger/balance.py`:

```python
from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry


def annotate_running_balance(
    entries: Sequence[LedgerEntry],
) -> list[tuple[LedgerEntry, int]]:
    """Pair each entry with the running balance after it. Entries must already be
    ordered oldest-first. Pure — no DB access."""
    running = 0
    out: list[tuple[LedgerEntry, int]] = []
    for entry in entries:
        running += entry.amount_cents
        out.append((entry, running))
    return out


async def _live_entries(
    session: AsyncSession, practice_id: uuid.UUID, patient_id: uuid.UUID
) -> list[LedgerEntry]:
    rows = (
        await session.scalars(
            select(LedgerEntry)
            .where(
                LedgerEntry.practice_id == practice_id,
                LedgerEntry.patient_id == patient_id,
                LedgerEntry.deleted_at.is_(None),
            )
            .order_by(LedgerEntry.posted_at, LedgerEntry.id)
        )
    ).all()
    return list(rows)


async def get_patient_balance(
    session: AsyncSession, practice_id: uuid.UUID, patient_id: uuid.UUID
) -> int:
    """SUM(amount_cents). Positive = patient owes; negative = credit balance."""
    total = await session.scalar(
        select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(
            LedgerEntry.practice_id == practice_id,
            LedgerEntry.patient_id == patient_id,
            LedgerEntry.deleted_at.is_(None),
        )
    )
    return int(total or 0)


async def get_ledger(
    session: AsyncSession, practice_id: uuid.UUID, patient_id: uuid.UUID
) -> tuple[list[tuple[LedgerEntry, int]], int]:
    """Return (entries-with-running-balance oldest-first, current balance)."""
    entries = await _live_entries(session, practice_id, patient_id)
    annotated = annotate_running_balance(entries)
    balance = annotated[-1][1] if annotated else 0
    return annotated, balance
```

- [ ] **Step 4: Run the unit test — verify pass**

Run: `cd apps/api && pytest tests/services/test_ledger_balance.py -v`
Expected: PASS.

- [ ] **Step 5: Add an integration test for `get_patient_balance` / `get_ledger`**

Append to `apps/api/tests/integration/test_ledger_service.py`:

```python
from app.services.ledger.balance import get_ledger, get_patient_balance


async def _add(session, practice_id, patient_id, entry_type, amount, **kw):
    from app.models.ledger_entry import LedgerEntry

    e = LedgerEntry(
        id=uuid.uuid4(),
        practice_id=practice_id,
        patient_id=patient_id,
        entry_type=entry_type,
        amount_cents=amount,
        **kw,
    )
    session.add(e)
    await session.commit()
    return e


@pytest.mark.asyncio
async def test_balance_and_ledger_read(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    await _add(db_session, practice_id, patient_id, "charge", 25000)
    await _add(db_session, practice_id, patient_id, "insurance_payment", -20000)
    await _add(db_session, practice_id, patient_id, "patient_payment", -5000,
               payment_method="cash")

    assert await get_patient_balance(db_session, practice_id, patient_id) == 0
    entries, balance = await get_ledger(db_session, practice_id, patient_id)
    assert balance == 0
    assert len(entries) == 3
    assert entries[0][1] == 25000  # running balance after first charge
```

- [ ] **Step 6: Run integration test** (confirm DB up / OK to run)

Run: `cd apps/api && pytest tests/integration/test_ledger_service.py -v`
Expected: PASS.

- [ ] **Step 7: Lint + commit**

```bash
cd apps/api && ruff check . && mypy app
git add apps/api/app/services/ledger/ apps/api/tests/services/test_ledger_balance.py \
  apps/api/tests/integration/test_ledger_service.py
git commit -m "feat(8a): ledger balance + running-balance read"
```

---

## Task 4: `posting.py` — patient payment, manual adjustment, reversal

**Files:**
- Create: `apps/api/app/services/ledger/posting.py`
- Test: add to `apps/api/tests/integration/test_ledger_service.py`

- [ ] **Step 1: Write failing integration tests**

Append to `apps/api/tests/integration/test_ledger_service.py`:

```python
from app.services.ledger.posting import (
    add_manual_adjustment,
    record_patient_payment,
    reverse_entry,
)


@pytest.mark.asyncio
async def test_record_patient_payment_posts_negative(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    entry = await record_patient_payment(
        db_session, practice_id, patient_id,
        amount_cents=5000, payment_method="card", memo="copay", posted_by="user-1",
    )
    assert entry.entry_type == "patient_payment"
    assert entry.amount_cents == -5000
    assert entry.payment_method == "card"
    assert await get_patient_balance(db_session, practice_id, patient_id) == -5000


@pytest.mark.asyncio
async def test_record_patient_payment_rejects_non_positive(db_session: AsyncSession):
    with pytest.raises(ValueError):
        await record_patient_payment(
            db_session, uuid.uuid4(), uuid.uuid4(),
            amount_cents=0, payment_method="cash", memo=None, posted_by="u",
        )


@pytest.mark.asyncio
async def test_add_manual_adjustment_requires_memo(db_session: AsyncSession):
    with pytest.raises(ValueError):
        await add_manual_adjustment(
            db_session, uuid.uuid4(), uuid.uuid4(),
            amount_cents=-1000, memo="", posted_by="u",
        )


@pytest.mark.asyncio
async def test_add_manual_adjustment_posts(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    await _add(db_session, practice_id, patient_id, "charge", 10000)
    entry = await add_manual_adjustment(
        db_session, practice_id, patient_id,
        amount_cents=-1500, memo="senior discount", posted_by="user-1",
    )
    assert entry.entry_type == "adjustment"
    assert entry.amount_cents == -1500
    assert await get_patient_balance(db_session, practice_id, patient_id) == 8500


@pytest.mark.asyncio
async def test_reverse_entry_mirrors_and_zeroes(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    pay = await record_patient_payment(
        db_session, practice_id, patient_id,
        amount_cents=5000, payment_method="cash", memo=None, posted_by="u",
    )
    rev = await reverse_entry(db_session, practice_id, pay.id, posted_by="u", memo="entered twice")
    assert rev is not None
    assert rev.amount_cents == 5000  # mirror of -5000
    assert rev.reverses_entry_id == pay.id
    assert await get_patient_balance(db_session, practice_id, patient_id) == 0


@pytest.mark.asyncio
async def test_reverse_entry_rejects_double_reverse(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    pay = await record_patient_payment(
        db_session, practice_id, patient_id,
        amount_cents=5000, payment_method="cash", memo=None, posted_by="u",
    )
    await reverse_entry(db_session, practice_id, pay.id, posted_by="u")
    # second reversal of the same entry is rejected
    assert await reverse_entry(db_session, practice_id, pay.id, posted_by="u") is None


@pytest.mark.asyncio
async def test_reverse_entry_other_practice_returns_none(db_session: AsyncSession):
    pay = await record_patient_payment(
        db_session, uuid.uuid4(), uuid.uuid4(),
        amount_cents=5000, payment_method="cash", memo=None, posted_by="u",
    )
    assert await reverse_entry(db_session, uuid.uuid4(), pay.id, posted_by="u") is None
```

- [ ] **Step 2: Run — verify fail**

Run: `cd apps/api && pytest tests/integration/test_ledger_service.py -v -k "payment or adjustment or reverse"`
Expected: FAIL (import error — functions undefined).

- [ ] **Step 3: Implement `posting.py` (this slice)**

`apps/api/app/services/ledger/posting.py`:

```python
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ledger_entry import LedgerEntry


async def record_patient_payment(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    *,
    amount_cents: int,
    payment_method: str,
    memo: str | None,
    posted_by: str,
) -> LedgerEntry:
    """Post a patient payment (stored as a negative entry). Amount must be > 0."""
    if amount_cents <= 0:
        raise ValueError("payment amount_cents must be positive")
    entry = LedgerEntry(
        id=uuid.uuid4(),
        practice_id=practice_id,
        patient_id=patient_id,
        entry_type="patient_payment",
        amount_cents=-amount_cents,
        payment_method=payment_method,
        memo=memo,
        posted_by=posted_by,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def add_manual_adjustment(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    *,
    amount_cents: int,
    memo: str,
    posted_by: str,
) -> LedgerEntry:
    """Post a manual adjustment. Sign is the caller's: negative = credit/write-off,
    positive = additional charge. `memo` (reason) is required."""
    if not memo or not memo.strip():
        raise ValueError("adjustment memo is required")
    if amount_cents == 0:
        raise ValueError("adjustment amount_cents must be non-zero")
    entry = LedgerEntry(
        id=uuid.uuid4(),
        practice_id=practice_id,
        patient_id=patient_id,
        entry_type="adjustment",
        amount_cents=amount_cents,
        memo=memo,
        posted_by=posted_by,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def _is_reversed(session: AsyncSession, entry_id: uuid.UUID) -> bool:
    found = await session.scalar(
        select(LedgerEntry.id).where(
            LedgerEntry.reverses_entry_id == entry_id,
            LedgerEntry.deleted_at.is_(None),
        )
    )
    return found is not None


async def reverse_entry(
    session: AsyncSession,
    practice_id: uuid.UUID,
    entry_id: uuid.UUID,
    *,
    posted_by: str,
    memo: str | None = None,
) -> LedgerEntry | None:
    """Post a mirror entry that cancels `entry_id`. Returns None if the entry is not
    found in this practice, is itself a reversal, or has already been reversed."""
    original = await session.scalar(
        select(LedgerEntry).where(
            LedgerEntry.id == entry_id,
            LedgerEntry.practice_id == practice_id,
            LedgerEntry.deleted_at.is_(None),
        )
    )
    if original is None or original.reverses_entry_id is not None:
        return None
    if await _is_reversed(session, entry_id):
        return None
    reversal = LedgerEntry(
        id=uuid.uuid4(),
        practice_id=original.practice_id,
        patient_id=original.patient_id,
        guarantor_account_id=original.guarantor_account_id,
        entry_type=original.entry_type,
        amount_cents=-original.amount_cents,
        appointment_id=original.appointment_id,
        appointment_procedure_id=original.appointment_procedure_id,
        claim_id=original.claim_id,
        remittance_id=original.remittance_id,
        reverses_entry_id=original.id,
        memo=memo or f"reversal of {original.id}",
        posted_by=posted_by,
    )
    session.add(reversal)
    await session.commit()
    await session.refresh(reversal)
    return reversal
```

- [ ] **Step 4: Run — verify pass**

Run: `cd apps/api && pytest tests/integration/test_ledger_service.py -v -k "payment or adjustment or reverse"`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
cd apps/api && ruff check . && mypy app
git add apps/api/app/services/ledger/posting.py apps/api/tests/integration/test_ledger_service.py
git commit -m "feat(8a): patient payment, manual adjustment, reversal posting"
```

---

## Task 5: `posting.py` — charge reconciliation from completed appointment

**Files:**
- Modify: `apps/api/app/services/ledger/posting.py`
- Test: add to `apps/api/tests/integration/test_ledger_service.py`

**Behavior:** Given a completed appointment, for each of its (non-deleted) procedures ensure exactly one *live* charge entry equal to `fee_cents`. A live charge = a `charge` entry for that `appointment_procedure_id` that has not been reversed. If a procedure's fee changed, reverse the stale charge and post a new one. If a procedure was deleted, reverse its charge. Idempotent: a second run with no changes posts nothing.

- [ ] **Step 1: Write failing integration tests**

Append to `apps/api/tests/integration/test_ledger_service.py`:

```python
from app.models.appointment_procedure import AppointmentProcedure
from app.services.ledger.posting import reconcile_charges_for_appointment


async def _seed_proc(session, practice_id, patient_id, appointment_id, fee, name="Exam"):
    proc = AppointmentProcedure(
        id=uuid.uuid4(),
        practice_id=practice_id,
        appointment_id=appointment_id,
        patient_id=patient_id,
        procedure_code="D0120",
        procedure_name=name,
        fee_cents=fee,
    )
    session.add(proc)
    await session.commit()
    return proc


@pytest.mark.asyncio
async def test_reconcile_posts_one_charge_per_procedure(db_session: AsyncSession):
    practice_id, patient_id, appt_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed_proc(db_session, practice_id, patient_id, appt_id, 12000)
    await _seed_proc(db_session, practice_id, patient_id, appt_id, 8000, name="X-ray")
    appt = SimpleNamespace(id=appt_id, practice_id=practice_id, patient_id=patient_id)

    await reconcile_charges_for_appointment(db_session, appt, user_sub="u")
    assert await get_patient_balance(db_session, practice_id, patient_id) == 20000


@pytest.mark.asyncio
async def test_reconcile_is_idempotent(db_session: AsyncSession):
    practice_id, patient_id, appt_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed_proc(db_session, practice_id, patient_id, appt_id, 12000)
    appt = SimpleNamespace(id=appt_id, practice_id=practice_id, patient_id=patient_id)

    await reconcile_charges_for_appointment(db_session, appt, user_sub="u")
    await reconcile_charges_for_appointment(db_session, appt, user_sub="u")  # no-op
    entries, balance = await get_ledger(db_session, practice_id, patient_id)
    assert balance == 12000
    assert len(entries) == 1  # not double-posted


@pytest.mark.asyncio
async def test_reconcile_reverses_and_reposts_on_fee_change(db_session: AsyncSession):
    practice_id, patient_id, appt_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    proc = await _seed_proc(db_session, practice_id, patient_id, appt_id, 12000)
    appt = SimpleNamespace(id=appt_id, practice_id=practice_id, patient_id=patient_id)
    await reconcile_charges_for_appointment(db_session, appt, user_sub="u")

    proc.fee_cents = 15000
    await db_session.commit()
    await reconcile_charges_for_appointment(db_session, appt, user_sub="u")

    entries, balance = await get_ledger(db_session, practice_id, patient_id)
    assert balance == 15000  # 12000 charge, -12000 reversal, 15000 new charge
    assert len(entries) == 3


@pytest.mark.asyncio
async def test_reconcile_reverses_when_procedure_deleted(db_session: AsyncSession):
    practice_id, patient_id, appt_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    proc = await _seed_proc(db_session, practice_id, patient_id, appt_id, 12000)
    appt = SimpleNamespace(id=appt_id, practice_id=practice_id, patient_id=patient_id)
    await reconcile_charges_for_appointment(db_session, appt, user_sub="u")

    from datetime import UTC, datetime
    proc.deleted_at = datetime.now(UTC)
    await db_session.commit()
    await reconcile_charges_for_appointment(db_session, appt, user_sub="u")
    assert await get_patient_balance(db_session, practice_id, patient_id) == 0
```

- [ ] **Step 2: Run — verify fail**

Run: `cd apps/api && pytest tests/integration/test_ledger_service.py -v -k reconcile`
Expected: FAIL (`reconcile_charges_for_appointment` undefined).

- [ ] **Step 3: Implement charge reconciliation**

Add to `apps/api/app/services/ledger/posting.py` (imports + functions):

```python
from typing import Any

from app.models.appointment_procedure import AppointmentProcedure


def _post_reversal_obj(original: LedgerEntry, posted_by: str) -> LedgerEntry:
    """Build (but do not add) a mirror entry for `original`."""
    return LedgerEntry(
        id=uuid.uuid4(),
        practice_id=original.practice_id,
        patient_id=original.patient_id,
        guarantor_account_id=original.guarantor_account_id,
        entry_type=original.entry_type,
        amount_cents=-original.amount_cents,
        appointment_id=original.appointment_id,
        appointment_procedure_id=original.appointment_procedure_id,
        claim_id=original.claim_id,
        remittance_id=original.remittance_id,
        reverses_entry_id=original.id,
        memo=f"auto reversal of {original.id}",
        posted_by=posted_by,
    )


async def _live_charges_by_proc(
    session: AsyncSession, appointment_id: uuid.UUID
) -> dict[uuid.UUID, LedgerEntry]:
    """Map appointment_procedure_id -> its live (un-reversed) charge entry."""
    reversed_ids = select(LedgerEntry.reverses_entry_id).where(
        LedgerEntry.reverses_entry_id.isnot(None),
        LedgerEntry.deleted_at.is_(None),
    )
    rows = (
        await session.scalars(
            select(LedgerEntry).where(
                LedgerEntry.appointment_id == appointment_id,
                LedgerEntry.entry_type == "charge",
                LedgerEntry.reverses_entry_id.is_(None),
                LedgerEntry.id.notin_(reversed_ids),
                LedgerEntry.deleted_at.is_(None),
            )
        )
    ).all()
    return {r.appointment_procedure_id: r for r in rows if r.appointment_procedure_id}


async def reconcile_charges_for_appointment(
    session: AsyncSession, appointment: Any, *, user_sub: str | None = None
) -> None:
    """Ensure exactly one live charge == fee_cents per live procedure of `appointment`.

    Idempotent. Posts reversing entries for stale/removed charges and new charges for
    new/changed procedures. `appointment` needs `.id`, `.practice_id`, `.patient_id`.
    """
    posted_by = user_sub or "system"
    procs = (
        await session.scalars(
            select(AppointmentProcedure).where(
                AppointmentProcedure.appointment_id == appointment.id,
                AppointmentProcedure.deleted_at.is_(None),
            )
        )
    ).all()
    proc_by_id = {p.id: p for p in procs}
    live = await _live_charges_by_proc(session, appointment.id)

    changed = False
    # Reverse charges whose procedure was deleted or whose fee changed.
    for proc_id, entry in live.items():
        proc = proc_by_id.get(proc_id)
        if proc is None or proc.fee_cents != entry.amount_cents:
            session.add(_post_reversal_obj(entry, posted_by))
            changed = True
    # Post charges for procedures lacking a matching live charge.
    for proc in procs:
        entry = live.get(proc.id)
        if entry is None or entry.amount_cents != proc.fee_cents:
            session.add(
                LedgerEntry(
                    id=uuid.uuid4(),
                    practice_id=appointment.practice_id,
                    patient_id=appointment.patient_id,
                    entry_type="charge",
                    amount_cents=proc.fee_cents,
                    appointment_id=appointment.id,
                    appointment_procedure_id=proc.id,
                    posted_by=posted_by,
                )
            )
            changed = True
    if changed:
        await session.commit()
```

- [ ] **Step 4: Run — verify pass**

Run: `cd apps/api && pytest tests/integration/test_ledger_service.py -v -k reconcile`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
cd apps/api && ruff check . && mypy app
git add apps/api/app/services/ledger/posting.py apps/api/tests/integration/test_ledger_service.py
git commit -m "feat(8a): charge reconciliation from completed appointment"
```

---

## Task 6: `posting.py` — insurance posting from a matched remittance

**Files:**
- Modify: `apps/api/app/services/ledger/posting.py`
- Test: add to `apps/api/tests/integration/test_ledger_service.py`

**Behavior:** Given a claim already matched to a remittance (7b has set `insurance_paid_cents`, `patient_responsibility_cents`, `adjustments`), post: one `insurance_payment` entry (`-insurance_paid_cents`) and one `adjustment` entry equal to the negative sum of **non-PR** (contractual write-off) adjustment cents — PR (patient-responsibility) adjustments are what the patient owes and are NOT written off. Idempotent on `(claim_id, remittance_id, entry_type)`: re-running posts nothing. Invariant for a single primary claim: `charge - insurance_payment - contractual_writeoff == patient_responsibility`.

- [ ] **Step 1: Write failing integration tests**

Append to `apps/api/tests/integration/test_ledger_service.py`:

```python
from app.models.claim import Claim
from app.services.ledger.posting import post_insurance_remittance


async def _seed_claim_for_ledger(session, practice_id, patient_id):
    claim = Claim(
        id=uuid.uuid4(),
        practice_id=practice_id,
        appointment_id=uuid.uuid4(),
        patient_id=patient_id,
        insurance_id=uuid.uuid4(),
        provider_id=uuid.uuid4(),
        idempotency_key=uuid.uuid4().hex,
        patient_control_number=uuid.uuid4().hex[:12],
        payer_id="CDLA1",
        status="partially_paid",
        total_charge_cents=25000,
        insurance_paid_cents=20000,
        patient_responsibility_cents=2000,
        adjustments=[
            {"group": "CO", "code": "45", "cents": 3000},   # contractual write-off
            {"group": "PR", "code": "2", "cents": 2000},    # patient responsibility
        ],
    )
    session.add(claim)
    await session.commit()
    return claim


@pytest.mark.asyncio
async def test_post_insurance_remittance_payment_and_writeoff(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    # patient already has the gross charge on the ledger
    await _add(db_session, practice_id, patient_id, "charge", 25000)
    claim = await _seed_claim_for_ledger(db_session, practice_id, patient_id)
    remittance_id = uuid.uuid4()

    await post_insurance_remittance(db_session, claim, remittance_id, user_sub="u")

    # 25000 charge - 20000 payment - 3000 contractual write-off = 2000 patient responsibility
    balance = await get_patient_balance(db_session, practice_id, patient_id)
    assert balance == claim.patient_responsibility_cents == 2000


@pytest.mark.asyncio
async def test_post_insurance_remittance_is_idempotent(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    await _add(db_session, practice_id, patient_id, "charge", 25000)
    claim = await _seed_claim_for_ledger(db_session, practice_id, patient_id)
    remittance_id = uuid.uuid4()

    await post_insurance_remittance(db_session, claim, remittance_id, user_sub="u")
    await post_insurance_remittance(db_session, claim, remittance_id, user_sub="u")  # no-op
    assert await get_patient_balance(db_session, practice_id, patient_id) == 2000


@pytest.mark.asyncio
async def test_post_insurance_remittance_no_writeoff_when_only_pr(db_session: AsyncSession):
    practice_id, patient_id = uuid.uuid4(), uuid.uuid4()
    await _add(db_session, practice_id, patient_id, "charge", 25000)
    claim = await _seed_claim_for_ledger(db_session, practice_id, patient_id)
    claim.adjustments = [{"group": "PR", "code": "2", "cents": 5000}]
    claim.insurance_paid_cents = 20000
    await db_session.commit()

    await post_insurance_remittance(db_session, claim, uuid.uuid4(), user_sub="u")
    # only the payment posts; PR is not written off -> 25000 - 20000 = 5000
    assert await get_patient_balance(db_session, practice_id, patient_id) == 5000
```

- [ ] **Step 2: Run — verify fail**

Run: `cd apps/api && pytest tests/integration/test_ledger_service.py -v -k insurance`
Expected: FAIL (`post_insurance_remittance` undefined).

- [ ] **Step 3: Implement insurance posting**

Add to `apps/api/app/services/ledger/posting.py`:

```python
async def _insurance_entry_exists(
    session: AsyncSession,
    claim_id: uuid.UUID,
    remittance_id: uuid.UUID,
    entry_type: str,
) -> bool:
    found = await session.scalar(
        select(LedgerEntry.id).where(
            LedgerEntry.claim_id == claim_id,
            LedgerEntry.remittance_id == remittance_id,
            LedgerEntry.entry_type == entry_type,
            LedgerEntry.reverses_entry_id.is_(None),
            LedgerEntry.deleted_at.is_(None),
        )
    )
    return found is not None


def _contractual_writeoff_cents(adjustments: list[dict[str, Any]] | None) -> int:
    """Sum of non-PR adjustment cents (contractual write-offs the provider absorbs).

    PR (patient responsibility) adjustments are what the patient owes and are NOT
    written off, so they are excluded.
    """
    if not adjustments:
        return 0
    return sum(int(a.get("cents", 0)) for a in adjustments if a.get("group") != "PR")


async def post_insurance_remittance(
    session: AsyncSession,
    claim: Any,
    remittance_id: uuid.UUID,
    *,
    user_sub: str | None = None,
) -> None:
    """Post insurance payment + contractual write-off entries for a matched claim.

    Reads the payment columns 7b set on the claim. Idempotent on
    (claim_id, remittance_id, entry_type). `claim` needs `.id`, `.practice_id`,
    `.patient_id`, `.insurance_paid_cents`, `.adjustments`.
    """
    posted_by = user_sub or "system"
    paid = claim.insurance_paid_cents or 0
    if paid and not await _insurance_entry_exists(
        session, claim.id, remittance_id, "insurance_payment"
    ):
        session.add(
            LedgerEntry(
                id=uuid.uuid4(),
                practice_id=claim.practice_id,
                patient_id=claim.patient_id,
                entry_type="insurance_payment",
                amount_cents=-paid,
                claim_id=claim.id,
                remittance_id=remittance_id,
                posted_by=posted_by,
            )
        )

    writeoff = _contractual_writeoff_cents(claim.adjustments)
    if writeoff and not await _insurance_entry_exists(
        session, claim.id, remittance_id, "adjustment"
    ):
        session.add(
            LedgerEntry(
                id=uuid.uuid4(),
                practice_id=claim.practice_id,
                patient_id=claim.patient_id,
                entry_type="adjustment",
                amount_cents=-writeoff,
                claim_id=claim.id,
                remittance_id=remittance_id,
                memo="contractual adjustment",
                posted_by=posted_by,
            )
        )
    await session.commit()
```

- [ ] **Step 4: Run — verify pass**

Run: `cd apps/api && pytest tests/integration/test_ledger_service.py -v -k insurance`
Expected: PASS.

- [ ] **Step 5: Run the whole ledger service suite + lint**

Run: `cd apps/api && pytest tests/integration/test_ledger_service.py tests/services/test_ledger_balance.py -v`
Expected: all PASS.
Run: `cd apps/api && ruff check . && mypy app`

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/ledger/posting.py apps/api/tests/integration/test_ledger_service.py
git commit -m "feat(8a): insurance payment + contractual write-off posting"
```

---

## Task 7: `ledger` router + feature flag

**Files:**
- Create: `apps/api/app/routers/ledger.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/integration/test_ledger_endpoints.py`

**Feature flag:** `ledger` write/read endpoints gate on `require_feature(..., "billing_ledger")` — a dedicated flag so the ledger enables independently of `claims_submission`.

- [ ] **Step 1: Write the router**

`apps/api/app/routers/ledger.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.core.db import get_session_factory
from app.core.features import require_feature
from app.models.ledger_entry import LedgerEntry as LedgerEntryModel
from app.models.patient import Patient as PatientModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import (
    AddAdjustmentRequest,
    ApiError,
    Error,
    LedgerEntry,
    PatientLedger,
    RecordPaymentRequest,
    ReverseEntryRequest,
)
from app.services.ledger.balance import get_ledger
from app.services.ledger.posting import (
    add_manual_adjustment,
    record_patient_payment,
    reverse_entry,
)

router = APIRouter(prefix="/api/v1", tags=["ledger"])

_FEATURE = "billing_ledger"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True),
    )


def _entry_schema(row: LedgerEntryModel, running_balance: int) -> LedgerEntry:
    return LedgerEntry(
        id=row.id,
        practiceId=row.practice_id,
        patientId=row.patient_id,
        entryType=row.entry_type,
        amountCents=row.amount_cents,
        runningBalanceCents=running_balance,
        appointmentId=row.appointment_id,
        appointmentProcedureId=row.appointment_procedure_id,
        claimId=row.claim_id,
        remittanceId=row.remittance_id,
        reversesEntryId=row.reverses_entry_id,
        paymentMethod=row.payment_method,
        memo=row.memo,
        postedBy=row.posted_by,
        postedAt=row.posted_at.replace(tzinfo=UTC),
    )


async def _require_patient(session, practice_id: uuid.UUID, patient_id: uuid.UUID) -> None:
    found = await session.scalar(
        select(PatientModel.id).where(
            PatientModel.id == patient_id,
            PatientModel.practice_id == practice_id,
            PatientModel.deleted_at.is_(None),
        )
    )
    if found is None:
        raise _err(404, "PATIENT_NOT_FOUND", "Patient not found in this practice")


@router.get("/patients/{patient_id}/ledger", response_model=PatientLedger)
async def get_patient_ledger(patient_id: uuid.UUID, request: Request) -> PatientLedger:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        await _require_patient(session, practice_id, patient_id)
        annotated, balance = await get_ledger(session, practice_id, patient_id)
        return PatientLedger(
            patientId=patient_id,
            balanceCents=balance,
            entries=[_entry_schema(row, rb) for row, rb in annotated],
        )


@router.post("/patients/{patient_id}/payments", status_code=201, response_model=LedgerEntry)
async def post_payment(
    patient_id: uuid.UUID, body: RecordPaymentRequest, request: Request
) -> LedgerEntry:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", None) or "system"
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        await _require_patient(session, practice_id, patient_id)
        try:
            entry = await record_patient_payment(
                session, practice_id, patient_id,
                amount_cents=body.amount_cents,
                payment_method=body.payment_method,
                memo=body.memo,
                posted_by=user_sub,
            )
        except ValueError as exc:
            raise _err(422, "INVALID_PAYMENT", str(exc)) from exc
        return _entry_schema(entry, entry.amount_cents)


@router.post("/patients/{patient_id}/adjustments", status_code=201, response_model=LedgerEntry)
async def post_adjustment(
    patient_id: uuid.UUID, body: AddAdjustmentRequest, request: Request
) -> LedgerEntry:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", None) or "system"
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        await _require_patient(session, practice_id, patient_id)
        try:
            entry = await add_manual_adjustment(
                session, practice_id, patient_id,
                amount_cents=body.amount_cents, memo=body.memo, posted_by=user_sub,
            )
        except ValueError as exc:
            raise _err(422, "INVALID_ADJUSTMENT", str(exc)) from exc
        return _entry_schema(entry, entry.amount_cents)


@router.post("/ledger/entries/{entry_id}/reverse", response_model=LedgerEntry)
async def post_reverse(
    entry_id: uuid.UUID, body: ReverseEntryRequest, request: Request
) -> LedgerEntry:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", None) or "system"
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        reversal = await reverse_entry(
            session, practice_id, entry_id, posted_by=user_sub, memo=body.memo
        )
        if reversal is None:
            raise _err(
                422, "CANNOT_REVERSE",
                "Entry not found, already reversed, or is itself a reversal",
            )
        return _entry_schema(reversal, reversal.amount_cents)
```

> Note: `runningBalanceCents` on the single-entry POST/reverse responses is set to the entry's own amount (the GET ledger endpoint is the source of truth for accumulated balances). This keeps the response schema uniform without an extra balance query on writes.

- [ ] **Step 2: Register the router**

In `apps/api/app/main.py`: add `ledger` to the `from app.routers import (...)` block and add after the `era` include (line ~146):

```python
    app.include_router(ledger.router)
```

- [ ] **Step 3: Write endpoint integration tests**

`apps/api/tests/integration/test_ledger_endpoints.py`:

```python
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient
from app.models.practice import Practice
from app.models.user import PracticeUser, User

pytestmark = pytest.mark.integration


async def _seed(session: AsyncSession, ledger_enabled: bool = True):
    practice = Practice(
        id=uuid.uuid4(),
        name="Sunrise Dental",
        timezone="America/New_York",
        features={"billing_ledger": ledger_enabled},
    )
    session.add(practice)
    cognito_sub = f"sub-{uuid.uuid4().hex}"
    user = User(
        id=uuid.uuid4(), cognito_sub=cognito_sub,
        email="s@x.test", full_name="Staff", is_active=True,
    )
    session.add(user)
    await session.flush()
    session.add(PracticeUser(practice_id=practice.id, user_id=user.id, role="admin",
                             is_active=True))
    from datetime import date
    patient = Patient(
        id=uuid.uuid4(), practice_id=practice.id, first_name="Jane", last_name="Doe",
        date_of_birth=date(1990, 6, 15), phone="+15551234567",
    )
    session.add(patient)
    await session.commit()
    return practice, user, cognito_sub, patient


def _auth(practice_id, cognito_sub, email):
    from unittest.mock import AsyncMock, patch
    return (
        patch("app.middleware.auth.jwt.get_unverified_header", return_value={"kid": "k"}),
        patch("app.middleware.auth._get_public_key", new=AsyncMock(return_value="pk")),
        patch("app.middleware.auth.jwt.decode", return_value={
            "sub": cognito_sub, "email": email, "cognito:groups": ["admin"]}),
    )


@pytest.mark.asyncio
async def test_record_payment_then_read_ledger(client: AsyncClient, db_session):
    practice, user, sub, patient = await _seed(db_session)
    p1, p2, p3 = _auth(practice.id, sub, user.email)
    headers = {"Authorization": "Bearer t", "X-Practice-ID": str(practice.id)}
    with p1, p2, p3:
        r = await client.post(
            f"/api/v1/patients/{patient.id}/payments",
            json={"amountCents": 5000, "paymentMethod": "cash", "memo": "copay"},
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert r.status_code == 201, r.text
        assert r.json()["amountCents"] == -5000

        r = await client.get(f"/api/v1/patients/{patient.id}/ledger", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["balanceCents"] == -5000
        assert len(body["entries"]) == 1


@pytest.mark.asyncio
async def test_record_payment_rejects_non_positive(client: AsyncClient, db_session):
    practice, user, sub, patient = await _seed(db_session)
    p1, p2, p3 = _auth(practice.id, sub, user.email)
    headers = {"Authorization": "Bearer t", "X-Practice-ID": str(practice.id)}
    with p1, p2, p3:
        r = await client.post(
            f"/api/v1/patients/{patient.id}/payments",
            json={"amountCents": -100, "paymentMethod": "cash"},
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        )
    # negative fails Zod-generated validation (positive int) -> 422
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_ledger_requires_feature(client: AsyncClient, db_session):
    practice, user, sub, patient = await _seed(db_session, ledger_enabled=False)
    p1, p2, p3 = _auth(practice.id, sub, user.email)
    headers = {"Authorization": "Bearer t", "X-Practice-ID": str(practice.id)}
    with p1, p2, p3:
        r = await client.get(f"/api/v1/patients/{patient.id}/ledger", headers=headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_adjustment_requires_memo(client: AsyncClient, db_session):
    practice, user, sub, patient = await _seed(db_session)
    p1, p2, p3 = _auth(practice.id, sub, user.email)
    headers = {"Authorization": "Bearer t", "X-Practice-ID": str(practice.id)}
    with p1, p2, p3:
        r = await client.post(
            f"/api/v1/patients/{patient.id}/adjustments",
            json={"amountCents": -1000, "memo": ""},
            headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
        )
    assert r.status_code == 422
```

> If `_seed`'s `Practice(features=...)` / auth mock differs from the live `test_era_endpoints.py` helper, copy that file's exact `_seed`/auth pattern — it is the canonical reference for feature-gated endpoint tests.

- [ ] **Step 4: Run — verify pass**

Run: `cd apps/api && pytest tests/integration/test_ledger_endpoints.py -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
cd apps/api && ruff check . && mypy app
git add apps/api/app/routers/ledger.py apps/api/app/main.py \
  apps/api/tests/integration/test_ledger_endpoints.py
git commit -m "feat(8a): ledger router (read/payment/adjustment/reverse) + billing_ledger flag"
```

---

## Task 8: Hook charge reconciliation into appointment checkout

**Files:**
- Modify: `apps/api/app/routers/appointments.py`
- Test: add to `apps/api/tests/integration/test_appointments.py` (or a new `test_appointments_ledger.py`)

**Behavior:** When `update_appointment` transitions status to `completed` (and the appointment has a patient), reconcile charges. Also reconcile when procedures change while the appointment is already `completed` — but that path lives in the appointment-procedures router; for 8a, wire the `update_appointment` `→ completed` case (the primary trigger). Add a follow-up note for the procedure-edit path.

- [ ] **Step 1: Write failing integration test**

Add to `apps/api/tests/integration/test_appointments.py` (new test; reuse the file's existing fixtures/auth helpers — match its style):

```python
@pytest.mark.asyncio
async def test_completing_appointment_posts_ledger_charges(client, db_session, ...):
    # 1. create an appointment with a patient (existing helpers in this file)
    # 2. add an appointment_procedure with fee_cents=12000 to it
    # 3. PATCH the appointment status -> "completed"
    # 4. GET /api/v1/patients/{patient_id}/ledger (enable billing_ledger on the practice)
    #    assert balanceCents == 12000 and one charge entry exists
    ...
```

> Fill in using the concrete fixtures already in `test_appointments.py`. The appointment's practice must have `features={"billing_ledger": True, ...}` for the ledger read; set it on the seeded practice. Assert the charge posted.

- [ ] **Step 2: Run — verify fail**

Run: `cd apps/api && pytest tests/integration/test_appointments.py -v -k ledger_charges`
Expected: FAIL (no ledger entry yet).

- [ ] **Step 3: Wire the hook**

In `apps/api/app/routers/appointments.py`:

Add import near the other service imports at the top of the file:

```python
from app.services.ledger.posting import reconcile_charges_for_appointment
```

In `update_appointment`, after the risk-recompute block and **before** `await session.commit()` (around line 687), add:

```python
        # Post patient-ledger charges when the visit is finalized at checkout.
        if (
            "status" in provided
            and body.status == "completed"
            and row.patient_id is not None
        ):
            user_sub = getattr(request.state.user, "sub", None)
            await reconcile_charges_for_appointment(session, row, user_sub=user_sub)
```

> `reconcile_charges_for_appointment` calls `session.commit()` internally when it posts; the subsequent `await session.commit()` in `update_appointment` is a harmless no-op/flush for the appointment row changes. (Confirm no "already committed" error in the test; if needed, the appointment field writes happen before this block so they're already flushed.)

- [ ] **Step 4: Run — verify pass**

Run: `cd apps/api && pytest tests/integration/test_appointments.py -v -k ledger_charges`
Expected: PASS.

- [ ] **Step 5: Full appointments suite (no regressions) + lint**

Run: `cd apps/api && pytest tests/integration/test_appointments.py -v`
Run: `cd apps/api && ruff check . && mypy app`

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/routers/appointments.py apps/api/tests/integration/test_appointments.py
git commit -m "feat(8a): post ledger charges on appointment checkout"
```

---

## Task 9: Hook insurance posting into the ERA poll

**Files:**
- Modify: `apps/api/app/services/era/service.py`
- Test: add to `apps/api/tests/integration/test_era_service.py`

**Behavior:** In `poll_and_post_eras`, immediately after `_post_to_claim(claim, cp, remittance.id, user_sub)` (the match branch), also post ledger entries for that claim+remittance.

- [ ] **Step 1: Write failing integration test**

Append to `apps/api/tests/integration/test_era_service.py`:

```python
from app.services.ledger.balance import get_patient_balance


@pytest.mark.asyncio
async def test_era_match_posts_ledger_insurance_entries(db_session: AsyncSession):
    claim = await _seed_claim(db_session, "PCNLED123")
    # gross charge already on the ledger for this patient
    from app.models.ledger_entry import LedgerEntry
    db_session.add(LedgerEntry(
        id=uuid.uuid4(), practice_id=claim.practice_id, patient_id=claim.patient_id,
        entry_type="charge", amount_cents=25000,
    ))
    await db_session.commit()

    client = _FakeClient({"txn-1": _era_doc("PCNLED123")})  # paid 200.00, PR 50.00
    summary = await poll_and_post_eras(
        db_session, claim.practice_id, client=client,
        since=datetime.now(UTC) - timedelta(days=30), user_sub="s",
    )
    assert summary["matched"] == 1
    # 25000 charge - 20000 insurance payment = 5000 (no non-PR adjustment in _era_doc)
    balance = await get_patient_balance(db_session, claim.practice_id, claim.patient_id)
    assert balance == 5000
```

> Note: `_era_doc` produces `claimPaymentAmount=200.00` and no CAS adjustments, so only the `insurance_payment` posts. If you want to also assert the write-off path here, extend `_era_doc` with an adjustment — otherwise the contractual-writeoff math is already covered in `test_ledger_service.py`.

- [ ] **Step 2: Run — verify fail**

Run: `cd apps/api && pytest tests/integration/test_era_service.py -v -k ledger_insurance`
Expected: FAIL (balance is 25000 — insurance entry not posted).

- [ ] **Step 3: Wire the hook**

In `apps/api/app/services/era/service.py`:

Add import at the top:

```python
from app.services.ledger.posting import post_insurance_remittance
```

In `poll_and_post_eras`, the match branch currently reads:

```python
            if claim is not None:
                _post_to_claim(claim, cp, remittance.id, user_sub)
                r_matched += 1
```

Change to:

```python
            if claim is not None:
                _post_to_claim(claim, cp, remittance.id, user_sub)
                await session.flush()  # ensure claim payment columns are set before ledger read
                await post_insurance_remittance(
                    session, claim, remittance.id, user_sub=user_sub
                )
                r_matched += 1
```

> `post_insurance_remittance` commits internally; the existing `await session.commit()` at the end of the per-transaction loop remains correct. `_post_to_claim` mutates the claim object in memory, so `post_insurance_remittance` reads the just-set `insurance_paid_cents`/`adjustments` directly — the `flush()` is belt-and-suspenders.

- [ ] **Step 4: Run — verify pass**

Run: `cd apps/api && pytest tests/integration/test_era_service.py -v -k ledger_insurance`
Expected: PASS.

- [ ] **Step 5: Full ERA suite (no regressions) + lint**

Run: `cd apps/api && pytest tests/integration/test_era_service.py -v`
Expected: all PASS (existing 7b tests unaffected — they don't assert ledger state).
Run: `cd apps/api && ruff check . && mypy app`

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/era/service.py apps/api/tests/integration/test_era_service.py
git commit -m "feat(8a): post ledger insurance entries on ERA match"
```

---

## Task 10: Frontend — Ledger tab on the patient chart

**Files:**
- Create: `apps/web/lib/api/ledger.ts`
- Create: `apps/web/components/patients/LedgerTab.tsx`
- Modify: `apps/web/app/(app)/patients/[patientId]/page.tsx`

- [ ] **Step 1: API hooks**

`apps/web/lib/api/ledger.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";

export type LedgerEntryType =
  | "charge"
  | "insurance_payment"
  | "patient_payment"
  | "adjustment";
export type LedgerPaymentMethod =
  | "cash"
  | "check"
  | "card"
  | "external_terminal"
  | "other";

export interface LedgerEntry {
  id: string;
  practiceId: string;
  patientId: string;
  entryType: LedgerEntryType;
  amountCents: number;
  runningBalanceCents: number;
  appointmentId: string | null;
  appointmentProcedureId: string | null;
  claimId: string | null;
  remittanceId: string | null;
  reversesEntryId: string | null;
  paymentMethod: LedgerPaymentMethod | null;
  memo: string | null;
  postedBy: string;
  postedAt: string;
}

export interface PatientLedger {
  patientId: string;
  balanceCents: number;
  entries: LedgerEntry[];
}

export const ledgerKeys = {
  patient: (patientId: string) => ["ledger", patientId] as const,
};

export function usePatientLedger(patientId: string) {
  return useQuery({
    queryKey: ledgerKeys.patient(patientId),
    queryFn: () => apiClient.get<PatientLedger>(`/api/v1/patients/${patientId}/ledger`),
  });
}

export function useRecordPayment(patientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      amountCents: number;
      paymentMethod: LedgerPaymentMethod;
      memo?: string | null;
    }) =>
      apiClient.post<LedgerEntry>(`/api/v1/patients/${patientId}/payments`, body, {
        idempotencyKey: generateId(),
      }),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ledgerKeys.patient(patientId) }),
  });
}

export function useAddAdjustment(patientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { amountCents: number; memo: string }) =>
      apiClient.post<LedgerEntry>(`/api/v1/patients/${patientId}/adjustments`, body, {
        idempotencyKey: generateId(),
      }),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ledgerKeys.patient(patientId) }),
  });
}
```

> Verify the exact `apiClient.post` signature / options shape against `apps/web/lib/api/claims.ts` and `apps/web/lib/api-client.ts` — match it (the `{ idempotencyKey }` option mirrors `useSubmitClaim`).

- [ ] **Step 2: LedgerTab component**

`apps/web/components/patients/LedgerTab.tsx` — a balance badge + entries table + two action forms. Follow the table/markup conventions from `apps/web/app/(app)/billing/claims/page.tsx` (`Table`, `TableHeader`, `TableRow`, `TableCell`, `Badge`, the `centsToUsd` helper). Skeleton:

```tsx
"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useAddAdjustment,
  usePatientLedger,
  useRecordPayment,
  type LedgerEntry,
} from "@/lib/api/ledger";

function centsToUsd(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  return `${sign}$${(Math.abs(cents) / 100).toFixed(2)}`;
}

function describe(entry: LedgerEntry): string {
  if (entry.reversesEntryId) return "Reversal";
  switch (entry.entryType) {
    case "charge":
      return "Charge";
    case "insurance_payment":
      return "Insurance payment";
    case "patient_payment":
      return `Patient payment${entry.paymentMethod ? ` (${entry.paymentMethod})` : ""}`;
    case "adjustment":
      return entry.memo ?? "Adjustment";
  }
}

export function LedgerTab({ patientId }: { patientId: string }) {
  const { data, isLoading } = usePatientLedger(patientId);
  const recordPayment = useRecordPayment(patientId);
  const addAdjustment = useAddAdjustment(patientId);
  const [showPayment, setShowPayment] = useState(false);
  const [showAdjustment, setShowAdjustment] = useState(false);

  const ledger = data;
  const balance = ledger?.balanceCents ?? 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Balance</span>
          <Badge variant={balance > 0 ? "destructive" : "secondary"}>
            {balance < 0 ? `${centsToUsd(balance)} credit` : centsToUsd(balance)}
          </Badge>
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={() => setShowPayment((v) => !v)}>
            Record Payment
          </Button>
          <Button size="sm" variant="outline" onClick={() => setShowAdjustment((v) => !v)}>
            Add Adjustment
          </Button>
        </div>
      </div>

      {/* showPayment: amount input + method select + submit -> recordPayment.mutate(...) */}
      {/* showAdjustment: amount input (signed) + memo input + submit -> addAdjustment.mutate(...) */}

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
      {!isLoading && ledger && ledger.entries.length === 0 && (
        <p className="rounded-lg border border-border py-12 text-center text-sm text-muted-foreground">
          No ledger activity yet.
        </p>
      )}
      {!isLoading && ledger && ledger.entries.length > 0 && (
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Description</TableHead>
                <TableHead className="text-right">Charge</TableHead>
                <TableHead className="text-right">Credit</TableHead>
                <TableHead className="text-right">Balance</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ledger.entries.map((e) => (
                <TableRow key={e.id} className={e.reversesEntryId ? "text-muted-foreground" : ""}>
                  <TableCell>{e.postedAt.slice(0, 10)}</TableCell>
                  <TableCell>{describe(e)}</TableCell>
                  <TableCell className="text-right">
                    {e.amountCents > 0 ? centsToUsd(e.amountCents) : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    {e.amountCents < 0 ? centsToUsd(-e.amountCents) : "—"}
                  </TableCell>
                  <TableCell className="text-right">{centsToUsd(e.runningBalanceCents)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
```

> Implement the two inline forms (payment: amount + method `<select>` + submit; adjustment: signed amount + required memo + submit) using the same `<select>`/`<input>` styling as `billing/claims/page.tsx`. Disable submit while the mutation `isPending`. Confirm `Button` exists at `@/components/ui/button` (used elsewhere in the app); if the import path differs, match the existing usage.

- [ ] **Step 3: Add the tab to the patient chart**

In `apps/web/app/(app)/patients/[patientId]/page.tsx`:

1. Import: `import { LedgerTab } from "@/components/patients/LedgerTab";`
2. Add `"ledger"` to the `activeTab` union type (line 778) and to the tab list array (line 852):
   ```tsx
   (["overview", "notes", "tooth-chart", "treatment-plan", "perio", "procedure-history", "ledger"] as const)
   ```
3. Add a label case in the tab button (it will render "ledger" capitalized by default — fine, or add an explicit `: tab === "ledger" ? "Ledger"`).
4. Add the panel after the procedure-history block (line ~923):
   ```tsx
   {activeTab === "ledger" && <LedgerTab patientId={patientId} />}
   ```

- [ ] **Step 4: Typecheck + lint the web app**

Run: `cd apps/web && pnpm tsc --noEmit && pnpm lint`
Expected: clean. (Run the dev server and click the Ledger tab if you want a visual check — optional.)

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/api/ledger.ts apps/web/components/patients/LedgerTab.tsx \
  "apps/web/app/(app)/patients/[patientId]/page.tsx"
git commit -m "feat(8a): patient ledger tab (balance, entries, payment/adjustment actions)"
```

---

## Task 11: Roadmap + spec status updates

**Files:**
- Modify: `longterm_build_plan.md`
- Modify: `docs/superpowers/specs/phase3-build-order.md`

- [ ] **Step 1: Mark Module 8a built in the roadmap**

In `longterm_build_plan.md`, update the Module 8 line: change `🔲 **Module 8 — Billing & Payments**` to reflect 8a built (ledger) with 8b statements / aging / QuickBooks export still pending, referencing the spec and the future-Stripe note. Keep the existing wording style of the other "built" module lines (e.g. Module 7).

- [ ] **Step 2: Update the build-order table**

In `docs/superpowers/specs/phase3-build-order.md`, update row `6 | 8 — Billing & Payments` to point at `2026-06-23-module-8a-patient-ledger-design.md` and note 8a (ledger) built; statements/aging/QuickBooks-export deferred to 8b+.

- [ ] **Step 3: Commit**

```bash
git add longterm_build_plan.md docs/superpowers/specs/phase3-build-order.md
git commit -m "docs(8a): mark patient ledger built; statements/aging/QB export deferred to 8b+"
```

---

## Final verification

- [ ] Run the full new test set (integration — confirm DB up / OK to run):
  ```bash
  cd apps/api && pytest tests/services/test_ledger_balance.py \
    tests/integration/test_ledger_service.py \
    tests/integration/test_ledger_endpoints.py -v
  ```
- [ ] Run the touched existing suites for regressions:
  ```bash
  cd apps/api && pytest tests/integration/test_appointments.py \
    tests/integration/test_era_service.py -v
  ```
- [ ] Full-repo lint (matches CI): `cd apps/api && ruff check . && mypy app`
- [ ] Web: `cd apps/web && pnpm tsc --noEmit && pnpm lint`
- [ ] Use superpowers:finishing-a-development-branch to open the PR.
```
