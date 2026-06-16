# Module 6 — Co-pay / Patient-Responsibility Calculation: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn captured procedures + eligibility data into an estimate of what the patient owes vs. what insurance pays, persisted onto procedure rows and a snapshot, for PPO/Premier + MassHealth + OON plans.

**Architecture:** A pure, I/O-free calculation engine (`app/services/copay/`) wrapped by a thin `CopayService` that loads rows, resolves contracted fees / coinsurance / frequency counts, calls the engine, and persists results. New API endpoints under the appointment, plus a contracted-fee Settings surface. Mirrors how Module 5 split its pure 271 parser from its router.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy (async) / Alembic; Pydantic schemas generated from Zod (`packages/shared-types` → `pnpm --filter @molar/shared-types generate` → `app/schemas/generated.py`); pytest (`tests/services`, `tests/integration`); React + TypeScript frontend.

**Source spec:** `docs/superpowers/specs/2026-06-16-module-6-copay-calculation-design.md`

---

## Recommended PR split

This plan is organized into four **independently shippable parts**. Each leaves the app green and is useful on its own:

- **PR 1 — Contracted Fee Schedule** (Part 1): table + CRUD + Settings UI. Standalone; practices can enter contracted rates immediately.
- **PR 2 — Eligibility parser extension** (Part 2): per-CDT coinsurance map + `plan_type`/`network_status` + the eligibility schema additions. Standalone; enriches eligibility data.
- **PR 3 — Full CDT catalog seed** (Part 3): one data migration. Standalone.
- **PR 4 — Engine + Service + Endpoints + Frontend** (Part 4): the core. Depends on PRs 1–3.

PRs 1–3 are mutually independent and may land in any order or in parallel. **Migration revision numbers below assume the order 0028 (PR1) → 0029 (PR2) → 0030 (PR3) → 0031 (PR4); if you merge in a different order, renumber `revision`/`down_revision` to match the actual chain head** (check `apps/api/alembic/versions/` for the latest revision before creating each migration).

Each task is TDD: write the failing test, watch it fail, implement, watch it pass, commit. Run backend tests from `apps/api/` with `uv run pytest`. Non-integration tests run automatically; integration tests (marked `@pytest.mark.integration`) need the test Postgres — ask before running them.

---

# PART 1 — Contracted Fee Schedule (PR 1)

The authoritative source of carrier "allowed amounts." Keyed `(practice_id, payer_id, cdt_code_id)`; billed-fee fallback happens later in the engine (Part 4), so this part is pure CRUD.

### Task 1.1: Migration — `contracted_fee_schedule` table

**Files:**
- Create: `apps/api/alembic/versions/0028_contracted_fee_schedule.py`

- [ ] **Step 1: Write the migration**

```python
"""Contracted fee schedule (per-carrier allowed amounts)

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0028"
down_revision: str | Sequence[str] | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contracted_fee_schedule",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payer_id", sa.String(50), nullable=False),
        sa.Column("cdt_code_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("allowed_amount_cents", sa.Integer, nullable=True),
        sa.Column("not_covered", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("requires_prior_auth", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["cdt_code_id"], ["cdt_codes.id"],
            name="fk_contracted_fee_schedule_cdt_code",
        ),
    )
    op.create_index(
        "ix_contracted_fee_schedule_lookup",
        "contracted_fee_schedule", ["practice_id", "payer_id"],
    )
    op.create_index(
        "uq_contracted_fee_schedule_active",
        "contracted_fee_schedule",
        ["practice_id", "payer_id", "cdt_code_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("contracted_fee_schedule")
```

- [ ] **Step 2: Apply and verify the migration runs**

Run: `cd apps/api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: no errors; `contracted_fee_schedule` created, dropped, recreated.

- [ ] **Step 3: Commit**

```bash
git add apps/api/alembic/versions/0028_contracted_fee_schedule.py
git commit -m "feat(6): contracted_fee_schedule migration"
```

### Task 1.2: Model — `ContractedFeeSchedule`

**Files:**
- Create: `apps/api/app/models/contracted_fee_schedule.py`

- [ ] **Step 1: Write the model**

```python
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ContractedFeeSchedule(Base, TimestampMixin):
    """Per-carrier contracted allowed amount for a CDT code. Source of truth for
    the engine's allowed_amount; the engine falls back to the billed fee when no
    active row exists. Keyed (practice_id, payer_id, cdt_code_id). Soft-deletable."""

    __tablename__ = "contracted_fee_schedule"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payer_id: Mapped[str] = mapped_column(String(50), nullable=False)
    cdt_code_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cdt_codes.id", name="fk_contracted_fee_schedule_cdt_code"),
        nullable=False,
    )
    allowed_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    not_covered: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    requires_prior_auth: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    __table_args__ = (
        Index("ix_contracted_fee_schedule_lookup", "practice_id", "payer_id"),
    )
```

- [ ] **Step 2: Verify it imports**

Run: `cd apps/api && uv run python -c "from app.models.contracted_fee_schedule import ContractedFeeSchedule"`
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add apps/api/app/models/contracted_fee_schedule.py
git commit -m "feat(6): ContractedFeeSchedule model"
```

### Task 1.3: Zod schemas + generate Pydantic

**Files:**
- Create: `packages/shared-types/src/schemas/copay.ts`
- Modify: `packages/shared-types/src/index.ts` (add `export * from "./schemas/copay.js";`)

- [ ] **Step 1: Write the Zod schemas (contracted-fee slice only for now)**

```typescript
import { z } from "zod";
import { UuidSchema } from "./common.js";
import { CdtCategorySchema } from "./procedures.js";

// ---- Contracted fee schedule (Part 1) ----

export const ContractedFeeRowSchema = z.object({
  cdtCodeId: UuidSchema,
  code: z.string().min(1),
  description: z.string().min(1),
  category: CdtCategorySchema,
  payerId: z.string().min(1),
  allowedAmountCents: z.number().int().nonnegative().nullable(),
  notCovered: z.boolean(),
  requiresPriorAuth: z.boolean(),
});
export type ContractedFeeRow = z.infer<typeof ContractedFeeRowSchema>;

export const SetContractedFeeSchema = z.object({
  allowedAmountCents: z.number().int().nonnegative().nullable(),
  notCovered: z.boolean().optional(),
  requiresPriorAuth: z.boolean().optional(),
});
export type SetContractedFee = z.infer<typeof SetContractedFeeSchema>;
```

- [ ] **Step 2: Add the export**

In `packages/shared-types/src/index.ts`, add alongside the other schema exports:
```typescript
export * from "./schemas/copay.js";
```

- [ ] **Step 3: Generate Pydantic + verify the new models exist**

Run: `pnpm --filter @molar/shared-types generate && cd apps/api && uv run python -c "from app.schemas.generated import ContractedFeeRow, SetContractedFee"`
Expected: generation prints output; import succeeds, exit 0.

- [ ] **Step 4: Commit**

```bash
git add packages/shared-types/src/schemas/copay.ts packages/shared-types/src/index.ts apps/api/app/schemas/generated.py
git commit -m "feat(6): contracted-fee Zod schemas + generated Pydantic"
```

### Task 1.4: Router — contracted-fee CRUD + integration tests

**Files:**
- Create: `apps/api/app/routers/contracted_fees.py`
- Modify: `apps/api/app/main.py` (import + `include_router`)
- Test: `apps/api/tests/integration/test_contracted_fees.py`

- [ ] **Step 1: Write the router**

```python
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.core.features import require_feature
from app.models.appointment_procedure import CdtCode as CdtCodeModel
from app.models.contracted_fee_schedule import ContractedFeeSchedule as ContractedModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import ApiError, ContractedFeeRow, Error, SetContractedFee

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/contracted-fees", tags=["contracted-fees"])

_FEATURE = "copay_estimation"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True),
    )


def _row_to_schema(cdt: CdtCodeModel, payer_id: str, row: ContractedModel | None) -> ContractedFeeRow:
    return ContractedFeeRow(
        cdtCodeId=cdt.id,
        code=cdt.code,
        description=cdt.description,
        category=cdt.category,  # type: ignore[arg-type]
        payerId=payer_id,
        allowedAmountCents=row.allowed_amount_cents if row else None,  # type: ignore[arg-type]
        notCovered=row.not_covered if row else False,
        requiresPriorAuth=row.requires_prior_auth if row else False,
    )


@router.get("", response_model=list[ContractedFeeRow])
async def list_contracted_fees(payer_id: str, request: Request) -> list[ContractedFeeRow]:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        result = await session.execute(
            select(CdtCodeModel, ContractedModel)
            .outerjoin(
                ContractedModel,
                and_(
                    ContractedModel.cdt_code_id == CdtCodeModel.id,
                    ContractedModel.practice_id == practice_id,
                    ContractedModel.payer_id == payer_id,
                    ContractedModel.deleted_at.is_(None),
                ),
            )
            .where(CdtCodeModel.is_active.is_(True), CdtCodeModel.deleted_at.is_(None))
            .order_by(CdtCodeModel.code.asc())
        )
        return [_row_to_schema(cdt, payer_id, row) for cdt, row in result.all()]


async def _load_active_code(session: AsyncSession, cdt_code_id: uuid.UUID) -> CdtCodeModel:
    cdt = await session.scalar(
        select(CdtCodeModel).where(
            CdtCodeModel.id == cdt_code_id,
            CdtCodeModel.is_active.is_(True),
            CdtCodeModel.deleted_at.is_(None),
        )
    )
    if cdt is None:
        raise _err(404, "CDT_CODE_NOT_FOUND", "Unknown CDT code")
    return cdt


@router.put("/{cdt_code_id}", response_model=ContractedFeeRow)
async def set_contracted_fee(
    cdt_code_id: uuid.UUID, payer_id: str, body: SetContractedFee, request: Request
) -> ContractedFeeRow:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        cdt = await _load_active_code(session, cdt_code_id)
        row = await session.scalar(
            select(ContractedModel).where(
                ContractedModel.practice_id == practice_id,
                ContractedModel.payer_id == payer_id,
                ContractedModel.cdt_code_id == cdt.id,
                ContractedModel.deleted_at.is_(None),
            )
        )
        if row is None:
            row = ContractedModel(
                id=uuid.uuid4(),
                practice_id=practice_id,
                payer_id=payer_id,
                cdt_code_id=cdt.id,
                allowed_amount_cents=body.allowed_amount_cents,
                not_covered=body.not_covered if body.not_covered is not None else False,
                requires_prior_auth=(
                    body.requires_prior_auth if body.requires_prior_auth is not None else False
                ),
            )
            session.add(row)
        else:
            row.allowed_amount_cents = body.allowed_amount_cents
            if body.not_covered is not None:
                row.not_covered = body.not_covered
            if body.requires_prior_auth is not None:
                row.requires_prior_auth = body.requires_prior_auth
            row.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(row)
        return _row_to_schema(cdt, payer_id, row)


@router.delete("/{cdt_code_id}", status_code=204)
async def revert_contracted_fee(
    cdt_code_id: uuid.UUID, payer_id: str, request: Request
) -> None:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        row = await session.scalar(
            select(ContractedModel).where(
                ContractedModel.practice_id == practice_id,
                ContractedModel.payer_id == payer_id,
                ContractedModel.cdt_code_id == cdt_code_id,
                ContractedModel.deleted_at.is_(None),
            )
        )
        if row is not None:
            row.deleted_at = datetime.now(UTC)
            await session.commit()
```

- [ ] **Step 2: Wire the router into the app**

In `apps/api/app/main.py`, add `contracted_fees` to the `from app.routers import (...)` block and add after the `fee_schedule` line (~line 138):
```python
    app.include_router(contracted_fees.router)
```

- [ ] **Step 3: Write integration tests**

Mirror the auth/role helpers from `tests/integration/test_fee_schedule.py`. Use a practice with `features={"copay_estimation": True, "eligibility_verification": True}`.

```python
"""Integration tests for /api/v1/contracted-fees (GET/PUT/DELETE)."""
from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

_PAYER = "62308"


class TestContractedFees:
    async def test_get_lists_catalog_with_blank_fees(self, client: AsyncClient, auth_headers):
        resp = await client.get(
            "/api/v1/contracted-fees", params={"payer_id": _PAYER}, headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        rows = resp.json()
        assert all(r["allowedAmountCents"] is None for r in rows)

    async def test_put_then_get_reflects_allowed_amount(self, client: AsyncClient, auth_headers):
        rows = (await client.get(
            "/api/v1/contracted-fees", params={"payer_id": _PAYER}, headers=auth_headers
        )).json()
        code_id = rows[0]["cdtCodeId"]
        put = await client.put(
            f"/api/v1/contracted-fees/{code_id}",
            params={"payer_id": _PAYER},
            json={"allowedAmountCents": 8000, "notCovered": False},
            headers={**auth_headers, "Idempotency-Key": "ck-1"},
        )
        assert put.status_code == 200, put.text
        assert put.json()["allowedAmountCents"] == 8000

    async def test_put_unknown_code_404(self, client: AsyncClient, auth_headers):
        import uuid
        resp = await client.put(
            f"/api/v1/contracted-fees/{uuid.uuid4()}",
            params={"payer_id": _PAYER},
            json={"allowedAmountCents": 100},
            headers={**auth_headers, "Idempotency-Key": "ck-2"},
        )
        assert resp.status_code == 404

    async def test_delete_reverts(self, client: AsyncClient, auth_headers):
        rows = (await client.get(
            "/api/v1/contracted-fees", params={"payer_id": _PAYER}, headers=auth_headers
        )).json()
        code_id = rows[0]["cdtCodeId"]
        await client.put(
            f"/api/v1/contracted-fees/{code_id}",
            params={"payer_id": _PAYER},
            json={"allowedAmountCents": 5000},
            headers={**auth_headers, "Idempotency-Key": "ck-3"},
        )
        d = await client.delete(
            f"/api/v1/contracted-fees/{code_id}",
            params={"payer_id": _PAYER},
            headers={**auth_headers, "Idempotency-Key": "ck-4"},
        )
        assert d.status_code == 204
        rows2 = (await client.get(
            "/api/v1/contracted-fees", params={"payer_id": _PAYER}, headers=auth_headers
        )).json()
        assert next(r for r in rows2 if r["cdtCodeId"] == code_id)["allowedAmountCents"] is None
```

- [ ] **Step 4: Run the tests (integration — ask first)**

Run: `cd apps/api && uv run pytest tests/integration/test_contracted_fees.py -v`
Expected: all PASS. (If the shared `auth_headers`/`client` fixtures' practice lacks `copay_estimation`, enable it in the fixture; check `tests/integration/conftest.py` for how `features` is set and add the flag.)

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/routers/contracted_fees.py apps/api/app/main.py apps/api/tests/integration/test_contracted_fees.py
git commit -m "feat(6): contracted-fees CRUD endpoints + tests"
```

### Task 1.5: Frontend — Settings → Contracted Fees

**Files:**
- Create: `apps/web/src/features/settings/ContractedFeesSettings.tsx`
- Modify: the settings navigation/router (find where `FeeScheduleSettings` or the 3.6 fee page is registered and add a sibling route/tab)

- [ ] **Step 1: Find the existing fee-schedule Settings surface to mirror**

Run: `cd apps/web && grep -rl "fee-schedule\|FeeSchedule" src/ | head`
Expected: the 3.6 component + its route registration. Mirror its data-fetch (TanStack Query or the project's client), table, and editable-cents field. Reuse the dollars↔cents conversion helper it uses.

- [ ] **Step 2: Build the component**

Render a payer selector (the practice's payers / `payer_id`s) + a searchable CDT table with columns: code, description, allowed amount (editable dollars→cents on save), Not covered (checkbox), Prior auth (checkbox). On save call `PUT /api/v1/contracted-fees/{cdtCodeId}?payer_id=…`; on clear call `DELETE`. Mirror the exact query/mutation and form patterns from the 3.6 component found in Step 1 (do not invent a new data layer).

- [ ] **Step 3: Register the route/tab** next to the existing Fee Schedule settings entry found in Step 1.

- [ ] **Step 4: Typecheck + lint**

Run: `cd apps/web && pnpm typecheck && pnpm lint`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/features/settings/ContractedFeesSettings.tsx apps/web/src/<route-file>
git commit -m "feat(6): Settings contracted-fees data entry"
```

---

# PART 2 — Eligibility parser extension (PR 2)

Add the eligibility fields Module 6 needs and populate the per-CDT coinsurance map. Pure-parser TDD against fixtures.

### Task 2.1: Migration — extend `eligibility_checks`

**Files:**
- Create: `apps/api/alembic/versions/0029_eligibility_copay_fields.py`

- [ ] **Step 1: Write the migration**

```python
"""Eligibility fields for Module 6 (plan_type, network, per-code coinsurance, waivers)

Revision ID: 0029
Revises: 0028
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0029"
down_revision: str | Sequence[str] | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "eligibility_checks",
        sa.Column("plan_type", sa.String(20), nullable=False, server_default="ppo"),
    )
    op.add_column(
        "eligibility_checks",
        sa.Column(
            "network_status", sa.String(20), nullable=False, server_default="in_network"
        ),
    )
    op.add_column(
        "eligibility_checks",
        sa.Column("coinsurance_by_code", postgresql.JSONB, nullable=True),
    )
    op.add_column(
        "eligibility_checks",
        sa.Column(
            "deductible_waived_diagnostic", sa.Boolean, nullable=False, server_default="false"
        ),
    )
    op.add_column(
        "eligibility_checks",
        sa.Column(
            "deductible_waived_preventive", sa.Boolean, nullable=False, server_default="true"
        ),
    )
    op.add_column(
        "eligibility_checks",
        sa.Column(
            "deductible_waived_orthodontic", sa.Boolean, nullable=False, server_default="false"
        ),
    )
    op.add_column(
        "eligibility_checks", sa.Column("ortho_lifetime_max", sa.Integer, nullable=True)
    )
    op.add_column(
        "eligibility_checks", sa.Column("ortho_lifetime_max_used", sa.Integer, nullable=True)
    )
    op.create_check_constraint(
        "ck_eligibility_checks_plan_type",
        "eligibility_checks",
        "plan_type IN ('ppo', 'premier', 'medicaid', 'indemnity', 'dhmo')",
    )
    op.create_check_constraint(
        "ck_eligibility_checks_network_status",
        "eligibility_checks",
        "network_status IN ('in_network', 'out_of_network')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_eligibility_checks_network_status", "eligibility_checks", type_="check"
    )
    op.drop_constraint("ck_eligibility_checks_plan_type", "eligibility_checks", type_="check")
    for col in (
        "ortho_lifetime_max_used",
        "ortho_lifetime_max",
        "deductible_waived_orthodontic",
        "deductible_waived_preventive",
        "deductible_waived_diagnostic",
        "coinsurance_by_code",
        "network_status",
        "plan_type",
    ):
        op.drop_column("eligibility_checks", col)
```

- [ ] **Step 2: Apply and round-trip the migration**

Run: `cd apps/api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/api/alembic/versions/0029_eligibility_copay_fields.py
git commit -m "feat(6): eligibility_checks copay fields migration"
```

### Task 2.2: Model + dataclass — add the new fields

**Files:**
- Modify: `apps/api/app/models/eligibility_check.py`
- Modify: `apps/api/app/services/eligibility/base.py` (the `EligibilityResult` dataclass)

- [ ] **Step 1: Add columns to the model**

In `EligibilityCheck`, add (match the migration types):
```python
    plan_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ppo")
    network_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="in_network"
    )
    coinsurance_by_code: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    deductible_waived_diagnostic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    deductible_waived_preventive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    deductible_waived_orthodontic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    ortho_lifetime_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ortho_lifetime_max_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
```
(Ensure `Boolean`, `Integer`, `String` and `JSONB` are imported at the top of the file — add any that are missing.)

- [ ] **Step 2: Add fields to `EligibilityResult`**

In `apps/api/app/services/eligibility/base.py`, add to the `EligibilityResult` dataclass (after `frequency_limits`, keeping defaults last):
```python
    plan_type: str = "ppo"
    network_status: str = "in_network"
    coinsurance_by_code: dict[str, float] | None = None
    deductible_waived_diagnostic: bool = False
    deductible_waived_preventive: bool = True
    deductible_waived_orthodontic: bool = False
    ortho_lifetime_max: int | None = None
    ortho_lifetime_max_used: int | None = None
```

- [ ] **Step 3: Verify imports**

Run: `cd apps/api && uv run python -c "from app.models.eligibility_check import EligibilityCheck; from app.services.eligibility.base import EligibilityResult; EligibilityResult.__dataclass_fields__['coinsurance_by_code']"`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/models/eligibility_check.py apps/api/app/services/eligibility/base.py
git commit -m "feat(6): eligibility model + result dataclass copay fields"
```

### Task 2.3: Parser — per-CDT coinsurance map + category fallback + plan/network

**Files:**
- Modify: `apps/api/app/services/eligibility/parser.py`
- Test: `apps/api/tests/services/test_eligibility_parser.py`

The real-data finding (eligibility spec §3): coinsurance comes per CDT code under granular service-type codes; the description holds D-code lists. We parse `code == "A"` segments into `{cdt_code: patient_share}`, and derive a per-category fallback by averaging the per-code rates whose CDT code maps to that category.

- [ ] **Step 1: Write failing tests**

Add to `tests/services/test_eligibility_parser.py`:
```python
def test_parse_per_code_coinsurance_map():
    raw = {
        "benefitsInformation": [
            {"code": "1", "name": "Active Coverage"},
            {
                "code": "A", "name": "Co-Insurance", "benefitPercent": "0.20",
                "additionalInformation": [{"description": "D1110, D0120"}],
            },
            {
                "code": "A", "name": "Co-Insurance", "benefitPercent": "0.50",
                "additionalInformation": [{"description": "D2740"}],
            },
        ],
    }
    r = parse_stedi_response(raw)
    assert r.coinsurance_by_code == {"D1110": 0.20, "D0120": 0.20, "D2740": 0.50}


def test_per_category_fallback_derived_from_codes():
    raw = {
        "benefitsInformation": [
            {"code": "1"},
            {"code": "A", "benefitPercent": "0.00",
             "additionalInformation": [{"description": "D1110"}]},   # preventive
            {"code": "A", "benefitPercent": "0.20",
             "additionalInformation": [{"description": "D2140"}]},   # basic (n<5000)
            {"code": "A", "benefitPercent": "0.50",
             "additionalInformation": [{"description": "D5110"}]},   # major (5000<=n<8000)
        ],
    }
    r = parse_stedi_response(raw)
    assert r.coinsurance_preventive == 0.00
    assert r.coinsurance_basic == 0.20
    assert r.coinsurance_major == 0.50
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/services/test_eligibility_parser.py -k "per_code or fallback" -v`
Expected: FAIL (`coinsurance_by_code` is None / categories None).

- [ ] **Step 3: Implement the parsing**

Add a CDT→category helper and the `A`-segment loop to `parser.py`. Insert this module-level helper near the top:
```python
import re

_CDT_RE = re.compile(r"D\d{4}")


def _cdt_category(code: str) -> str:
    """ADA D-code range → coarse insurance category (matches cdt_codes.category)."""
    try:
        n = int(code[1:])
    except (ValueError, IndexError):
        return "other"
    if n < 1000:
        return "diagnostic"
    if n < 2000:
        return "preventive"
    if n < 5000:
        return "basic"        # restorative/endo/perio default; carrier overrides later
    if n < 8000:
        return "major"
    if n < 9000:
        return "ortho"
    return "other"
```

Inside `parse_stedi_response`, before building the result, collect the map (the `for b in benefits` loop already exists — add an `A` branch and post-loop derivation):
```python
    coinsurance_by_code: dict[str, float] = {}
    for b in benefits:
        if b.get("code") != "A":
            continue
        pct = b.get("benefitPercent")
        if pct is None:
            continue
        try:
            share = float(pct)
        except (TypeError, ValueError):
            continue
        for part in _info_parts(b):
            for code in _CDT_RE.findall(part):
                coinsurance_by_code[code] = share

    # Per-category fallback = average of the per-code rates in that category.
    _by_cat: dict[str, list[float]] = {}
    for code, share in coinsurance_by_code.items():
        _by_cat.setdefault(_cdt_category(code), []).append(share)

    def _cat_avg(cat: str) -> float | None:
        vals = _by_cat.get(cat)
        return round(sum(vals) / len(vals), 4) if vals else None
```

Then in the `EligibilityResult(...)` constructor, replace the four `coinsurance_* = None` lines with:
```python
        coinsurance_preventive=_cat_avg("preventive"),
        coinsurance_basic=_cat_avg("basic"),
        coinsurance_major=_cat_avg("major"),
        coinsurance_ortho=_cat_avg("ortho"),
        coinsurance_by_code=coinsurance_by_code or None,
```
Leave `plan_type`/`network_status` at their dataclass defaults for now (detection from the 271 is payer-specific and out of scope for the deterministic parser; the router defaults them and they can be overridden when a reliable 271 signal is identified — noted in the spec).

- [ ] **Step 4: Update the now-obsolete `test_coinsurance_is_not_summarized` test**

That test asserted the old behavior (categories stay None). Per CLAUDE.md, changing a test means flagging it: this test encodes the *old* contract that Module 6 intentionally replaces. Update it to assert the new behavior — that `_ACTIVE_FULL`'s `A` segments (which use prose descriptions like "Preventive services", not D-codes) yield an **empty** `coinsurance_by_code` (no D-codes to extract) while a D-code fixture populates it. Rename to `test_coinsurance_requires_dcodes_in_description`:
```python
def test_coinsurance_requires_dcodes_in_description():
    # _ACTIVE_FULL's 'A' segments describe categories in prose, no D-codes -> nothing extracted.
    r = parse_stedi_response(_ACTIVE_FULL)
    assert r.coinsurance_by_code is None
```

- [ ] **Step 5: Run all parser tests**

Run: `cd apps/api && uv run pytest tests/services/test_eligibility_parser.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/eligibility/parser.py apps/api/tests/services/test_eligibility_parser.py
git commit -m "feat(6): parse per-CDT coinsurance map + category fallback from 271"
```

### Task 2.4: Persist the new fields through the router + schema

**Files:**
- Modify: `apps/api/app/routers/eligibility.py` (`_apply_result`, `_row_to_schema`)
- Modify: `packages/shared-types/src/schemas/eligibility.ts` (add the new fields)

- [ ] **Step 1: Persist in `_apply_result`**

In `apps/api/app/routers/eligibility.py`, add to `_apply_result(row, result)`:
```python
    row.coinsurance_by_code = result.coinsurance_by_code
    row.plan_type = result.plan_type
    row.network_status = result.network_status
    row.deductible_waived_diagnostic = result.deductible_waived_diagnostic
    row.deductible_waived_preventive = result.deductible_waived_preventive
    row.deductible_waived_orthodontic = result.deductible_waived_orthodontic
    row.ortho_lifetime_max = result.ortho_lifetime_max
    row.ortho_lifetime_max_used = result.ortho_lifetime_max_used
```

- [ ] **Step 2: Expose in the read schema**

Add the fields to `EligibilityCheckSchema` in `packages/shared-types/src/schemas/eligibility.ts`:
```typescript
  planType: z.enum(["ppo", "premier", "medicaid", "indemnity", "dhmo"]),
  networkStatus: z.enum(["in_network", "out_of_network"]),
  coinsuranceByCode: z.record(z.string(), z.number()).nullable(),
  orthoLifetimeMax: z.number().int().nonnegative().nullable(),
  orthoLifetimeMaxUsed: z.number().int().nonnegative().nullable(),
```
Then in `_row_to_schema` in `eligibility.py`, add the matching kwargs:
```python
        planType=row.plan_type,  # type: ignore[arg-type]
        networkStatus=row.network_status,  # type: ignore[arg-type]
        coinsuranceByCode=row.coinsurance_by_code,
        orthoLifetimeMax=row.ortho_lifetime_max,  # type: ignore[arg-type]
        orthoLifetimeMaxUsed=row.ortho_lifetime_max_used,  # type: ignore[arg-type]
```

- [ ] **Step 3: Regenerate + run eligibility router tests**

Run: `pnpm --filter @molar/shared-types generate && cd apps/api && uv run pytest tests/routers/test_eligibility.py -v`
Expected: generation succeeds; tests PASS (update any `_row_to_schema` assertion fixtures that now need the new fields).

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/routers/eligibility.py packages/shared-types/src/schemas/eligibility.ts apps/api/app/schemas/generated.py
git commit -m "feat(6): persist + expose eligibility copay fields"
```

---

# PART 3 — Full CDT catalog seed (PR 3)

### Task 3.1: Migration — seed the full D-code catalog

**Files:**
- Create: `apps/api/alembic/versions/0030_full_cdt_catalog_seed.py`
- Create: `apps/api/app/data/cdt_catalog.py` (the code→(description, category) data, sourced from Open Dental's GPL seed)

- [ ] **Step 1: Assemble the catalog data module**

Create `apps/api/app/data/cdt_catalog.py` with the full list as `CDT_CATALOG: list[tuple[str, str, str]]` (code, description, category) where category ∈ the `cdt_codes` check set (`diagnostic/preventive/basic/major/ortho/other`). Source codes + nomenclature from Open Dental's GPL `procedurecode` seed (redistributable); map each D-code's range to a category with the same ranges as `_cdt_category` in Task 2.3. Keep `default_fee_cents` null (practices set fees via 3.6). This is data entry, not logic — include the real rows, not a placeholder list.

- [ ] **Step 2: Write the migration (idempotent upsert of codes not already seeded)**

```python
"""Seed the full ADA CDT catalog (codes + categories; fees stay null)

Revision ID: 0030
Revises: 0029
Create Date: 2026-06-16
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.data.cdt_catalog import CDT_CATALOG

revision: str = "0030"
down_revision: str | Sequence[str] | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    existing = {row[0] for row in conn.execute(sa.text("SELECT code FROM cdt_codes"))}
    rows = [
        {
            "id": uuid.uuid4(),
            "code": code,
            "description": desc,
            "category": cat,
            "default_fee_cents": None,
            "is_active": True,
        }
        for code, desc, cat in CDT_CATALOG
        if code not in existing
    ]
    if rows:
        meta = sa.MetaData()
        cdt = sa.Table("cdt_codes", meta, autoload_with=conn)
        op.bulk_insert(cdt, rows)


def downgrade() -> None:
    # Leave the catalog in place; the 20-code seed predates this migration and
    # other rows reference cdt_codes. No-op downgrade.
    pass
```

- [ ] **Step 3: Apply + verify the count grew**

Run: `cd apps/api && uv run alembic upgrade head && uv run python -c "
import asyncio; from sqlalchemy import text; from app.core.db import get_session_factory
async def main():
    async with get_session_factory()() as s:
        print((await s.execute(text('select count(*) from cdt_codes'))).scalar())
asyncio.run(main())"`
Expected: a count well above 20 (the full catalog size).

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/data/cdt_catalog.py apps/api/alembic/versions/0030_full_cdt_catalog_seed.py
git commit -m "feat(6): seed full CDT catalog with categories"
```

---

# PART 4 — Engine + Service + Endpoints + Frontend (PR 4)

Depends on Parts 1–3. The pure engine first (exhaustive TDD), then the I/O layer, endpoints, frontend, and the algorithm doc.

### Task 4.1: Engine dataclasses + enums

**Files:**
- Create: `apps/api/app/services/copay/__init__.py` (empty)
- Create: `apps/api/app/services/copay/models.py`

- [ ] **Step 1: Write the models module**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class InsuranceCategory(StrEnum):
    DIAGNOSTIC = "diagnostic"
    PREVENTIVE = "preventive"
    BASIC = "basic"
    MAJOR = "major"
    ORTHO = "ortho"
    OTHER = "other"


class PlanType(StrEnum):
    PPO = "ppo"
    PREMIER = "premier"
    MEDICAID = "medicaid"
    INDEMNITY = "indemnity"
    DHMO = "dhmo"


# Deductible is applied to these in order, so it lands where it costs the patient least.
CATEGORY_ORDER = ["preventive", "diagnostic", "basic", "major", "ortho", "other"]


@dataclass(frozen=True, kw_only=True)
class ProcedureInput:
    procedure_id: str
    cdt_code: str
    category: str
    provider_fee_cents: int
    allowed_amount_cents: int | None          # None -> fall back to provider_fee
    coinsurance_patient_share: float | None   # None -> needs manual entry
    not_covered: bool = False
    requires_prior_auth: bool = False
    frequency_limit_count: int | None = None
    frequency_used_count: int = 0


@dataclass(frozen=True, kw_only=True)
class EligibilitySnapshot:
    plan_type: PlanType
    network_status: str                        # 'in_network' | 'out_of_network'
    coverage_start_date: date | None
    deductible_remaining_cents: int
    deductible_waived_categories: frozenset[str]
    annual_max_remaining_cents: int | None     # None -> no annual cap returned
    ortho_lifetime_max_remaining_cents: int | None
    waiting_period_months_by_category: dict[str, int]
    has_secondary_insurance: bool = False


@dataclass
class ProcedureResult:
    procedure_id: str
    cdt_code: str
    category: str
    provider_fee_cents: int
    allowed_amount_cents: int
    write_off_cents: int
    deductible_applied_cents: int
    insurance_owes_cents: int
    patient_owes_cents: int
    needs_manual_entry: bool = False
    not_covered: bool = False
    is_frequency_exceeded: bool = False
    is_in_waiting_period: bool = False
    annual_max_cap_applied: bool = False


@dataclass
class PatientResponsibilityBreakdown:
    service_date: date
    plan_type: PlanType
    line_items: list[ProcedureResult] = field(default_factory=list)
    total_provider_fee_cents: int = 0
    total_write_off_cents: int = 0
    total_insurance_owes_cents: int = 0
    total_patient_owes_cents: int = 0
    deductible_remaining_after_cents: int = 0
    annual_max_remaining_after_cents: int | None = None
    has_secondary_insurance: bool = False
```

- [ ] **Step 2: Verify import**

Run: `cd apps/api && uv run python -c "from app.services.copay.models import ProcedureInput, EligibilitySnapshot, PlanType"`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add apps/api/app/services/copay/__init__.py apps/api/app/services/copay/models.py
git commit -m "feat(6): copay engine dataclasses + enums"
```

### Task 4.2: Engine — standard pipeline (deductible + coinsurance), scenarios 1–3, 7

**Files:**
- Create: `apps/api/app/services/copay/engine.py`
- Test: `apps/api/tests/services/test_copay_engine.py`

- [ ] **Step 1: Write failing tests (the deductible/coinsurance core + the accounting identity helper)**

```python
from __future__ import annotations

from datetime import date

from app.services.copay.engine import calculate_patient_responsibility
from app.services.copay.models import (
    EligibilitySnapshot,
    PlanType,
    ProcedureInput,
)

SVC = date(2026, 6, 16)


def _snap(**kw):
    base = dict(
        plan_type=PlanType.PPO,
        network_status="in_network",
        coverage_start_date=date(2020, 1, 1),
        deductible_remaining_cents=0,
        deductible_waived_categories=frozenset({"preventive", "diagnostic"}),
        annual_max_remaining_cents=200000,
        ortho_lifetime_max_remaining_cents=None,
        waiting_period_months_by_category={},
        has_secondary_insurance=False,
    )
    base.update(kw)
    return EligibilitySnapshot(**base)


def _assert_identity(result):
    for li in result.line_items:
        assert (
            li.write_off_cents + li.patient_owes_cents + li.insurance_owes_cents
            == li.provider_fee_cents
        ), li


def test_scenario2_basic_filling_fresh_deductible():
    # D2392 fee=200.00 allowed=180.00 deductible=50.00 coins patient=0.20
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2392", category="basic",
        provider_fee_cents=20000, allowed_amount_cents=18000,
        coinsurance_patient_share=0.20,
    )
    r = calculate_patient_responsibility(_snap(deductible_remaining_cents=5000), [proc], SVC)
    li = r.line_items[0]
    assert li.write_off_cents == 2000
    assert li.deductible_applied_cents == 5000
    assert li.insurance_owes_cents == 10400   # (18000-5000)*0.80
    assert li.patient_owes_cents == 7600      # 5000 + 13000*0.20
    _assert_identity(r)


def test_scenario3_deductible_met():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2392", category="basic",
        provider_fee_cents=20000, allowed_amount_cents=18000,
        coinsurance_patient_share=0.20,
    )
    r = calculate_patient_responsibility(_snap(deductible_remaining_cents=0), [proc], SVC)
    li = r.line_items[0]
    assert li.deductible_applied_cents == 0
    assert li.insurance_owes_cents == 14400
    assert li.patient_owes_cents == 3600
    _assert_identity(r)


def test_scenario1_preventive_zero_and_deductible_untouched():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D1110", category="preventive",
        provider_fee_cents=12000, allowed_amount_cents=12000,
        coinsurance_patient_share=0.00,
    )
    r = calculate_patient_responsibility(_snap(deductible_remaining_cents=5000), [proc], SVC)
    li = r.line_items[0]
    assert li.patient_owes_cents == 0
    assert li.deductible_applied_cents == 0
    assert r.deductible_remaining_after_cents == 5000
    _assert_identity(r)


def test_scenario7_deductible_splits_across_two_procedures():
    p1 = ProcedureInput(
        procedure_id="p1", cdt_code="D2391", category="basic",
        provider_fee_cents=3000, allowed_amount_cents=3000, coinsurance_patient_share=0.20,
    )
    p2 = ProcedureInput(
        procedure_id="p2", cdt_code="D2392", category="basic",
        provider_fee_cents=20000, allowed_amount_cents=20000, coinsurance_patient_share=0.20,
    )
    r = calculate_patient_responsibility(_snap(deductible_remaining_cents=5000), [p1, p2], SVC)
    by_id = {li.procedure_id: li for li in r.line_items}
    assert by_id["p1"].deductible_applied_cents == 3000
    assert by_id["p2"].deductible_applied_cents == 2000
    assert r.deductible_remaining_after_cents == 0
    _assert_identity(r)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/services/test_copay_engine.py -v`
Expected: FAIL (`engine` has no `calculate_patient_responsibility`).

- [ ] **Step 3: Implement the engine core**

```python
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta

from app.services.copay.models import (
    CATEGORY_ORDER,
    EligibilitySnapshot,
    PatientResponsibilityBreakdown,
    PlanType,
    ProcedureInput,
    ProcedureResult,
)


def _round_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _sort_key(proc: ProcedureInput) -> int:
    try:
        return CATEGORY_ORDER.index(proc.category)
    except ValueError:
        return len(CATEGORY_ORDER)


def calculate_patient_responsibility(
    snapshot: EligibilitySnapshot,
    procedures: list[ProcedureInput],
    service_date: date,
) -> PatientResponsibilityBreakdown:
    """Pure function. No I/O. Dispatches by plan type; OON is a branch in _standard."""
    if snapshot.plan_type == PlanType.MEDICAID:
        return _calculate_medicaid(snapshot, procedures, service_date)
    if snapshot.plan_type in (PlanType.PPO, PlanType.PREMIER, PlanType.INDEMNITY):
        return _calculate_standard(snapshot, procedures, service_date)
    return _calculate_unsupported(snapshot, procedures, service_date)


def _new_breakdown(
    snapshot: EligibilitySnapshot, service_date: date
) -> PatientResponsibilityBreakdown:
    return PatientResponsibilityBreakdown(
        service_date=service_date,
        plan_type=snapshot.plan_type,
        annual_max_remaining_after_cents=snapshot.annual_max_remaining_cents,
        has_secondary_insurance=snapshot.has_secondary_insurance,
    )


def _finalize(result: PatientResponsibilityBreakdown) -> PatientResponsibilityBreakdown:
    result.total_provider_fee_cents = sum(li.provider_fee_cents for li in result.line_items)
    result.total_write_off_cents = sum(li.write_off_cents for li in result.line_items)
    result.total_insurance_owes_cents = sum(li.insurance_owes_cents for li in result.line_items)
    result.total_patient_owes_cents = sum(li.patient_owes_cents for li in result.line_items)
    return result


def _calculate_standard(
    snapshot: EligibilitySnapshot,
    procedures: list[ProcedureInput],
    service_date: date,
) -> PatientResponsibilityBreakdown:
    result = _new_breakdown(snapshot, service_date)
    deductible_remaining = snapshot.deductible_remaining_cents
    annual_max_remaining = snapshot.annual_max_remaining_cents

    for proc in sorted(procedures, key=_sort_key):
        fee = proc.provider_fee_cents
        oon = snapshot.network_status == "out_of_network"
        allowed = proc.allowed_amount_cents if proc.allowed_amount_cents is not None else fee
        write_off = 0 if oon else max(0, fee - allowed)
        balance_bill = max(0, fee - allowed) if oon else 0

        li = ProcedureResult(
            procedure_id=proc.procedure_id, cdt_code=proc.cdt_code, category=proc.category,
            provider_fee_cents=fee, allowed_amount_cents=allowed,
            write_off_cents=write_off, deductible_applied_cents=0,
            insurance_owes_cents=0, patient_owes_cents=0,
        )

        # --- short-circuit gates: insurance pays 0, patient owes allowed (+ balance bill) ---
        if proc.not_covered:
            li.not_covered = True
            li.patient_owes_cents = allowed + balance_bill
            result.line_items.append(li)
            continue
        if _in_waiting_period(snapshot, proc, service_date):
            li.is_in_waiting_period = True
            li.patient_owes_cents = allowed + balance_bill
            result.line_items.append(li)
            continue
        if proc.frequency_limit_count is not None and (
            proc.frequency_used_count >= proc.frequency_limit_count
        ):
            li.is_frequency_exceeded = True
            li.patient_owes_cents = allowed + balance_bill
            result.line_items.append(li)
            continue
        if proc.coinsurance_patient_share is None:
            li.needs_manual_entry = True
            result.line_items.append(li)
            continue

        # --- deductible ---
        amount = allowed
        if proc.category not in snapshot.deductible_waived_categories:
            applied = min(deductible_remaining, amount)
            li.deductible_applied_cents = applied
            deductible_remaining -= applied
            amount -= applied

        # --- coinsurance (Decimal math; round once) ---
        patient_share = Decimal(str(proc.coinsurance_patient_share))
        gross_insurance = _round_cents(Decimal(amount) * (Decimal(1) - patient_share))
        patient_coins = amount - gross_insurance  # exact complement, no double-rounding

        # --- annual max cap ---
        overflow = 0
        if annual_max_remaining is not None:
            capped = min(gross_insurance, annual_max_remaining)
            if capped < gross_insurance:
                li.annual_max_cap_applied = True
            overflow = gross_insurance - capped
            annual_max_remaining -= capped
            gross_insurance = capped

        li.insurance_owes_cents = gross_insurance
        li.patient_owes_cents = li.deductible_applied_cents + patient_coins + overflow + balance_bill
        result.line_items.append(li)

    result.deductible_remaining_after_cents = deductible_remaining
    result.annual_max_remaining_after_cents = annual_max_remaining
    return _finalize(result)


def _in_waiting_period(
    snapshot: EligibilitySnapshot, proc: ProcedureInput, service_date: date
) -> bool:
    months = snapshot.waiting_period_months_by_category.get(proc.category, 0) or 0
    if months <= 0 or snapshot.coverage_start_date is None:
        return False
    clears = snapshot.coverage_start_date + relativedelta(months=months)
    return service_date < clears


def _calculate_medicaid(
    snapshot: EligibilitySnapshot,
    procedures: list[ProcedureInput],
    service_date: date,
) -> PatientResponsibilityBreakdown:
    result = _new_breakdown(snapshot, service_date)
    for proc in procedures:
        fee = proc.provider_fee_cents
        allowed = proc.allowed_amount_cents if proc.allowed_amount_cents is not None else fee
        li = ProcedureResult(
            procedure_id=proc.procedure_id, cdt_code=proc.cdt_code, category=proc.category,
            provider_fee_cents=fee, allowed_amount_cents=allowed,
            write_off_cents=0, deductible_applied_cents=0,
            insurance_owes_cents=0, patient_owes_cents=0,
        )
        if proc.not_covered:
            li.not_covered = True
            li.patient_owes_cents = allowed
            li.write_off_cents = fee - allowed
        else:
            li.insurance_owes_cents = allowed
            li.write_off_cents = fee - allowed
        result.line_items.append(li)
    result.deductible_remaining_after_cents = snapshot.deductible_remaining_cents
    return _finalize(result)


def _calculate_unsupported(
    snapshot: EligibilitySnapshot,
    procedures: list[ProcedureInput],
    service_date: date,
) -> PatientResponsibilityBreakdown:
    # DHMO / unknown plan types: every line flagged for manual entry (deferred slice).
    result = _new_breakdown(snapshot, service_date)
    for proc in procedures:
        fee = proc.provider_fee_cents
        allowed = proc.allowed_amount_cents if proc.allowed_amount_cents is not None else fee
        li = ProcedureResult(
            procedure_id=proc.procedure_id, cdt_code=proc.cdt_code, category=proc.category,
            provider_fee_cents=fee, allowed_amount_cents=allowed,
            write_off_cents=0, deductible_applied_cents=0,
            insurance_owes_cents=0, patient_owes_cents=0, needs_manual_entry=True,
        )
        result.line_items.append(li)
    return _finalize(result)
```

Confirm `python-dateutil` is already a dependency (the spec's waiting-period math uses `relativedelta`). Run: `cd apps/api && uv run python -c "import dateutil"` — if it fails, `uv add python-dateutil` and commit `pyproject.toml`/lock.

- [ ] **Step 4: Run the tests**

Run: `cd apps/api && uv run pytest tests/services/test_copay_engine.py -v`
Expected: all 4 scenario tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/copay/engine.py apps/api/tests/services/test_copay_engine.py
git commit -m "feat(6): copay engine standard pipeline (deductible + coinsurance)"
```

### Task 4.3: Engine — annual max, frequency, waiting period, not-covered, manual (scenarios 4,5,6,6b)

**Files:**
- Test: `apps/api/tests/services/test_copay_engine.py`

- [ ] **Step 1: Add failing tests**

```python
def test_scenario4_annual_max_exhausted_mid_visit():
    # major allowed=800.00 deductible met 50/50; annual_max_remaining=200.00
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2750", category="major",
        provider_fee_cents=80000, allowed_amount_cents=80000, coinsurance_patient_share=0.50,
    )
    r = calculate_patient_responsibility(
        _snap(deductible_remaining_cents=0, annual_max_remaining_cents=20000), [proc], SVC
    )
    li = r.line_items[0]
    assert li.annual_max_cap_applied is True
    assert li.insurance_owes_cents == 20000
    assert li.patient_owes_cents == 60000     # 40000 coinsurance + 20000 overflow
    _assert_identity(r)


def test_scenario5_frequency_exceeded():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D1110", category="preventive",
        provider_fee_cents=12000, allowed_amount_cents=12000, coinsurance_patient_share=0.00,
        frequency_limit_count=2, frequency_used_count=2,
    )
    r = calculate_patient_responsibility(_snap(), [proc], SVC)
    li = r.line_items[0]
    assert li.is_frequency_exceeded is True
    assert li.insurance_owes_cents == 0
    assert li.patient_owes_cents == 12000
    _assert_identity(r)


def test_scenario6_waiting_period_blocks_coverage():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2750", category="major",
        provider_fee_cents=80000, allowed_amount_cents=80000, coinsurance_patient_share=0.50,
    )
    snap = _snap(
        coverage_start_date=date(2026, 3, 16),  # 3 months before SVC
        waiting_period_months_by_category={"major": 12},
    )
    r = calculate_patient_responsibility(snap, [proc], SVC)
    li = r.line_items[0]
    assert li.is_in_waiting_period is True
    assert li.insurance_owes_cents == 0
    _assert_identity(r)


def test_scenario6b_waiting_period_zero_months_is_waived():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2750", category="major",
        provider_fee_cents=80000, allowed_amount_cents=80000, coinsurance_patient_share=0.50,
    )
    snap = _snap(
        coverage_start_date=date(2026, 3, 16),
        waiting_period_months_by_category={"major": 0},
    )
    r = calculate_patient_responsibility(snap, [proc], SVC)
    assert r.line_items[0].is_in_waiting_period is False
    assert r.line_items[0].insurance_owes_cents > 0


def test_unknown_coinsurance_flags_manual():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D9999", category="other",
        provider_fee_cents=10000, allowed_amount_cents=10000, coinsurance_patient_share=None,
    )
    r = calculate_patient_responsibility(_snap(), [proc], SVC)
    assert r.line_items[0].needs_manual_entry is True
```

- [ ] **Step 2: Run — they should already PASS** (the Task 4.2 implementation already covers these branches).

Run: `cd apps/api && uv run pytest tests/services/test_copay_engine.py -v`
Expected: all PASS. If any fail, fix `engine.py` (do not weaken the test).

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/services/test_copay_engine.py
git commit -m "test(6): engine annual-max/frequency/waiting/manual scenarios"
```

### Task 4.4: Engine — OON balance billing + Medicaid + secondary flag (scenarios 8,9,11,12,13)

**Files:**
- Test: `apps/api/tests/services/test_copay_engine.py`

- [ ] **Step 1: Add failing tests**

```python
def test_scenario12_oon_balance_billing():
    # fee=1400 UCR/allowed=900 major 50% deductible met -> write_off 0, ins 450, patient 950
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2750", category="major",
        provider_fee_cents=140000, allowed_amount_cents=90000, coinsurance_patient_share=0.50,
    )
    snap = _snap(network_status="out_of_network", deductible_remaining_cents=0)
    r = calculate_patient_responsibility(snap, [proc], SVC)
    li = r.line_items[0]
    assert li.write_off_cents == 0
    assert li.insurance_owes_cents == 45000
    assert li.patient_owes_cents == 95000     # 45000 coinsurance + 50000 balance bill
    _assert_identity(r)


def test_scenario8_medicaid_patient_zero():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D1110", category="preventive",
        provider_fee_cents=12000, allowed_amount_cents=8000, coinsurance_patient_share=None,
    )
    snap = _snap(plan_type=PlanType.MEDICAID)
    r = calculate_patient_responsibility(snap, [proc], SVC)
    li = r.line_items[0]
    assert li.patient_owes_cents == 0
    assert li.insurance_owes_cents == 8000
    assert li.write_off_cents == 4000
    _assert_identity(r)


def test_scenario9_medicaid_not_covered_implant():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D6010", category="major",
        provider_fee_cents=200000, allowed_amount_cents=200000,
        coinsurance_patient_share=None, not_covered=True,
    )
    snap = _snap(plan_type=PlanType.MEDICAID)
    r = calculate_patient_responsibility(snap, [proc], SVC)
    li = r.line_items[0]
    assert li.not_covered is True
    assert li.insurance_owes_cents == 0
    assert li.patient_owes_cents == 200000
    _assert_identity(r)


def test_scenario13_secondary_insurance_flagged():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2392", category="basic",
        provider_fee_cents=20000, allowed_amount_cents=20000, coinsurance_patient_share=0.20,
    )
    r = calculate_patient_responsibility(_snap(has_secondary_insurance=True), [proc], SVC)
    assert r.has_secondary_insurance is True
```

- [ ] **Step 2: Run**

Run: `cd apps/api && uv run pytest tests/services/test_copay_engine.py -v`
Expected: all PASS (the Task 4.2 implementation already handles OON, Medicaid, and the secondary flag).

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/services/test_copay_engine.py
git commit -m "test(6): engine OON, Medicaid, secondary-flag scenarios"
```

### Task 4.5: Edge cases (negative write-off clamp, annual-max exactly zero, totals)

**Files:**
- Test: `apps/api/tests/services/test_copay_engine.py`

- [ ] **Step 1: Add tests**

```python
def test_negative_write_off_clamped():
    # provider_fee < allowed -> write_off must not go negative
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2392", category="basic",
        provider_fee_cents=10000, allowed_amount_cents=18000, coinsurance_patient_share=0.20,
    )
    r = calculate_patient_responsibility(_snap(deductible_remaining_cents=0), [proc], SVC)
    assert r.line_items[0].write_off_cents == 0
    _assert_identity(r)


def test_annual_max_exactly_zero_pays_nothing():
    proc = ProcedureInput(
        procedure_id="p1", cdt_code="D2750", category="major",
        provider_fee_cents=80000, allowed_amount_cents=80000, coinsurance_patient_share=0.50,
    )
    r = calculate_patient_responsibility(
        _snap(deductible_remaining_cents=0, annual_max_remaining_cents=0), [proc], SVC
    )
    li = r.line_items[0]
    assert li.insurance_owes_cents == 0
    assert li.annual_max_cap_applied is True
    _assert_identity(r)


def test_totals_sum_line_items():
    p1 = ProcedureInput(
        procedure_id="p1", cdt_code="D1110", category="preventive",
        provider_fee_cents=12000, allowed_amount_cents=12000, coinsurance_patient_share=0.00,
    )
    p2 = ProcedureInput(
        procedure_id="p2", cdt_code="D2392", category="basic",
        provider_fee_cents=20000, allowed_amount_cents=18000, coinsurance_patient_share=0.20,
    )
    r = calculate_patient_responsibility(_snap(deductible_remaining_cents=5000), [p1, p2], SVC)
    assert r.total_provider_fee_cents == 32000
    assert (
        r.total_write_off_cents + r.total_patient_owes_cents + r.total_insurance_owes_cents
        == r.total_provider_fee_cents
    )
```

- [ ] **Step 2: Run**

Run: `cd apps/api && uv run pytest tests/services/test_copay_engine.py -v`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/services/test_copay_engine.py
git commit -m "test(6): engine edge cases (write-off clamp, zero annual max, totals)"
```

### Task 4.6: Migration + model — `copay_calculations`

**Files:**
- Create: `apps/api/alembic/versions/0031_copay_calculations.py`
- Create: `apps/api/app/models/copay_calculation.py`

- [ ] **Step 1: Write the migration**

```python
"""copay_calculations snapshot table

Revision ID: 0031
Revises: 0030
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0031"
down_revision: str | Sequence[str] | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "copay_calculations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("eligibility_check_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("plan_type", sa.String(20), nullable=False),
        sa.Column("total_provider_fee_cents", sa.Integer, nullable=False),
        sa.Column("total_write_off_cents", sa.Integer, nullable=False),
        sa.Column("total_insurance_owes_cents", sa.Integer, nullable=False),
        sa.Column("total_patient_owes_cents", sa.Integer, nullable=False),
        sa.Column("deductible_remaining_after_cents", sa.Integer, nullable=True),
        sa.Column("annual_max_remaining_after_cents", sa.Integer, nullable=True),
        sa.Column("override_patient_cents", sa.Integer, nullable=True),
        sa.Column("override_note", sa.Text, nullable=True),
        sa.Column("overridden_by", sa.String(255), nullable=True),
        sa.Column("line_items", postgresql.JSONB, nullable=False),
        sa.Column("idempotency_key", sa.Text, nullable=False),
        sa.Column("has_secondary_insurance", sa.Boolean, nullable=False, server_default="false"),
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
    )
    op.create_index(
        "ix_copay_calculations_appointment_id", "copay_calculations", ["appointment_id"]
    )
    op.create_index(
        "uq_copay_calculations_idempotency_key",
        "copay_calculations", ["idempotency_key"], unique=True,
    )


def downgrade() -> None:
    op.drop_table("copay_calculations")
```

- [ ] **Step 2: Write the model**

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin


class CopayCalculation(Base, PHIMixin):
    """Snapshot of one co-pay calculation run for an appointment (audit + override)."""

    __tablename__ = "copay_calculations"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    eligibility_check_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    plan_type: Mapped[str] = mapped_column(String(20), nullable=False)
    total_provider_fee_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    total_write_off_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    total_insurance_owes_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    total_patient_owes_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    deductible_remaining_after_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    annual_max_remaining_after_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    override_patient_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    override_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    overridden_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    line_items: Mapped[list] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    has_secondary_insurance: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    __table_args__ = (
        Index("ix_copay_calculations_appointment_id", "appointment_id"),
    )
```

- [ ] **Step 3: Apply + round-trip + import**

Run: `cd apps/api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run python -c "from app.models.copay_calculation import CopayCalculation"`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add apps/api/alembic/versions/0031_copay_calculations.py apps/api/app/models/copay_calculation.py
git commit -m "feat(6): copay_calculations snapshot table + model"
```

### Task 4.7: Zod schemas — copay estimate response + override request

**Files:**
- Modify: `packages/shared-types/src/schemas/copay.ts`

- [ ] **Step 1: Append the estimate schemas** (these go in the same `copay.ts` from Task 1.3, which already imports `z`, `UuidSchema`, and `CdtCategorySchema`)

```typescript
export const CopayLineItemSchema = z.object({
  procedureId: UuidSchema,
  cdtCode: z.string(),
  category: CdtCategorySchema,
  providerFeeCents: z.number().int(),
  allowedAmountCents: z.number().int(),
  writeOffCents: z.number().int(),
  deductibleAppliedCents: z.number().int(),
  insuranceOwesCents: z.number().int(),
  patientOwesCents: z.number().int(),
  needsManualEntry: z.boolean(),
  notCovered: z.boolean(),
  isFrequencyExceeded: z.boolean(),
  isInWaitingPeriod: z.boolean(),
  annualMaxCapApplied: z.boolean(),
});
export type CopayLineItem = z.infer<typeof CopayLineItemSchema>;

export const CopayEstimateSchema = z.object({
  id: UuidSchema,
  appointmentId: UuidSchema,
  eligibilityCheckId: UuidSchema.nullable(),
  calculatedAt: z.string().datetime(),
  planType: z.enum(["ppo", "premier", "medicaid", "indemnity", "dhmo"]),
  totalProviderFeeCents: z.number().int(),
  totalWriteOffCents: z.number().int(),
  totalInsuranceOwesCents: z.number().int(),
  totalPatientOwesCents: z.number().int(),
  deductibleRemainingAfterCents: z.number().int().nullable(),
  annualMaxRemainingAfterCents: z.number().int().nullable(),
  overridePatientCents: z.number().int().nullable(),
  overrideNote: z.string().nullable(),
  hasSecondaryInsurance: z.boolean(),
  lineItems: z.array(CopayLineItemSchema),
});
export type CopayEstimate = z.infer<typeof CopayEstimateSchema>;

export const OverrideCopaySchema = z.object({
  overridePatientCents: z.number().int().nonnegative().nullable(),
  overrideNote: z.string().optional(),
});
export type OverrideCopay = z.infer<typeof OverrideCopaySchema>;
```

- [ ] **Step 2: Generate + verify**

Run: `pnpm --filter @molar/shared-types generate && cd apps/api && uv run python -c "from app.schemas.generated import CopayEstimate, CopayLineItem, OverrideCopay"`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add packages/shared-types/src/schemas/copay.ts apps/api/app/schemas/generated.py
git commit -m "feat(6): copay estimate + override Zod schemas"
```

### Task 4.8: `CopayService` — assemble inputs, calculate, persist

**Files:**
- Create: `apps/api/app/services/copay/service.py`
- Test: `apps/api/tests/integration/test_copay_service.py`

The service is the only I/O layer. It: loads the appointment's procedures + latest verified eligibility check; resolves allowed amount (contracted row → billed fee), coinsurance (`coinsurance_by_code[code]` → per-category field → None), frequency `used_count` (count of completed `appointment_procedures` for the same patient + `procedure_code`, excluding this appointment); builds the snapshot + inputs; calls the engine; writes estimates onto the procedure rows and upserts a `copay_calculations` snapshot.

- [ ] **Step 1: Write the service**

```python
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment as AppointmentModel
from app.models.appointment_procedure import AppointmentProcedure as ProcedureModel
from app.models.appointment_procedure import CdtCode as CdtCodeModel
from app.models.contracted_fee_schedule import ContractedFeeSchedule as ContractedModel
from app.models.copay_calculation import CopayCalculation as CalcModel
from app.models.eligibility_check import EligibilityCheck as CheckModel
from app.models.patient_insurance import PatientInsurance as InsuranceModel
from app.services.copay.engine import calculate_patient_responsibility
from app.services.copay.models import (
    EligibilitySnapshot,
    PlanType,
    ProcedureInput,
)

_CATEGORY_COINSURANCE_FIELD = {
    "preventive": "coinsurance_preventive",
    "diagnostic": "coinsurance_preventive",  # diagnostic tracks preventive when not separately returned
    "basic": "coinsurance_basic",
    "major": "coinsurance_major",
    "ortho": "coinsurance_ortho",
}


class CopayCalculationError(Exception):
    """Raised when prerequisites are missing (no procedures / no verified eligibility)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _line_item_json(li) -> dict:
    """Serialize a ProcedureResult to the camelCase shape CopayLineItemSchema expects,
    so the stored JSONB round-trips straight into the API response."""
    return {
        "procedureId": li.procedure_id,
        "cdtCode": li.cdt_code,
        "category": li.category,
        "providerFeeCents": li.provider_fee_cents,
        "allowedAmountCents": li.allowed_amount_cents,
        "writeOffCents": li.write_off_cents,
        "deductibleAppliedCents": li.deductible_applied_cents,
        "insuranceOwesCents": li.insurance_owes_cents,
        "patientOwesCents": li.patient_owes_cents,
        "needsManualEntry": li.needs_manual_entry,
        "notCovered": li.not_covered,
        "isFrequencyExceeded": li.is_frequency_exceeded,
        "isInWaitingPeriod": li.is_in_waiting_period,
        "annualMaxCapApplied": li.annual_max_cap_applied,
    }


async def _latest_verified_check(
    session: AsyncSession, practice_id: uuid.UUID, patient_id: uuid.UUID
) -> CheckModel | None:
    return await session.scalar(
        select(CheckModel)
        .where(
            CheckModel.practice_id == practice_id,
            CheckModel.patient_id == patient_id,
            CheckModel.status == "verified",
            CheckModel.deleted_at.is_(None),
        )
        .order_by(CheckModel.created_at.desc())
    )


def _resolve_coinsurance(check: CheckModel, code: str, category: str) -> float | None:
    by_code = check.coinsurance_by_code or {}
    if code in by_code:
        return float(by_code[code])
    field = _CATEGORY_COINSURANCE_FIELD.get(category)
    if field is None:
        return None
    val = getattr(check, field)
    return float(val) if val is not None else None


def _waived_categories(check: CheckModel) -> frozenset[str]:
    waived = set()
    if check.deductible_waived_diagnostic:
        waived.add("diagnostic")
    if check.deductible_waived_preventive:
        waived.add("preventive")
    if check.deductible_waived_orthodontic:
        waived.add("ortho")
    return frozenset(waived)


def _waiting_period_map(check: CheckModel) -> dict[str, int]:
    out: dict[str, int] = {}
    if check.waiting_period_basic_months is not None:
        out["basic"] = check.waiting_period_basic_months
    if check.waiting_period_major_months is not None:
        out["major"] = check.waiting_period_major_months
    if check.waiting_period_ortho_months is not None:
        out["ortho"] = check.waiting_period_ortho_months
    return out


def _snapshot(check: CheckModel) -> EligibilitySnapshot:
    ded_total = check.deductible_individual or 0
    ded_met = check.deductible_individual_met or 0
    annual_remaining = check.annual_max_individual_remaining
    if annual_remaining is None and check.annual_max_individual is not None:
        annual_remaining = check.annual_max_individual - (check.annual_max_individual_used or 0)
    ortho_remaining = None
    if check.ortho_lifetime_max is not None:
        ortho_remaining = check.ortho_lifetime_max - (check.ortho_lifetime_max_used or 0)
    try:
        plan_type = PlanType(check.plan_type)
    except ValueError:
        plan_type = PlanType.PPO
    return EligibilitySnapshot(
        plan_type=plan_type,
        network_status=check.network_status,
        coverage_start_date=check.coverage_start_date,
        deductible_remaining_cents=max(0, ded_total - ded_met),
        deductible_waived_categories=_waived_categories(check),
        annual_max_remaining_cents=annual_remaining,
        ortho_lifetime_max_remaining_cents=ortho_remaining,
        waiting_period_months_by_category=_waiting_period_map(check),
        has_secondary_insurance=False,
    )


async def _frequency_used(
    session: AsyncSession,
    practice_id: uuid.UUID,
    patient_id: uuid.UUID,
    appointment_id: uuid.UUID,
    code: str,
) -> int:
    """Best-effort count from completed procedure history (claims history lands in M7).

    Counts this calendar year, excluding the current appointment."""
    year_start = date(date.today().year, 1, 1)
    rows = await session.scalars(
        select(ProcedureModel.id).where(
            ProcedureModel.practice_id == practice_id,
            ProcedureModel.patient_id == patient_id,
            ProcedureModel.appointment_id != appointment_id,
            ProcedureModel.procedure_code == code,
            ProcedureModel.deleted_at.is_(None),
            ProcedureModel.created_at >= year_start,
        )
    )
    return len(rows.all())


async def calculate_for_appointment(
    session: AsyncSession,
    practice_id: uuid.UUID,
    appointment_id: uuid.UUID,
    user_sub: str | None,
) -> CalcModel:
    appt = await session.scalar(
        select(AppointmentModel).where(
            AppointmentModel.id == appointment_id,
            AppointmentModel.practice_id == practice_id,
            AppointmentModel.deleted_at.is_(None),
        )
    )
    if appt is None or appt.patient_id is None:
        raise CopayCalculationError("APPOINTMENT_NOT_FOUND", "Appointment not found")

    procs = (
        await session.scalars(
            select(ProcedureModel).where(
                ProcedureModel.appointment_id == appointment_id,
                ProcedureModel.deleted_at.is_(None),
            )
        )
    ).all()
    if not procs:
        raise CopayCalculationError("NO_PROCEDURES", "Appointment has no procedures to estimate")

    check = await _latest_verified_check(session, practice_id, appt.patient_id)
    if check is None:
        raise CopayCalculationError(
            "NO_ELIGIBILITY", "No verified eligibility check for this patient"
        )

    # payer for the contracted-fee lookup
    payer_id = check.payer_id_used

    # category per procedure (from cdt_codes when linked, else range-derived 'other')
    cdt_ids = [p.cdt_code_id for p in procs if p.cdt_code_id is not None]
    cdt_by_id: dict[uuid.UUID, CdtCodeModel] = {}
    if cdt_ids:
        for c in (await session.scalars(select(CdtCodeModel).where(CdtCodeModel.id.in_(cdt_ids)))).all():
            cdt_by_id[c.id] = c

    inputs: list[ProcedureInput] = []
    for p in procs:
        cdt = cdt_by_id.get(p.cdt_code_id) if p.cdt_code_id else None
        code = (cdt.code if cdt else p.procedure_code) or ""
        category = cdt.category if cdt else "other"
        contracted = await session.scalar(
            select(ContractedModel).where(
                ContractedModel.practice_id == practice_id,
                ContractedModel.payer_id == payer_id,
                ContractedModel.cdt_code_id == p.cdt_code_id,
                ContractedModel.deleted_at.is_(None),
            )
        ) if p.cdt_code_id else None
        freq_used = await _frequency_used(
            session, practice_id, appt.patient_id, appointment_id, code
        )
        inputs.append(
            ProcedureInput(
                procedure_id=str(p.id),
                cdt_code=code,
                category=category,
                provider_fee_cents=p.fee_cents,
                allowed_amount_cents=contracted.allowed_amount_cents if contracted else None,
                coinsurance_patient_share=_resolve_coinsurance(check, code, category),
                not_covered=bool(contracted.not_covered) if contracted else False,
                requires_prior_auth=bool(contracted.requires_prior_auth) if contracted else False,
                frequency_limit_count=(check.frequency_limits or {}).get(code, {}).get("count"),
                frequency_used_count=freq_used,
            )
        )

    service_date = (appt.scheduled_at.date() if appt.scheduled_at else date.today())
    breakdown = calculate_patient_responsibility(_snapshot(check), inputs, service_date)

    # write estimates back onto the procedure rows
    by_proc = {li.procedure_id: li for li in breakdown.line_items}
    for p in procs:
        li = by_proc.get(str(p.id))
        if li is not None:
            p.insurance_est_cents = li.insurance_owes_cents
            p.patient_est_cents = li.patient_owes_cents
            p.estimate_source = "eligibility"

    idem = hashlib.sha256(
        f"{appointment_id}|{check.id}|{sorted(str(p.id) for p in procs)}".encode()
    ).hexdigest()

    existing = await session.scalar(
        select(CalcModel).where(CalcModel.idempotency_key == idem)
    )
    calc = existing or CalcModel(id=uuid.uuid4(), idempotency_key=idem)
    calc.practice_id = practice_id
    calc.patient_id = appt.patient_id
    calc.appointment_id = appointment_id
    calc.eligibility_check_id = check.id
    calc.calculated_at = datetime.now(UTC)
    calc.plan_type = breakdown.plan_type.value
    calc.total_provider_fee_cents = breakdown.total_provider_fee_cents
    calc.total_write_off_cents = breakdown.total_write_off_cents
    calc.total_insurance_owes_cents = breakdown.total_insurance_owes_cents
    calc.total_patient_owes_cents = breakdown.total_patient_owes_cents
    calc.deductible_remaining_after_cents = breakdown.deductible_remaining_after_cents
    calc.annual_max_remaining_after_cents = breakdown.annual_max_remaining_after_cents
    calc.has_secondary_insurance = breakdown.has_secondary_insurance
    calc.line_items = [_line_item_json(li) for li in breakdown.line_items]
    calc.last_accessed_by = user_sub
    calc.last_accessed_at = datetime.now(UTC)
    if existing is None:
        session.add(calc)
    await session.commit()
    await session.refresh(calc)
    return calc
```

- [ ] **Step 2: Write integration tests** (`tests/integration/test_copay_service.py`)

Seed an appointment + a procedure (D2392, fee 20000) + a verified eligibility check (`coinsurance_by_code={"D2392":0.20}`, `deductible_individual=5000`, `deductible_individual_met=0`, `annual_max_individual_remaining=200000`, `plan_type='ppo'`, `network_status='in_network'`). Call `calculate_for_appointment` and assert the persisted snapshot + the procedure row write-back:
```python
import pytest
pytestmark = pytest.mark.integration

async def test_calculate_writes_estimates_and_snapshot(db_session, seed_copay_fixture):
    from app.services.copay.service import calculate_for_appointment
    ctx = seed_copay_fixture  # provides practice_id, appointment_id, procedure_id
    calc = await calculate_for_appointment(
        db_session, ctx.practice_id, ctx.appointment_id, user_sub="tester"
    )
    assert calc.total_patient_owes_cents == 7600   # 5000 deductible + 13000*0.20
    assert calc.total_insurance_owes_cents == 10400
    # procedure row write-back
    from app.models.appointment_procedure import AppointmentProcedure
    from sqlalchemy import select
    p = await db_session.scalar(
        select(AppointmentProcedure).where(AppointmentProcedure.id == ctx.procedure_id)
    )
    assert p.estimate_source == "eligibility"
    assert p.patient_est_cents == 7600


async def test_no_eligibility_raises(db_session, seed_appointment_no_eligibility):
    from app.services.copay.service import calculate_for_appointment, CopayCalculationError
    ctx = seed_appointment_no_eligibility
    with pytest.raises(CopayCalculationError) as exc:
        await calculate_for_appointment(db_session, ctx.practice_id, ctx.appointment_id, "t")
    assert exc.value.code == "NO_ELIGIBILITY"
```
Write the `seed_copay_fixture` / `seed_appointment_no_eligibility` fixtures in this test file using the same model-construction style as `tests/integration/conftest.py` (inspect it for how practice/patient/appointment are built). Confirm the actual `Appointment` timestamp attribute name (`scheduled_at` vs `start_time`) and adjust `_snapshot`/service `service_date` if it differs.

- [ ] **Step 3: Run (integration — ask first)**

Run: `cd apps/api && uv run pytest tests/integration/test_copay_service.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/services/copay/service.py apps/api/tests/integration/test_copay_service.py
git commit -m "feat(6): CopayService assembles inputs, calculates, persists"
```

### Task 4.9: Endpoints — POST/GET/PATCH copay-estimate

**Files:**
- Create: `apps/api/app/routers/copay.py`
- Modify: `apps/api/app/main.py` (import + include_router)
- Test: `apps/api/tests/integration/test_copay_endpoints.py`

- [ ] **Step 1: Write the router**

```python
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.core.db import get_session_factory
from app.core.features import require_feature
from app.models.copay_calculation import CopayCalculation as CalcModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import ApiError, CopayEstimate, Error, OverrideCopay
from app.services.copay.service import CopayCalculationError, calculate_for_appointment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/appointments/{appointment_id}", tags=["copay"])

_FEATURE = "copay_estimation"
_REQUIRES = "eligibility_verification"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True),
    )


def _to_schema(row: CalcModel) -> CopayEstimate:
    return CopayEstimate(
        id=row.id,
        appointmentId=row.appointment_id,
        eligibilityCheckId=row.eligibility_check_id,
        calculatedAt=row.calculated_at.replace(tzinfo=UTC),
        planType=row.plan_type,  # type: ignore[arg-type]
        totalProviderFeeCents=row.total_provider_fee_cents,
        totalWriteOffCents=row.total_write_off_cents,
        totalInsuranceOwesCents=row.total_insurance_owes_cents,
        totalPatientOwesCents=row.total_patient_owes_cents,
        deductibleRemainingAfterCents=row.deductible_remaining_after_cents,  # type: ignore[arg-type]
        annualMaxRemainingAfterCents=row.annual_max_remaining_after_cents,  # type: ignore[arg-type]
        overridePatientCents=row.override_patient_cents,  # type: ignore[arg-type]
        overrideNote=row.override_note,
        hasSecondaryInsurance=row.has_secondary_insurance,
        lineItems=row.line_items,  # type: ignore[arg-type]
    )


async def _gate(session, practice_id: uuid.UUID) -> None:
    await require_feature(session, practice_id, _FEATURE)
    await require_feature(session, practice_id, _REQUIRES)


@router.post("/copay-estimate", status_code=201, response_model=CopayEstimate)
async def create_copay_estimate(appointment_id: uuid.UUID, request: Request) -> CopayEstimate:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", None)
    async with get_session_factory()() as session:
        await _gate(session, practice_id)
        try:
            calc = await calculate_for_appointment(session, practice_id, appointment_id, user_sub)
        except CopayCalculationError as exc:
            status = 404 if exc.code == "APPOINTMENT_NOT_FOUND" else 422
            raise _err(status, exc.code, exc.message) from exc
        return _to_schema(calc)


async def _latest(session, practice_id: uuid.UUID, appointment_id: uuid.UUID) -> CalcModel:
    row = await session.scalar(
        select(CalcModel)
        .where(
            CalcModel.appointment_id == appointment_id,
            CalcModel.practice_id == practice_id,
            CalcModel.deleted_at.is_(None),
        )
        .order_by(CalcModel.calculated_at.desc())
    )
    if row is None:
        raise _err(404, "COPAY_ESTIMATE_NOT_FOUND", "No estimate for this appointment")
    return row


@router.get("/copay-estimate", response_model=CopayEstimate)
async def get_copay_estimate(appointment_id: uuid.UUID, request: Request) -> CopayEstimate:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await _gate(session, practice_id)
        return _to_schema(await _latest(session, practice_id, appointment_id))


@router.patch("/copay-estimate", response_model=CopayEstimate)
async def override_copay_estimate(
    appointment_id: uuid.UUID, body: OverrideCopay, request: Request
) -> CopayEstimate:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", None)
    async with get_session_factory()() as session:
        await _gate(session, practice_id)
        row = await _latest(session, practice_id, appointment_id)
        row.override_patient_cents = body.override_patient_cents
        row.override_note = body.override_note
        row.overridden_by = user_sub
        row.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(row)
        return _to_schema(row)
```

- [ ] **Step 2: Wire into `main.py`** (`from app.routers import (..., copay, ...)` and `app.include_router(copay.router)`).

- [ ] **Step 3: Integration tests** (`tests/integration/test_copay_endpoints.py`) — reuse the seed fixture from Task 4.8. Cover: POST returns 201 with totals; GET returns the snapshot; PATCH sets the override; feature-gate 403 when `copay_estimation` is off; POST 422 when the appointment has no procedures. Use the auth/role helpers from `test_fee_schedule.py` and include an `Idempotency-Key` header on POST/PATCH.

- [ ] **Step 4: Run (integration — ask first)**

Run: `cd apps/api && uv run pytest tests/integration/test_copay_endpoints.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/routers/copay.py apps/api/app/main.py apps/api/tests/integration/test_copay_endpoints.py
git commit -m "feat(6): copay-estimate POST/GET/PATCH endpoints + tests"
```

### Task 4.10: Frontend — appointment estimate card

**Files:**
- Create: `apps/web/src/features/appointments/CopayEstimateCard.tsx`
- Modify: the appointment detail view to mount the card

- [ ] **Step 1: Find the appointment detail view + the procedures section (3.5)**

Run: `cd apps/web && grep -rl "ProceduresSection\|procedures" src/features/appointments src/ | head`
Expected: the appointment view + the 3.5 ProceduresSection. Mount the new card beside it. Reuse the existing API client + cents↔dollars helpers.

- [ ] **Step 2: Build the card**

Calls `GET /api/v1/appointments/{id}/copay-estimate` (shows the latest snapshot) with a "Calculate estimate" / "Recalculate" button that `POST`s. Render the per-line table (fee / write-off / insurance / patient), the visit totals, deductible & annual-max remaining-after, the manual-override editor (`PATCH`), and badges for `needsManualEntry`, `isFrequencyExceeded`, `isInWaitingPeriod`, `notCovered`. Always show the caption **"Estimate, not a guarantee of payment."** Gate the card's visibility on the `copay_estimation` feature flag the same way the eligibility card is gated (find that pattern in the chart/eligibility component).

- [ ] **Step 3: Typecheck + lint**

Run: `cd apps/web && pnpm typecheck && pnpm lint`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/features/appointments/CopayEstimateCard.tsx apps/web/src/<appointment-view-file>
git commit -m "feat(6): appointment co-pay estimate card"
```

### Task 4.11: Calculation-algorithm reference doc

**Files:**
- Create: `docs/billing/copay-calculation-algorithm.md`
- Modify: `apps/api/app/services/copay/engine.py` (module docstring links to the doc)

- [ ] **Step 1: Write the doc**

Document, with the worked numeric examples from `research/14`: the dispatch by plan type; the standard pipeline (allowed/write-off → gates → deductible → coinsurance → annual-max cap); the OON balance-bill branch; the Medicaid pipeline; the procedure-ordering rule (`preventive→diagnostic→basic→major→ortho`) and why it favors the patient; the deductible/annual-max running-state threading; the accounting identity `fee == write_off + patient_owes + insurance_owes`; the rounding rule (Decimal internally, round once per line); and the deferred alternate-benefit downgrade case (with the §5 research example, marked "not yet implemented"). Cross-reference each of the 14 engine test scenarios by name.

- [ ] **Step 2: Link from the engine**

Add to the top of `apps/api/app/services/copay/engine.py`:
```python
"""Pure co-pay calculation engine. Algorithm reference:
docs/billing/copay-calculation-algorithm.md. No I/O; all money integer cents."""
```

- [ ] **Step 3: Commit**

```bash
git add docs/billing/copay-calculation-algorithm.md apps/api/app/services/copay/engine.py
git commit -m "docs(6): co-pay calculation algorithm reference"
```

---

## Final verification (run before opening PR 4)

- [ ] **Backend unit + service tests pass**

Run: `cd apps/api && uv run pytest tests/services/test_copay_engine.py tests/services/test_eligibility_parser.py -v`
Expected: all PASS.

- [ ] **Integration tests pass (ask first)**

Run: `cd apps/api && uv run pytest tests/integration/test_copay_service.py tests/integration/test_copay_endpoints.py tests/integration/test_contracted_fees.py -v`
Expected: all PASS.

- [ ] **Lint/type the touched backend files**

Run: `cd apps/api && uv run ruff check app/services/copay app/routers/copay.py app/routers/contracted_fees.py && uv run mypy app/services/copay`
Expected: clean (match the repo's configured checks; fix anything they flag).

- [ ] **Frontend typecheck + lint**

Run: `cd apps/web && pnpm typecheck && pnpm lint`
Expected: clean.

- [ ] **Update the build order**

Mark Module 6 done in `docs/superpowers/specs/phase3-build-order.md` and tick the relevant backlog line in `longterm_build_plan.md`. Commit.
```

