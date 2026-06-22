# Module 7b — 835 ERA Ingest + Auto-Post Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an opted-in practice pull 835 ERAs from Stedi (as JSON), parse them, match each claim payment back to a claim by Patient Control Number, and auto-post the payment (paid/patient-responsibility/adjustments/denial) onto the `claims` row — surfaced in a Remittances worklist + an unmatched-payment queue, and on the existing claim panel.

**Architecture:** Mirror the eligibility/claims slice — a `RemittanceClient` ABC with a single `StediRemittanceClient` adapter (Stedi `Poll Transactions` → `835 ERA Report`, both JSON; no raw X12), a pure `parse_stedi_era` parser (Stedi JSON → domain `ERAPayment`), pure status-mapping/posting helpers, and an orchestration service called inline from a feature-gated FastAPI router. Payments post **onto the `claims` row** (claim-level); Module 8 owns the ledger. Money is integer cents end-to-end. No worker/queue (deferred). Ingest is idempotent via `UNIQUE(stedi_transaction_id)`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (async), Alembic, httpx, pytest; Zod→Pydantic schema generation (`pnpm generate`); Next.js 15 + React Query + Tailwind frontend.

**Spec:** `docs/superpowers/specs/2026-06-22-module-7b-era-ingest-design.md`

**Conventions to follow (verified in codebase):**
- Models: `app/models/base.py` `Base` + `PHIMixin` (gives `id`, `created_at`, `updated_at`, `deleted_at`, `last_accessed_by`, `last_accessed_at`). Money = `Integer` cents. Register every model in `app/models/__init__.py`.
- Migrations: `apps/api/alembic/versions/NNNN_*.py`, `revision`/`down_revision` string vars. **Current head is `0032`; this plan adds `0033`** (`down_revision = "0032"`).
- Router pattern: `app/routers/claims.py` — `_require_practice_scope(request)` / `_require_write_role(request)` (from `app.routers.patients`), `require_feature(session, practice_id, feature, practice=...)` (from `app.core.features`), `get_session_factory()` context manager, `get_ssm_parameter(path)` (from `app.core.ssm`), `_err(status, code, message)` returning `ApiError(error=Error(...))`. Audit is middleware — no manual audit calls. Register router in `app/main.py` after `claims.router`.
- Stedi auth header: `{"Authorization": f"Key {api_key}"}` (same as `app/services/eligibility/stedi.py`). The feature gate `claims_submission` covers ERA too (ERA is the back half of the same capability).
- Tests: unit tests run by default (`pytest`); integration tests need Postgres and are marked `pytestmark = pytest.mark.integration` (run with `pytest -m integration`). Integration fixtures live in `apps/api/tests/integration/conftest.py` (`db_session`, `client`). HTTP is mocked with `httpx.MockTransport`.
- Zod schemas live in `packages/shared-types/src/schemas/*.ts`, barrel-exported from `packages/shared-types/src/index.ts`; `generated.py` (Pydantic) is built by `pnpm generate` and **never hand-edited**.
- Frontend types are **hand-written** per domain in `apps/web/lib/api/*.ts` (mirror `apps/web/lib/api/claims.ts`), not generated.

**Run commands (from `apps/api/`):**
- Unit test file: `pytest tests/services/test_<x>.py -v`
- Integration test file: `pytest -m integration tests/integration/test_<x>.py -v`
- Type check: `mypy app`  ·  Lint: `ruff check app tests`
- Migration: `alembic upgrade head`
- Schema regen (repo root): `pnpm generate`  ·  Frontend types: `pnpm -C apps/web typecheck`

---

## File structure (what each new file owns)

```
apps/api/app/services/era/
  __init__.py
  base.py        # ERAPayment, ClaimPayment, ClaimAdjustment, RemittanceClient (ABC), ERAFetchError
  parser.py      # parse_stedi_era(json) -> ERAPayment   (Stedi/CHC-Convert JSON -> domain)
  posting.py     # status_for_claim_payment(), claim_payment_fields()   (pure; status + cents)
  stedi.py       # StediRemittanceClient(RemittanceClient): poll_transactions(), fetch_era()
  service.py     # poll_and_post_eras(...) orchestration + resolve_unmatched_payment(...)
apps/api/app/models/era_remittance.py     # ERARemittance, UnmatchedERAPayment
apps/api/app/models/claim.py              # MODIFY: add payment columns
apps/api/alembic/versions/0033_era_ingest.py
apps/api/app/routers/era.py               # endpoints
apps/api/scripts/stedi_era_smoke.py       # manual sandbox pull (Stedi Test Payer); not in CI
packages/shared-types/src/schemas/era.ts  # Zod schemas -> generated.py
packages/shared-types/src/schemas/claims.ts  # MODIFY: add claim payment fields
apps/web/lib/api/era.ts                    # types + React Query hooks
apps/web/lib/api/claims.ts                 # MODIFY: add claim payment fields
apps/web/app/(app)/billing/remittances/page.tsx   # remittances + unmatched worklist
apps/web/components/scheduling/ClaimPanel.tsx      # MODIFY: payment readout (if present)
```

Tests:
```
apps/api/tests/services/test_era_parser.py
apps/api/tests/services/test_era_posting.py
apps/api/tests/services/test_stedi_remittance_client.py
apps/api/tests/services/test_claim_idempotency.py   # MODIFY: PCN <= 17
apps/api/tests/integration/test_era_service.py
apps/api/tests/integration/test_era_endpoints.py
```

---

## Task 1: Schema — claim payment columns + `era_remittances` + `unmatched_era_payments`

**Files:**
- Modify: `apps/api/app/models/claim.py`
- Create: `apps/api/app/models/era_remittance.py`
- Modify: `apps/api/app/models/__init__.py`
- Create: `apps/api/alembic/versions/0033_era_ingest.py`
- Modify: `apps/api/tests/integration/conftest.py` (truncate list)

- [ ] **Step 1: Add payment columns to the Claim model**

In `apps/api/app/models/claim.py`, add these mapped columns to the `Claim` class (after `submitted_at`, before `__table_args__`):

```python
    # --- Module 7b: ERA auto-post (claim-level) ---
    insurance_paid_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    patient_responsibility_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payer_claim_control_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    adjustments: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    denial_codes: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remittance_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
```

(`Integer`, `String`, `Text`, `DateTime`, `ARRAY`, `JSONB`, `UUID`, `Any`, `datetime`, `uuid` are already imported in this file.)

- [ ] **Step 2: Write the ERA models**

Create `apps/api/app/models/era_remittance.py`:

```python
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin


class ERARemittance(Base, PHIMixin):
    """One ingested 835 ERA (a Stedi remittance transaction).

    Holds PHI -> PHIMixin. `stedi_transaction_id` is the dedup key: re-polling never
    re-ingests or double-posts. `raw_response` keeps the full Stedi JSON so nothing
    is lost even though we post claim-level only.
    """

    __tablename__ = "era_remittances"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    stedi_transaction_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    trace_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payment_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    claim_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matched_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unmatched_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint("stedi_transaction_id", name="uq_era_remittances_stedi_txn"),
        Index("ix_era_remittances_practice_deleted", "practice_id", "deleted_at"),
    )


class UnmatchedERAPayment(Base, PHIMixin):
    """A claim payment (CLP) in an ERA with no matching claim — manual review queue.

    Never silently dropped. `resolved` is cleared by an operator who handled it
    manually (Phase 1 does not re-match to a chosen claim — that is deferred).
    """

    __tablename__ = "unmatched_era_payments"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    remittance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_control_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payer_claim_control_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    paid_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_claim_payment: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_unmatched_era_practice_resolved", "practice_id", "resolved"),
        Index("ix_unmatched_era_remittance", "remittance_id"),
    )
```

- [ ] **Step 3: Register the models**

In `apps/api/app/models/__init__.py`, add near the `Claim` import:

```python
from app.models.era_remittance import ERARemittance as ERARemittance
from app.models.era_remittance import UnmatchedERAPayment as UnmatchedERAPayment
```

- [ ] **Step 4: Write the migration**

Create `apps/api/alembic/versions/0033_era_ingest.py`:

```python
"""ERA ingest (Module 7b) — claim payment columns + era_remittances + unmatched_era_payments

Revision ID: 0033
Revises: 0032
Create Date: 2026-06-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0033"
down_revision: str | Sequence[str] | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Claim payment columns (auto-post target)
    op.add_column("claims", sa.Column("insurance_paid_cents", sa.Integer, nullable=True))
    op.add_column("claims", sa.Column("patient_responsibility_cents", sa.Integer, nullable=True))
    op.add_column("claims", sa.Column("payer_claim_control_number", sa.String(50), nullable=True))
    op.add_column("claims", sa.Column("adjustments", postgresql.JSONB, nullable=True))
    op.add_column("claims", sa.Column("denial_codes", postgresql.ARRAY(sa.Text), nullable=True))
    op.add_column("claims", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("claims", sa.Column("remittance_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.create_table(
        "era_remittances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stedi_transaction_id", sa.String(64), nullable=False),
        sa.Column("payer_name", sa.String(200), nullable=True),
        sa.Column("trace_number", sa.String(50), nullable=True),
        sa.Column("payment_cents", sa.Integer, nullable=True),
        sa.Column("payment_date", sa.Date, nullable=True),
        sa.Column("claim_count", sa.Integer, nullable=True),
        sa.Column("matched_count", sa.Integer, nullable=True),
        sa.Column("unmatched_count", sa.Integer, nullable=True),
        sa.Column("raw_response", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_by", sa.String(255), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_era_remittances_stedi_txn", "era_remittances", ["stedi_transaction_id"]
    )
    op.create_index(
        "ix_era_remittances_practice_deleted", "era_remittances", ["practice_id", "deleted_at"]
    )

    op.create_table(
        "unmatched_era_payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("remittance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_control_number", sa.String(50), nullable=True),
        sa.Column("payer_claim_control_number", sa.String(50), nullable=True),
        sa.Column("paid_cents", sa.Integer, nullable=True),
        sa.Column("raw_claim_payment", postgresql.JSONB, nullable=False),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_by", sa.String(255), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_unmatched_era_practice_resolved", "unmatched_era_payments", ["practice_id", "resolved"]
    )
    op.create_index("ix_unmatched_era_remittance", "unmatched_era_payments", ["remittance_id"])


def downgrade() -> None:
    op.drop_table("unmatched_era_payments")
    op.drop_table("era_remittances")
    for col in (
        "remittance_id", "paid_at", "denial_codes", "adjustments",
        "payer_claim_control_number", "patient_responsibility_cents", "insurance_paid_cents",
    ):
        op.drop_column("claims", col)
```

- [ ] **Step 5: Add the new tables to the integration truncate list**

In `apps/api/tests/integration/conftest.py`, add the two new tables to the top of the `_TRUNCATE_TABLES` tuple (before `"claims"`):

```python
_TRUNCATE_TABLES = (
    "unmatched_era_payments",
    "era_remittances",
    "claims",
    # ... existing entries unchanged ...
```

- [ ] **Step 6: Apply the migration**

Run (from `apps/api/`): `alembic upgrade head`
Expected: `Running upgrade 0032 -> 0033, ERA ingest (Module 7b)` and no errors.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/models/claim.py apps/api/app/models/era_remittance.py \
  apps/api/app/models/__init__.py apps/api/alembic/versions/0033_era_ingest.py \
  apps/api/tests/integration/conftest.py
git commit -m "feat(7b): ERA schema — claim payment columns + era_remittances + unmatched (0033)"
```

---

## Task 2: ERA domain types + `RemittanceClient` ABC

**Files:**
- Create: `apps/api/app/services/era/__init__.py` (empty)
- Create: `apps/api/app/services/era/base.py`

- [ ] **Step 1: Create the package init**

Create empty file `apps/api/app/services/era/__init__.py`.

- [ ] **Step 2: Write `base.py`**

Create `apps/api/app/services/era/base.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, kw_only=True)
class ClaimAdjustment:
    group: str          # CO | PR | OA | PI  (CAS group code)
    code: str           # CARC reason code (e.g. "45", "2")
    cents: int          # adjustment amount in cents


@dataclass(frozen=True, kw_only=True)
class ClaimPayment:
    patient_control_number: str          # CLP01 — matches claims.patient_control_number
    claim_status_code: str               # CLP02 — 1/2/3/19/20/21 processed, 4 denied, 22 reversal
    total_charge_cents: int              # CLP03
    paid_cents: int                      # CLP04
    patient_responsibility_cents: int    # CLP05
    payer_claim_control_number: str | None  # CLP07
    adjustments: tuple[ClaimAdjustment, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)  # the raw claim-payment JSON object


@dataclass(frozen=True, kw_only=True)
class ERAPayment:
    payer_name: str | None
    trace_number: str | None
    payment_cents: int | None
    payment_date: date | None
    claim_payments: tuple[ClaimPayment, ...]
    raw: dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class Transaction:
    transaction_id: str
    processed_at: datetime | None = None


class ERAFetchError(Exception):
    """Raised by a RemittanceClient on a transport/server failure.

    `retryable` -> timeout/5xx/transport: the poll can be safely re-run later
    (ingest is idempotent on the Stedi transaction id).
    """

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class RemittanceClient(ABC):
    @abstractmethod
    async def poll_transactions(self, since: datetime) -> list[Transaction]:
        """Return processed 835 transactions since `since` (filtered to ERAs)."""

    @abstractmethod
    async def fetch_era(self, transaction_id: str) -> dict[str, Any]:
        """Return the raw Stedi 835 ERA JSON for one transaction."""
```

- [ ] **Step 3: Sanity-import**

Run (from `apps/api/`): `python -c "from app.services.era.base import ERAPayment, ClaimPayment, ClaimAdjustment, RemittanceClient, ERAFetchError, Transaction; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/services/era/__init__.py apps/api/app/services/era/base.py
git commit -m "feat(7b): ERA domain types + RemittanceClient ABC"
```

---

## Task 3: PCN shortened to ≤ 17 chars (Stedi match-back fix)

**Why:** Stedi warns some payers truncate the PCN beyond 17 chars in ERAs, breaking match-back. 7a emits 20. No live claims exist yet (submission is test-key-blocked), so this is a clean contract change with no migration. **This is a deliberate behavior change — the test assertion is updated to encode the new contract, not to paper over a regression.**

**Files:**
- Modify: `apps/api/app/services/claims/idempotency.py`
- Modify: `apps/api/tests/services/test_claim_idempotency.py`
- Modify: `apps/api/app/services/claims/validator.py`

- [ ] **Step 1: Tighten the PCN test to ≤ 17**

In `apps/api/tests/services/test_claim_idempotency.py`, replace the body of `test_pcn_is_deterministic_and_within_stedi_limit` so the upper bound is 17:

```python
def test_pcn_is_deterministic_and_within_stedi_limit():
    cid = "0d2b9f3a-1c4e-4a8b-9f2a-123456789abc"
    pcn = generate_pcn(cid)
    assert pcn == generate_pcn(cid)
    assert 1 <= len(pcn) <= 17  # Stedi: payers may truncate beyond 17 chars
    # only X12-safe chars (no reserved delimiters ~ * : ^)
    assert all(c not in "~*:^" for c in pcn)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/services/test_claim_idempotency.py::test_pcn_is_deterministic_and_within_stedi_limit -v`
Expected: FAIL — `assert 20 <= 17` (current PCN is 20 chars).

- [ ] **Step 3: Shorten `generate_pcn`**

In `apps/api/app/services/claims/idempotency.py`, change the slice from `[:20]` to `[:17]` and update the docstring:

```python
def generate_pcn(claim_id: str) -> str:
    """Patient Control Number (CLM01).

    Deterministic from the claim's own UUID; <= 17 chars and X12-safe. Stedi warns
    that some payers truncate the PCN beyond 17 chars in 835 ERAs / 277CAs, which
    breaks match-back; keeping it <= 17 makes Module 7b's ERA matching reliable.
    """
    return claim_id.replace("-", "")[:17].upper()
```

- [ ] **Step 4: Tighten the validator threshold**

In `apps/api/app/services/claims/validator.py`, change the PCN length check from `> 20` to `> 17` and update the message:

```python
    if len(claim.patient_control_number) > 17:
        errors.append("Patient control number must be 17 characters or fewer")
```

(The existing `test_pcn_over_20_chars_is_error` uses a 21-char value, which is still `> 17`, so it stays green.)

- [ ] **Step 5: Run the affected tests**

Run: `pytest tests/services/test_claim_idempotency.py tests/services/test_claim_validator.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/claims/idempotency.py apps/api/app/services/claims/validator.py \
  apps/api/tests/services/test_claim_idempotency.py
git commit -m "fix(7b): shorten PCN to <=17 chars for reliable 835 ERA match-back"
```

---

## Task 4: Stedi ERA parser (`parse_stedi_era`)

**Files:**
- Create: `apps/api/app/services/era/parser.py`
- Test: `apps/api/tests/services/test_era_parser.py`

> **External-contract note:** Stedi returns the 835 in the Change-Healthcare "Convert" JSON
> shape: top level `meta` + `transactions[]`; each transaction carries payment/trace/date
> and an array of claim-payment objects each with `claimPaymentInfo`
> (`patientControlNumber`, `claimStatusCode`, `totalClaimChargeAmount`, `claimPaymentAmount`,
> `patientResponsibilityAmount`, `payerClaimControlNumber`), `claimAdjustments[]`
> (`claimAdjustmentGroupCode` + `adjustmentDetails[]` of `adjustmentReasonCode`/`adjustmentAmount`),
> and `serviceLines[]`. The **exact nesting path** to the claim-payment objects is isolated
> in `_iter_claim_payment_objs()` — the one place to adjust when a real recorded response is
> available at Staging Checkpoint 5. The fixtures below model that documented shape; the
> parser navigates defensively. Money strings → integer cents via `round(float(x) * 100)`.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/services/test_era_parser.py`:

```python
from datetime import date

from app.services.era.parser import parse_stedi_era

# Modeled on the documented Stedi/CHC-Convert 835 JSON shape (see parser external-contract note).
_PAID = {
    "meta": {"transactionId": "txn-1"},
    "transactions": [
        {
            "financialInformation": {"totalActualProviderPaymentAmount": "200.00"},
            "reassociationTraceNumber": {"checkOrEftTraceNumber": "EFT123"},
            "productionDate": "20260615",
            "payer": {"name": "DELTA DENTAL"},
            "detailInfo": [
                {
                    "paymentInfo": [
                        {
                            "claimPaymentInfo": {
                                "patientControlNumber": "ABC123",
                                "claimStatusCode": "1",
                                "totalClaimChargeAmount": "250.00",
                                "claimPaymentAmount": "200.00",
                                "patientResponsibilityAmount": "50.00",
                                "payerClaimControlNumber": "PAYER-9",
                            },
                            "claimAdjustments": [
                                {
                                    "claimAdjustmentGroupCode": "PR",
                                    "adjustmentDetails": [
                                        {"adjustmentReasonCode": "2", "adjustmentAmount": "50.00"}
                                    ],
                                }
                            ],
                        }
                    ]
                }
            ],
        }
    ],
}

_DENIED = {
    "meta": {"transactionId": "txn-2"},
    "transactions": [
        {
            "payer": {"name": "AETNA"},
            "detailInfo": [
                {
                    "paymentInfo": [
                        {
                            "claimPaymentInfo": {
                                "patientControlNumber": "DEN999",
                                "claimStatusCode": "4",
                                "totalClaimChargeAmount": "300.00",
                                "claimPaymentAmount": "0.00",
                                "patientResponsibilityAmount": "0.00",
                                "payerClaimControlNumber": "P-1",
                            },
                            "claimAdjustments": [
                                {
                                    "claimAdjustmentGroupCode": "CO",
                                    "adjustmentDetails": [
                                        {"adjustmentReasonCode": "29", "adjustmentAmount": "300.00"}
                                    ],
                                }
                            ],
                        }
                    ]
                }
            ],
        }
    ],
}


def test_parses_payer_trace_date_and_total():
    era = parse_stedi_era(_PAID)
    assert era.payer_name == "DELTA DENTAL"
    assert era.trace_number == "EFT123"
    assert era.payment_date == date(2026, 6, 15)
    assert era.payment_cents == 20000


def test_parses_claim_payment_to_cents():
    era = parse_stedi_era(_PAID)
    assert len(era.claim_payments) == 1
    cp = era.claim_payments[0]
    assert cp.patient_control_number == "ABC123"
    assert cp.claim_status_code == "1"
    assert cp.total_charge_cents == 25000
    assert cp.paid_cents == 20000
    assert cp.patient_responsibility_cents == 5000
    assert cp.payer_claim_control_number == "PAYER-9"


def test_parses_adjustments():
    cp = parse_stedi_era(_PAID).claim_payments[0]
    assert len(cp.adjustments) == 1
    adj = cp.adjustments[0]
    assert adj.group == "PR"
    assert adj.code == "2"
    assert adj.cents == 5000


def test_denied_claim_status_preserved():
    cp = parse_stedi_era(_DENIED).claim_payments[0]
    assert cp.claim_status_code == "4"
    assert cp.paid_cents == 0


def test_multi_claim_remittance():
    doc = {
        "transactions": [
            {
                "detailInfo": [
                    {
                        "paymentInfo": [
                            _PAID["transactions"][0]["detailInfo"][0]["paymentInfo"][0],
                            _DENIED["transactions"][0]["detailInfo"][0]["paymentInfo"][0],
                        ]
                    }
                ]
            }
        ]
    }
    era = parse_stedi_era(doc)
    assert len(era.claim_payments) == 2


def test_missing_fields_do_not_crash():
    era = parse_stedi_era({"transactions": [{"detailInfo": [{"paymentInfo": [{}]}]}]})
    assert len(era.claim_payments) == 1
    cp = era.claim_payments[0]
    assert cp.patient_control_number == ""
    assert cp.paid_cents == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/services/test_era_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.era.parser'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/app/services/era/parser.py`:

```python
from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from typing import Any

from app.services.era.base import ClaimAdjustment, ClaimPayment, ERAPayment


def _to_cents(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return 0


def _to_cents_opt(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return round(float(value) * 100)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if not value or not isinstance(value, str):
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _iter_claim_payment_objs(transaction: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield each claim-payment JSON object inside one 835 transaction.

    ISOLATED traversal — the single place to adjust if the real recorded Stedi
    response nests claim payments differently (verify at Staging Checkpoint 5).
    Documented shape: transaction.detailInfo[].paymentInfo[].
    """
    for detail in transaction.get("detailInfo") or []:
        for cp in detail.get("paymentInfo") or []:
            yield cp


def _parse_adjustments(cp_obj: dict[str, Any]) -> tuple[ClaimAdjustment, ...]:
    out: list[ClaimAdjustment] = []
    for group_obj in cp_obj.get("claimAdjustments") or []:
        group = str(group_obj.get("claimAdjustmentGroupCode") or "")
        for detail in group_obj.get("adjustmentDetails") or []:
            out.append(
                ClaimAdjustment(
                    group=group,
                    code=str(detail.get("adjustmentReasonCode") or ""),
                    cents=_to_cents(detail.get("adjustmentAmount")),
                )
            )
    return tuple(out)


def _parse_claim_payment(cp_obj: dict[str, Any]) -> ClaimPayment:
    info = cp_obj.get("claimPaymentInfo") or {}
    return ClaimPayment(
        patient_control_number=str(info.get("patientControlNumber") or ""),
        claim_status_code=str(info.get("claimStatusCode") or ""),
        total_charge_cents=_to_cents(info.get("totalClaimChargeAmount")),
        paid_cents=_to_cents(info.get("claimPaymentAmount")),
        patient_responsibility_cents=_to_cents(info.get("patientResponsibilityAmount")),
        payer_claim_control_number=info.get("payerClaimControlNumber") or None,
        adjustments=_parse_adjustments(cp_obj),
        raw=cp_obj,
    )


def parse_stedi_era(raw: dict[str, Any]) -> ERAPayment:
    """Parse a Stedi 835 ERA JSON document into a domain ERAPayment.

    Fail-soft on missing fields (a malformed claim yields zeros/empties rather than
    crashing the whole poll), but never silently drops a claim payment — every
    paymentInfo object becomes a ClaimPayment.
    """
    transactions = raw.get("transactions") or []
    txn = transactions[0] if transactions else {}

    fin = txn.get("financialInformation") or {}
    trn = txn.get("reassociationTraceNumber") or {}

    claim_payments = tuple(
        _parse_claim_payment(cp_obj)
        for t in transactions
        for cp_obj in _iter_claim_payment_objs(t)
    )

    return ERAPayment(
        payer_name=(txn.get("payer") or {}).get("name"),
        trace_number=trn.get("checkOrEftTraceNumber") or None,
        payment_cents=_to_cents_opt(fin.get("totalActualProviderPaymentAmount")),
        payment_date=_parse_date(txn.get("productionDate")),
        claim_payments=claim_payments,
        raw=raw,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/services/test_era_parser.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/era/parser.py apps/api/tests/services/test_era_parser.py
git commit -m "feat(7b): Stedi 835 ERA JSON parser -> domain ERAPayment"
```

---

## Task 5: Posting + status mapping (pure)

**Files:**
- Create: `apps/api/app/services/era/posting.py`
- Test: `apps/api/tests/services/test_era_posting.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/services/test_era_posting.py`:

```python
from app.services.era.base import ClaimAdjustment, ClaimPayment
from app.services.era.posting import claim_payment_fields, status_for_claim_payment


def _cp(status: str, pr_cents: int = 0, adjustments=()) -> ClaimPayment:
    return ClaimPayment(
        patient_control_number="ABC",
        claim_status_code=status,
        total_charge_cents=25000,
        paid_cents=20000,
        patient_responsibility_cents=pr_cents,
        payer_claim_control_number="P-1",
        adjustments=adjustments,
    )


def test_processed_with_no_patient_responsibility_is_paid():
    assert status_for_claim_payment(_cp("1", pr_cents=0)) == "paid"


def test_processed_with_patient_responsibility_is_partially_paid():
    assert status_for_claim_payment(_cp("1", pr_cents=5000)) == "partially_paid"


def test_forwarded_codes_are_processed():
    assert status_for_claim_payment(_cp("19", pr_cents=0)) == "paid"
    assert status_for_claim_payment(_cp("20", pr_cents=5000)) == "partially_paid"


def test_denied_code_is_denied():
    assert status_for_claim_payment(_cp("4")) == "denied"


def test_reversal_code_is_denied():
    assert status_for_claim_payment(_cp("22")) == "denied"


def test_zero_paid_but_processed_is_not_denied():
    # CLP02=1 with $0 paid is still an accepted claim — never infer 'denied' from amount.
    cp = ClaimPayment(
        patient_control_number="ABC", claim_status_code="1", total_charge_cents=25000,
        paid_cents=0, patient_responsibility_cents=0, payer_claim_control_number=None,
    )
    assert status_for_claim_payment(cp) == "paid"


def test_fields_map_cents_and_adjustments_and_denial_codes():
    cp = _cp(
        "4",
        adjustments=(
            ClaimAdjustment(group="PR", code="2", cents=5000),
            ClaimAdjustment(group="CO", code="45", cents=3000),
        ),
    )
    fields = claim_payment_fields(cp)
    assert fields["insurance_paid_cents"] == 20000
    assert fields["patient_responsibility_cents"] == 0
    assert fields["payer_claim_control_number"] == "P-1"
    assert fields["adjustments"] == [
        {"group": "PR", "code": "2", "cents": 5000},
        {"group": "CO", "code": "45", "cents": 3000},
    ]
    # denial_codes only populated on denied claims, from CARC reason codes
    assert fields["denial_codes"] == ["2", "45"]


def test_denial_codes_empty_when_not_denied():
    cp = _cp("1", adjustments=(ClaimAdjustment(group="CO", code="45", cents=3000),))
    assert claim_payment_fields(cp)["denial_codes"] is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/services/test_era_posting.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.era.posting'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/app/services/era/posting.py`:

```python
from __future__ import annotations

from typing import Any

from app.services.era.base import ClaimPayment

# X12 835 CLP02 (claim status). 1/2/3 processed; 19/20/21 processed-and-forwarded;
# 4 denied; 22 reversal. (research/15 incorrectly listed 19 as denied — it is not.)
_PROCESSED_CODES = {"1", "2", "3", "19", "20", "21"}
_DENIED_CODES = {"4", "22"}


def status_for_claim_payment(cp: ClaimPayment) -> str:
    """Map CLP02 + patient responsibility to a claim status.

    Never infers status from the paid amount: a $0 payment can be a valid accepted
    claim (Stedi guidance). 'partially_paid' means the patient still owes something.
    """
    if cp.claim_status_code in _DENIED_CODES:
        return "denied"
    if cp.claim_status_code in _PROCESSED_CODES:
        return "partially_paid" if cp.patient_responsibility_cents > 0 else "paid"
    # Unknown code: treat as denied-for-review rather than silently 'paid'.
    return "denied"


def claim_payment_fields(cp: ClaimPayment) -> dict[str, Any]:
    """The column values to post onto the claims row for this claim payment."""
    status = status_for_claim_payment(cp)
    adjustments = [{"group": a.group, "code": a.code, "cents": a.cents} for a in cp.adjustments]
    denial_codes = [a.code for a in cp.adjustments] if status == "denied" else None
    return {
        "insurance_paid_cents": cp.paid_cents,
        "patient_responsibility_cents": cp.patient_responsibility_cents,
        "payer_claim_control_number": cp.payer_claim_control_number,
        "adjustments": adjustments or None,
        "denial_codes": denial_codes,
        "status": status,
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/services/test_era_posting.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/era/posting.py apps/api/tests/services/test_era_posting.py
git commit -m "feat(7b): pure ERA status mapping + claim posting fields"
```

---

## Task 6: Stedi remittance client (poll + fetch)

**Files:**
- Create: `apps/api/app/services/era/stedi.py`
- Test: `apps/api/tests/services/test_stedi_remittance_client.py`

> **External-contract note:** endpoints per Stedi docs — Poll Transactions
> `GET https://core.us.stedi.com/2023-08-01/pollingTransactions` (cursor: `startDateTime`,
> `pageToken`/`nextPageToken`; items carry a `transactionId` and a transaction-set code) and
> 835 ERA Report `GET https://healthcare.us.stedi.com/2024-04-01/change/medicalnetwork/reports/v2/{transactionId}/835`.
> The exact host/version + the item field names used to detect "835" and read the id are
> isolated in `_is_835()` / `_transaction_id()` and must be confirmed against a recorded
> response at Staging Checkpoint 5. Unit tests mock httpx and do NOT depend on the URLs.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/services/test_stedi_remittance_client.py`:

```python
from datetime import UTC, datetime

import httpx
import pytest

from app.services.era.base import ERAFetchError
from app.services.era.stedi import StediRemittanceClient


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_poll_filters_to_835_and_returns_ids():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "items": [
                {"transactionId": "t-835-a", "transactionSetIdentifier": "835"},
                {"transactionId": "t-277", "transactionSetIdentifier": "277"},
                {"transactionId": "t-835-b", "transactionSetIdentifier": "835"},
            ],
            "nextPageToken": None,
        })

    client = StediRemittanceClient(api_key="k", client=_client(handler))
    txns = await client.poll_transactions(datetime(2026, 6, 1, tzinfo=UTC))
    assert [t.transaction_id for t in txns] == ["t-835-a", "t-835-b"]


@pytest.mark.asyncio
async def test_poll_paginates_via_next_page_token():
    pages = {
        None: {"items": [{"transactionId": "a", "transactionSetIdentifier": "835"}], "nextPageToken": "p2"},
        "p2": {"items": [{"transactionId": "b", "transactionSetIdentifier": "835"}], "nextPageToken": None},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.params.get("pageToken")
        return httpx.Response(200, json=pages[token])

    client = StediRemittanceClient(api_key="k", client=_client(handler))
    txns = await client.poll_transactions(datetime(2026, 6, 1, tzinfo=UTC))
    assert [t.transaction_id for t in txns] == ["a", "b"]


@pytest.mark.asyncio
async def test_fetch_era_returns_json_and_sends_key_auth():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        captured["path"] = request.url.path
        return httpx.Response(200, json={"transactions": [{"payer": {"name": "X"}}]})

    client = StediRemittanceClient(api_key="secret", client=_client(handler))
    body = await client.fetch_era("txn-1")
    assert body["transactions"][0]["payer"]["name"] == "X"
    assert captured["auth"] == "Key secret"
    assert "txn-1" in captured["path"]


@pytest.mark.asyncio
async def test_fetch_era_server_error_raises_retryable():
    client = StediRemittanceClient(api_key="k", client=_client(lambda r: httpx.Response(503, json={})))
    with pytest.raises(ERAFetchError) as exc:
        await client.fetch_era("txn-1")
    assert exc.value.retryable is True
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/services/test_stedi_remittance_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.era.stedi'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/app/services/era/stedi.py`:

```python
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from app.services.era.base import ERAFetchError, RemittanceClient, Transaction

logger = logging.getLogger(__name__)

# Confirm host/version against Stedi docs + the Staging Checkpoint 5 smoke run.
# Unit tests mock httpx and do not depend on these.
_POLL_URL = "https://core.us.stedi.com/2023-08-01/pollingTransactions"
_ERA_REPORT_URL = (
    "https://healthcare.us.stedi.com/2024-04-01/change/medicalnetwork/reports/v2/{txn}/835"
)
_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=15.0, pool=5.0)


def _is_835(item: dict[str, Any]) -> bool:
    for key in ("transactionSetIdentifier", "x12TransactionSetCode", "transactionType"):
        if str(item.get(key) or "") == "835":
            return True
    return False


def _transaction_id(item: dict[str, Any]) -> str | None:
    return item.get("transactionId") or item.get("id")


class StediRemittanceClient(RemittanceClient):
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._client = client  # injected in tests; created per-call in prod

    async def poll_transactions(self, since: datetime) -> list[Transaction]:
        headers = {"Authorization": f"Key {self._api_key}"}
        client = self._client or httpx.AsyncClient(timeout=_TIMEOUT)
        owns_client = self._client is None
        out: list[Transaction] = []
        page_token: str | None = None
        try:
            while True:
                params: dict[str, Any] = {"startDateTime": since.isoformat()}
                if page_token:
                    params["pageToken"] = page_token
                try:
                    resp = await client.get(_POLL_URL, params=params, headers=headers)
                except httpx.HTTPError as exc:
                    raise ERAFetchError(f"Stedi poll transport error: {exc}", retryable=True) from exc
                if resp.status_code >= 500:
                    raise ERAFetchError(f"Stedi poll server error {resp.status_code}", retryable=True)
                if resp.status_code >= 400:
                    raise ERAFetchError(
                        f"Stedi poll rejected {resp.status_code}: {resp.text[:200]}", retryable=False
                    )
                body = resp.json()
                for item in body.get("items") or []:
                    txn_id = _transaction_id(item)
                    if txn_id and _is_835(item):
                        out.append(Transaction(transaction_id=str(txn_id)))
                page_token = body.get("nextPageToken")
                if not page_token:
                    break
        finally:
            if owns_client:
                await client.aclose()
        return out

    async def fetch_era(self, transaction_id: str) -> dict[str, Any]:
        headers = {"Authorization": f"Key {self._api_key}"}
        url = _ERA_REPORT_URL.format(txn=transaction_id)
        client = self._client or httpx.AsyncClient(timeout=_TIMEOUT)
        owns_client = self._client is None
        try:
            try:
                resp = await client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                raise ERAFetchError(f"Stedi ERA transport error: {exc}", retryable=True) from exc
        finally:
            if owns_client:
                await client.aclose()
        if resp.status_code >= 500:
            raise ERAFetchError(f"Stedi ERA server error {resp.status_code}", retryable=True)
        if resp.status_code >= 400:
            raise ERAFetchError(
                f"Stedi ERA rejected {resp.status_code}: {resp.text[:200]}", retryable=False
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise ERAFetchError(f"Stedi returned non-JSON ERA body: {resp.text[:200]}", retryable=True) from exc
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/services/test_stedi_remittance_client.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/era/stedi.py apps/api/tests/services/test_stedi_remittance_client.py
git commit -m "feat(7b): Stedi remittance client — poll 835 transactions + fetch ERA JSON"
```

---

## Task 7: ERA orchestration service (poll → dedup → fetch → parse → match → post)

**Files:**
- Create: `apps/api/app/services/era/service.py`
- Test: `apps/api/tests/integration/test_era_service.py`

- [ ] **Step 1: Write the failing integration test**

Create `apps/api/tests/integration/test_era_service.py`. Reuse the claim-seeding approach from `tests/integration/test_claims_service.py` (verify model kwargs against the real models before running).

```python
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.claim import Claim
from app.models.era_remittance import ERARemittance, UnmatchedERAPayment
from app.services.era.base import RemittanceClient, Transaction
from app.services.era.service import poll_and_post_eras

pytestmark = pytest.mark.integration


def _era_doc(pcn: str, status: str = "1", paid: str = "200.00", pr: str = "50.00") -> dict:
    return {
        "transactions": [
            {
                "payer": {"name": "DELTA DENTAL"},
                "reassociationTraceNumber": {"checkOrEftTraceNumber": "EFT1"},
                "productionDate": "20260615",
                "financialInformation": {"totalActualProviderPaymentAmount": paid},
                "detailInfo": [
                    {
                        "paymentInfo": [
                            {
                                "claimPaymentInfo": {
                                    "patientControlNumber": pcn,
                                    "claimStatusCode": status,
                                    "totalClaimChargeAmount": "250.00",
                                    "claimPaymentAmount": paid,
                                    "patientResponsibilityAmount": pr,
                                    "payerClaimControlNumber": "P-1",
                                }
                            }
                        ]
                    }
                ],
            }
        ]
    }


class _FakeClient(RemittanceClient):
    def __init__(self, txn_to_doc: dict[str, dict]):
        self._docs = txn_to_doc
        self.fetches = 0

    async def poll_transactions(self, since):
        return [Transaction(transaction_id=t) for t in self._docs]

    async def fetch_era(self, transaction_id: str) -> dict:
        self.fetches += 1
        return self._docs[transaction_id]


async def _seed_claim(session: AsyncSession, pcn: str) -> Claim:
    claim = Claim(
        id=uuid.uuid4(),
        practice_id=uuid.uuid4(),
        appointment_id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        insurance_id=uuid.uuid4(),
        provider_id=uuid.uuid4(),
        idempotency_key=uuid.uuid4().hex,
        patient_control_number=pcn,
        payer_id="CDLA1",
        status="submitted",
        total_charge_cents=25000,
    )
    session.add(claim)
    await session.commit()
    return claim


@pytest.mark.asyncio
async def test_matches_and_posts_payment_onto_claim(db_session: AsyncSession):
    claim = await _seed_claim(db_session, "PCN12345")
    client = _FakeClient({"txn-1": _era_doc("PCN12345")})

    summary = await poll_and_post_eras(
        db_session, claim.practice_id, client=client,
        since=datetime.now(UTC) - timedelta(days=30), user_sub="sub-1",
    )
    assert summary["matched"] == 1
    assert summary["unmatched"] == 0

    await db_session.refresh(claim)
    assert claim.status == "partially_paid"
    assert claim.insurance_paid_cents == 20000
    assert claim.patient_responsibility_cents == 5000
    assert claim.paid_at is not None
    assert claim.remittance_id is not None


@pytest.mark.asyncio
async def test_dedup_skips_already_ingested_no_second_fetch(db_session: AsyncSession):
    claim = await _seed_claim(db_session, "PCN12345")
    client = _FakeClient({"txn-1": _era_doc("PCN12345")})
    practice_id = claim.practice_id
    since = datetime.now(UTC) - timedelta(days=30)

    await poll_and_post_eras(db_session, practice_id, client=client, since=since, user_sub="s")
    assert client.fetches == 1
    # second poll: same transaction id already ingested -> skipped, no new fetch
    summary = await poll_and_post_eras(db_session, practice_id, client=client, since=since, user_sub="s")
    assert client.fetches == 1
    assert summary["new"] == 0


@pytest.mark.asyncio
async def test_no_matching_claim_writes_unmatched(db_session: AsyncSession):
    practice_id = uuid.uuid4()
    client = _FakeClient({"txn-9": _era_doc("NOPE999")})
    summary = await poll_and_post_eras(
        db_session, practice_id, client=client,
        since=datetime.now(UTC) - timedelta(days=30), user_sub="s",
    )
    assert summary["matched"] == 0
    assert summary["unmatched"] == 1
    rows = (await db_session.scalars(
        select(UnmatchedERAPayment).where(UnmatchedERAPayment.practice_id == practice_id)
    )).all()
    assert len(rows) == 1
    assert rows[0].patient_control_number == "NOPE999"


@pytest.mark.asyncio
async def test_prefix_match_handles_truncated_pcn(db_session: AsyncSession):
    claim = await _seed_claim(db_session, "ABCDEFGHIJKLMNOPQ")  # 17 chars
    client = _FakeClient({"txn-1": _era_doc("ABCDEFGHIJKLM")})  # payer truncated to 13
    summary = await poll_and_post_eras(
        db_session, claim.practice_id, client=client,
        since=datetime.now(UTC) - timedelta(days=30), user_sub="s",
    )
    assert summary["matched"] == 1
    await db_session.refresh(claim)
    assert claim.status == "partially_paid"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest -m integration tests/integration/test_era_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.era.service'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/app/services/era/service.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.claim import Claim
from app.models.era_remittance import ERARemittance, UnmatchedERAPayment
from app.services.era.base import ClaimPayment, ERAPayment, RemittanceClient
from app.services.era.parser import parse_stedi_era
from app.services.era.posting import claim_payment_fields


async def _match_claim(
    session: AsyncSession, practice_id: uuid.UUID, pcn: str
) -> Claim | None:
    """Match by PCN: exact first, then prefix (payers may truncate the PCN)."""
    if not pcn:
        return None
    exact = await session.scalar(
        select(Claim).where(
            Claim.practice_id == practice_id,
            Claim.patient_control_number == pcn,
            Claim.deleted_at.is_(None),
        )
    )
    if exact is not None:
        return exact
    # Prefix: the stored claim PCN starts with the (possibly truncated) ERA value.
    return await session.scalar(
        select(Claim).where(
            Claim.practice_id == practice_id,
            Claim.patient_control_number.like(f"{pcn}%"),
            Claim.deleted_at.is_(None),
        )
    )


async def _post_to_claim(
    claim: Claim, cp: ClaimPayment, remittance_id: uuid.UUID, user_sub: str | None
) -> None:
    fields = claim_payment_fields(cp)
    claim.insurance_paid_cents = fields["insurance_paid_cents"]
    claim.patient_responsibility_cents = fields["patient_responsibility_cents"]
    claim.payer_claim_control_number = fields["payer_claim_control_number"]
    claim.adjustments = fields["adjustments"]
    claim.denial_codes = fields["denial_codes"]
    claim.status = fields["status"]
    claim.paid_at = datetime.now(UTC)
    claim.remittance_id = remittance_id
    claim.last_accessed_by = user_sub
    claim.last_accessed_at = datetime.now(UTC)


async def poll_and_post_eras(
    session: AsyncSession,
    practice_id: uuid.UUID,
    *,
    client: RemittanceClient,
    since: datetime,
    user_sub: str | None,
) -> dict[str, Any]:
    """Poll Stedi for 835 ERAs, dedup, fetch, parse, match by PCN, and auto-post.

    Idempotent: a transaction already in era_remittances is skipped (no re-fetch,
    no double-post). Safe to re-run after a crash.
    """
    transactions = await client.poll_transactions(since)
    polled = len(transactions)
    new = matched = unmatched = 0
    remittance_ids: list[str] = []

    for txn in transactions:
        already = await session.scalar(
            select(ERARemittance.id).where(
                ERARemittance.stedi_transaction_id == txn.transaction_id
            )
        )
        if already is not None:
            continue
        new += 1

        raw = await client.fetch_era(txn.transaction_id)
        era: ERAPayment = parse_stedi_era(raw)

        remittance = ERARemittance(
            id=uuid.uuid4(),
            practice_id=practice_id,
            stedi_transaction_id=txn.transaction_id,
            payer_name=era.payer_name,
            trace_number=era.trace_number,
            payment_cents=era.payment_cents,
            payment_date=era.payment_date,
            claim_count=len(era.claim_payments),
            matched_count=0,
            unmatched_count=0,
            raw_response=era.raw,
            last_accessed_by=user_sub,
            last_accessed_at=datetime.now(UTC),
        )
        session.add(remittance)

        r_matched = r_unmatched = 0
        for cp in era.claim_payments:
            claim = await _match_claim(session, practice_id, cp.patient_control_number)
            if claim is not None:
                await _post_to_claim(claim, cp, remittance.id, user_sub)
                r_matched += 1
            else:
                session.add(
                    UnmatchedERAPayment(
                        id=uuid.uuid4(),
                        practice_id=practice_id,
                        remittance_id=remittance.id,
                        patient_control_number=cp.patient_control_number or None,
                        payer_claim_control_number=cp.payer_claim_control_number,
                        paid_cents=cp.paid_cents,
                        raw_claim_payment=cp.raw,
                    )
                )
                r_unmatched += 1

        remittance.matched_count = r_matched
        remittance.unmatched_count = r_unmatched
        matched += r_matched
        unmatched += r_unmatched
        remittance_ids.append(str(remittance.id))
        await session.commit()

    return {
        "polled": polled,
        "new": new,
        "matched": matched,
        "unmatched": unmatched,
        "remittance_ids": remittance_ids,
    }


async def resolve_unmatched_payment(
    session: AsyncSession, practice_id: uuid.UUID, unmatched_id: uuid.UUID
) -> UnmatchedERAPayment | None:
    """Mark an unmatched payment resolved (operator handled it manually)."""
    row = await session.scalar(
        select(UnmatchedERAPayment).where(
            UnmatchedERAPayment.id == unmatched_id,
            UnmatchedERAPayment.practice_id == practice_id,
            UnmatchedERAPayment.deleted_at.is_(None),
        )
    )
    if row is None:
        return None
    row.resolved = True
    row.resolved_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(row)
    return row
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest -m integration tests/integration/test_era_service.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/era/service.py apps/api/tests/integration/test_era_service.py
git commit -m "feat(7b): ERA orchestration — poll/dedup/fetch/parse/match/post + resolve"
```

---

## Task 8: Zod schemas + regenerate Pydantic

**Files:**
- Create: `packages/shared-types/src/schemas/era.ts`
- Modify: `packages/shared-types/src/schemas/claims.ts` (claim payment fields)
- Modify: `packages/shared-types/src/index.ts` (export era.js)

- [ ] **Step 1: Add claim payment fields to the Claim Zod schema**

In `packages/shared-types/src/schemas/claims.ts`, add these fields to `ClaimSchema` (after `submissionErrors`, before `submittedAt`):

```typescript
  insurancePaidCents: z.number().int().nullable(),
  patientResponsibilityCents: z.number().int().nullable(),
  payerClaimControlNumber: z.string().nullable(),
  adjustments: z
    .array(z.object({ group: z.string(), code: z.string(), cents: z.number().int() }))
    .nullable(),
  denialCodes: z.array(z.string()).nullable(),
  paidAt: z.string().datetime().nullable(),
  remittanceId: UuidSchema.nullable(),
```

- [ ] **Step 2: Write the ERA Zod schemas**

Create `packages/shared-types/src/schemas/era.ts`:

```typescript
import { z } from "zod";
import { UuidSchema } from "./common.js";

export const ERARemittanceSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  stediTransactionId: z.string(),
  payerName: z.string().nullable(),
  traceNumber: z.string().nullable(),
  paymentCents: z.number().int().nullable(),
  paymentDate: z.string().nullable(),
  claimCount: z.number().int().nullable(),
  matchedCount: z.number().int().nullable(),
  unmatchedCount: z.number().int().nullable(),
  createdAt: z.string().datetime(),
});
export type ERARemittance = z.infer<typeof ERARemittanceSchema>;

export const UnmatchedERAPaymentSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  remittanceId: UuidSchema,
  patientControlNumber: z.string().nullable(),
  payerClaimControlNumber: z.string().nullable(),
  paidCents: z.number().int().nullable(),
  resolved: z.boolean(),
  resolvedAt: z.string().datetime().nullable(),
  createdAt: z.string().datetime(),
});
export type UnmatchedERAPayment = z.infer<typeof UnmatchedERAPaymentSchema>;

export const ERAPollSummarySchema = z.object({
  polled: z.number().int(),
  new: z.number().int(),
  matched: z.number().int(),
  unmatched: z.number().int(),
  remittanceIds: z.array(z.string()),
});
export type ERAPollSummary = z.infer<typeof ERAPollSummarySchema>;
```

- [ ] **Step 3: Export the new schema barrel**

In `packages/shared-types/src/index.ts`, add after the claims export:

```typescript
export * from "./schemas/era.js";
```

- [ ] **Step 4: Regenerate Pydantic**

Run (repo root): `pnpm generate`
Then verify the models exist:
Run: `grep -E "class (ERARemittance|UnmatchedERAPayment|ERAPollSummary)\b" apps/api/app/schemas/generated.py`
Expected: all three class names print. Also confirm `class Claim` now contains `insurance_paid_cents` (grep it).

- [ ] **Step 5: Commit**

```bash
git add packages/shared-types/src/schemas/era.ts packages/shared-types/src/schemas/claims.ts \
  packages/shared-types/src/index.ts apps/api/app/schemas/generated.py
git commit -m "feat(7b): Zod ERA schemas + claim payment fields -> regenerated Pydantic"
```

---

## Task 9: ERA router

**Files:**
- Create: `apps/api/app/routers/era.py`
- Modify: `apps/api/app/main.py` (register router)
- Modify: `apps/api/app/routers/claims.py` (`_to_schema` — add the new claim payment fields)

- [ ] **Step 1: Add the new claim fields to the claims `_to_schema`**

In `apps/api/app/routers/claims.py`, add to the `Claim(...)` construction in `_to_schema` (after `submissionErrors=...`):

```python
        insurancePaidCents=row.insurance_paid_cents,
        patientResponsibilityCents=row.patient_responsibility_cents,
        payerClaimControlNumber=row.payer_claim_control_number,
        adjustments=row.adjustments,
        denialCodes=row.denial_codes,
        paidAt=row.paid_at.replace(tzinfo=UTC) if row.paid_at else None,
        remittanceId=row.remittance_id,
```

- [ ] **Step 2: Write the ERA router**

Create `apps/api/app/routers/era.py`:

```python
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.core.db import get_session_factory
from app.core.features import require_feature
from app.core.ssm import get_ssm_parameter
from app.models.era_remittance import ERARemittance as ERARemittanceModel
from app.models.era_remittance import UnmatchedERAPayment as UnmatchedModel
from app.models.practice import Practice as PracticeModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import (
    ApiError,
    ERAPollSummary,
    ERARemittance,
    Error,
    UnmatchedERAPayment,
)
from app.services.era.service import poll_and_post_eras, resolve_unmatched_payment
from app.services.era.stedi import StediRemittanceClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["era"])

_FEATURE = "claims_submission"
_POLL_WINDOW_DAYS = 30


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True),
    )


def _remittance_schema(row: ERARemittanceModel) -> ERARemittance:
    return ERARemittance(
        id=row.id,
        practiceId=row.practice_id,
        stediTransactionId=row.stedi_transaction_id,
        payerName=row.payer_name,
        traceNumber=row.trace_number,
        paymentCents=row.payment_cents,
        paymentDate=row.payment_date.isoformat() if row.payment_date else None,
        claimCount=row.claim_count,
        matchedCount=row.matched_count,
        unmatchedCount=row.unmatched_count,
        createdAt=row.created_at.replace(tzinfo=UTC),
    )


def _unmatched_schema(row: UnmatchedModel) -> UnmatchedERAPayment:
    return UnmatchedERAPayment(
        id=row.id,
        practiceId=row.practice_id,
        remittanceId=row.remittance_id,
        patientControlNumber=row.patient_control_number,
        payerClaimControlNumber=row.payer_claim_control_number,
        paidCents=row.paid_cents,
        resolved=row.resolved,
        resolvedAt=row.resolved_at.replace(tzinfo=UTC) if row.resolved_at else None,
        createdAt=row.created_at.replace(tzinfo=UTC),
    )


@router.post("/era/poll", response_model=ERAPollSummary)
async def poll_eras(request: Request) -> ERAPollSummary:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", None)

    async with get_session_factory()() as session:
        practice = await session.scalar(select(PracticeModel).where(PracticeModel.id == practice_id))
        await require_feature(session, practice_id, _FEATURE, practice=practice)
        assert practice is not None

        if not practice.clearinghouse_api_key_ssm_path:
            raise _err(422, "MISSING_CLEARINGHOUSE", "Clearinghouse credentials are not configured")
        api_key = get_ssm_parameter(practice.clearinghouse_api_key_ssm_path)
        if not api_key:
            raise _err(422, "MISSING_CLEARINGHOUSE", "Clearinghouse API key unavailable")

        client = StediRemittanceClient(api_key=api_key)
        since = datetime.now(UTC) - timedelta(days=_POLL_WINDOW_DAYS)
        summary = await poll_and_post_eras(
            session, practice_id, client=client, since=since, user_sub=user_sub
        )
        return ERAPollSummary(**summary, remittanceIds=summary["remittance_ids"])


@router.get("/era/remittances", response_model=list[ERARemittance])
async def list_remittances(request: Request) -> list[ERARemittance]:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        rows = (
            await session.scalars(
                select(ERARemittanceModel)
                .where(
                    ERARemittanceModel.practice_id == practice_id,
                    ERARemittanceModel.deleted_at.is_(None),
                )
                .order_by(ERARemittanceModel.created_at.desc())
            )
        ).all()
        return [_remittance_schema(r) for r in rows]


@router.get("/era/unmatched", response_model=list[UnmatchedERAPayment])
async def list_unmatched(request: Request, resolved: bool = False) -> list[UnmatchedERAPayment]:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        rows = (
            await session.scalars(
                select(UnmatchedModel)
                .where(
                    UnmatchedModel.practice_id == practice_id,
                    UnmatchedModel.resolved == resolved,
                    UnmatchedModel.deleted_at.is_(None),
                )
                .order_by(UnmatchedModel.created_at.desc())
            )
        ).all()
        return [_unmatched_schema(r) for r in rows]


@router.post("/era/unmatched/{unmatched_id}/resolve", response_model=UnmatchedERAPayment)
async def resolve_unmatched(unmatched_id: uuid.UUID, request: Request) -> UnmatchedERAPayment:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        row = await resolve_unmatched_payment(session, practice_id, unmatched_id)
        if row is None:
            raise _err(404, "UNMATCHED_NOT_FOUND", "Unmatched payment not found")
        return _unmatched_schema(row)
```

> The `ERAPollSummary(**summary, remittanceIds=...)` call passes `polled/new/matched/unmatched`
> by keyword and supplies `remittanceIds` from `summary["remittance_ids"]`. If the generated
> field uses a different alias, construct it field-by-field instead. Confirm the generated
> `ERAPollSummary` field names after Task 8.

- [ ] **Step 3: Register the router**

In `apps/api/app/main.py`: add `era,` to the routers import block (alphabetically near `eligibility`) and add after `app.include_router(claims.router)`:

```python
    app.include_router(era.router)
```

- [ ] **Step 4: Sanity-import the app**

Run (from `apps/api/`): `python -c "import app.main; print('ok')"`
Expected: `ok` (no import errors).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/routers/era.py apps/api/app/main.py apps/api/app/routers/claims.py
git commit -m "feat(7b): ERA router (poll/remittances/unmatched/resolve) + claim payment fields"
```

---

## Task 10: ERA router integration tests

**Files:**
- Create: `apps/api/tests/integration/test_era_endpoints.py`

The router constructs `StediRemittanceClient` from the SSM key. Patch it with a fake so no
network happens. Mirror auth/seed helpers from `tests/integration/test_claims_endpoints.py`
(same `client` fixture, practice seeding, and feature-flag setup — verify those helpers'
names before running).

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/integration/test_era_endpoints.py`:

```python
import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.services.era.base import RemittanceClient, Transaction

pytestmark = pytest.mark.integration


class _FakeClient(RemittanceClient):
    def __init__(self, *args, **kwargs):
        pass

    async def poll_transactions(self, since):
        return [Transaction(transaction_id="txn-1")]

    async def fetch_era(self, transaction_id: str) -> dict:
        return {
            "transactions": [
                {
                    "payer": {"name": "DELTA"},
                    "detailInfo": [
                        {"paymentInfo": [{"claimPaymentInfo": {"patientControlNumber": "NOPE", "claimStatusCode": "1", "claimPaymentAmount": "0.00", "patientResponsibilityAmount": "0.00", "totalClaimChargeAmount": "0.00"}}]}
                    ],
                }
            ]
        }


@pytest.mark.asyncio
async def test_poll_requires_feature(client: AsyncClient):
    # A practice without claims_submission enabled -> 403.
    # (Use the test helper that seeds a practice with the feature OFF; see
    #  test_claims_endpoints.py for the equivalent claims-feature-off case.)
    resp = await client.post("/api/v1/era/poll", headers={"Idempotency-Key": uuid.uuid4().hex})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_poll_processes_and_returns_summary(client: AsyncClient):
    # Seed a practice with claims_submission ON + clearinghouse creds (mirror the
    # claims-endpoints happy-path seed). Then patch the Stedi client + SSM key.
    with patch("app.routers.era.StediRemittanceClient", _FakeClient), patch(
        "app.routers.era.get_ssm_parameter", return_value="fake-key"
    ):
        resp = await client.post(
            "/api/v1/era/poll", headers={"Idempotency-Key": uuid.uuid4().hex}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["new"] == 1
    assert body["unmatched"] == 1  # PCN "NOPE" matches no claim


@pytest.mark.asyncio
async def test_unmatched_list_and_resolve(client: AsyncClient):
    with patch("app.routers.era.StediRemittanceClient", _FakeClient), patch(
        "app.routers.era.get_ssm_parameter", return_value="fake-key"
    ):
        await client.post("/api/v1/era/poll", headers={"Idempotency-Key": uuid.uuid4().hex})

    listed = await client.get("/api/v1/era/unmatched?resolved=false")
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) >= 1

    target = items[0]["id"]
    resolved = await client.post(
        f"/api/v1/era/unmatched/{target}/resolve",
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert resolved.status_code == 200
    assert resolved.json()["resolved"] is True
```

> **Adapt the seeding/auth to this repo's harness.** `test_claims_endpoints.py` already
> solves "seed a practice with `claims_submission` on/off + write-role auth + clearinghouse
> creds" — copy its exact fixture usage (e.g. how it sets `practice.features` and the auth
> headers/patches). The assertions above (403 when off; summary + unmatched when on) are
> what matters.

- [ ] **Step 2: Run the tests to verify they fail, then pass**

Run: `pytest -m integration tests/integration/test_era_endpoints.py -v`
First expected: failures referencing missing seeding helpers — wire them per the note above.
After wiring: PASS (3 passed).

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/integration/test_era_endpoints.py
git commit -m "test(7b): ERA endpoint integration tests (403 / poll summary / unmatched resolve)"
```

---

## Task 11: Frontend — types, hooks, remittances page, claim panel readout

**Files:**
- Modify: `apps/web/lib/api/claims.ts` (claim payment fields)
- Create: `apps/web/lib/api/era.ts`
- Create: `apps/web/app/(app)/billing/remittances/page.tsx`
- Modify: `apps/web/components/scheduling/ClaimPanel.tsx` (payment readout — only if the file exists)

- [ ] **Step 1: Add claim payment fields to the frontend Claim type**

In `apps/web/lib/api/claims.ts`, add to the `Claim` interface (after `submissionErrors`):

```typescript
  insurancePaidCents: number | null;
  patientResponsibilityCents: number | null;
  payerClaimControlNumber: string | null;
  adjustments: Array<{ group: string; code: string; cents: number }> | null;
  denialCodes: string[] | null;
  paidAt: string | null;
  remittanceId: string | null;
```

- [ ] **Step 2: Write the ERA API module**

Create `apps/web/lib/api/era.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";

export interface ERARemittance {
  id: string;
  practiceId: string;
  stediTransactionId: string;
  payerName: string | null;
  traceNumber: string | null;
  paymentCents: number | null;
  paymentDate: string | null;
  claimCount: number | null;
  matchedCount: number | null;
  unmatchedCount: number | null;
  createdAt: string;
}

export interface UnmatchedERAPayment {
  id: string;
  practiceId: string;
  remittanceId: string;
  patientControlNumber: string | null;
  payerClaimControlNumber: string | null;
  paidCents: number | null;
  resolved: boolean;
  resolvedAt: string | null;
  createdAt: string;
}

export interface ERAPollSummary {
  polled: number;
  new: number;
  matched: number;
  unmatched: number;
  remittanceIds: string[];
}

export const eraKeys = {
  remittances: ["era", "remittances"] as const,
  unmatched: (resolved: boolean) => ["era", "unmatched", { resolved }] as const,
};

export function useRemittances() {
  return useQuery({
    queryKey: eraKeys.remittances,
    queryFn: () => apiClient.get<ERARemittance[]>("/api/v1/era/remittances"),
  });
}

export function useUnmatched(resolved = false) {
  return useQuery({
    queryKey: eraKeys.unmatched(resolved),
    queryFn: () =>
      apiClient.get<UnmatchedERAPayment[]>(`/api/v1/era/unmatched?resolved=${resolved}`),
  });
}

export function usePollEras() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiClient.post<ERAPollSummary>("/api/v1/era/poll", {}, { idempotencyKey: generateId() }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: eraKeys.remittances });
      void qc.invalidateQueries({ queryKey: ["era", "unmatched"] });
      void qc.invalidateQueries({ queryKey: ["claims"] });
    },
  });
}

export function useResolveUnmatched() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.post<UnmatchedERAPayment>(
        `/api/v1/era/unmatched/${id}/resolve`,
        {},
        { idempotencyKey: generateId() },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["era", "unmatched"] });
    },
  });
}
```

- [ ] **Step 3: Write the Remittances worklist page**

Create `apps/web/app/(app)/billing/remittances/page.tsx`:

```tsx
"use client";

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
import {
  usePollEras,
  useRemittances,
  useResolveUnmatched,
  useUnmatched,
} from "@/lib/api/era";

function centsToUsd(cents: number | null): string {
  return cents == null ? "—" : `$${(cents / 100).toFixed(2)}`;
}

export default function RemittancesPage() {
  const poll = usePollEras();
  const { data: remittances } = useRemittances();
  const { data: unmatched } = useUnmatched(false);
  const resolve = useResolveUnmatched();

  return (
    <div className="flex flex-col gap-6 p-6">
      <PageHeader
        title="Remittances (ERA)"
        description="Pull 835 ERAs from the clearinghouse and auto-post insurance payments."
      />

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => poll.mutate()}
          disabled={poll.isPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {poll.isPending ? "Polling…" : "Poll for ERAs"}
        </button>
        {poll.data && (
          <span className="text-sm text-muted-foreground">
            {poll.data.new} new · {poll.data.matched} matched · {poll.data.unmatched} unmatched
          </span>
        )}
      </div>

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold">Remittances</h2>
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Payer</TableHead>
                <TableHead>Trace</TableHead>
                <TableHead className="text-right">Payment</TableHead>
                <TableHead className="text-right">Claims</TableHead>
                <TableHead className="text-right">Matched</TableHead>
                <TableHead>Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(remittances ?? []).map((r) => (
                <TableRow key={r.id}>
                  <TableCell>{r.payerName ?? "—"}</TableCell>
                  <TableCell className="font-mono text-xs">{r.traceNumber ?? "—"}</TableCell>
                  <TableCell className="text-right">{centsToUsd(r.paymentCents)}</TableCell>
                  <TableCell className="text-right">{r.claimCount ?? 0}</TableCell>
                  <TableCell className="text-right">{r.matchedCount ?? 0}</TableCell>
                  <TableCell className="text-muted-foreground">{r.paymentDate ?? "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold">Unmatched payments</h2>
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Patient Control #</TableHead>
                <TableHead>Payer Claim #</TableHead>
                <TableHead className="text-right">Paid</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(unmatched ?? []).map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="font-mono text-xs">{u.patientControlNumber ?? "—"}</TableCell>
                  <TableCell className="font-mono text-xs">{u.payerClaimControlNumber ?? "—"}</TableCell>
                  <TableCell className="text-right">{centsToUsd(u.paidCents)}</TableCell>
                  <TableCell className="text-right">
                    <button
                      type="button"
                      onClick={() => resolve.mutate(u.id)}
                      disabled={resolve.isPending}
                      className="text-sm text-primary underline disabled:opacity-50"
                    >
                      Resolve
                    </button>
                  </TableCell>
                </TableRow>
              ))}
              {(unmatched ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="py-8 text-center text-sm text-muted-foreground">
                    <Badge variant="secondary">All clear</Badge>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Add a payment readout to the claim panel (if `ClaimPanel.tsx` exists)**

Open `apps/web/components/scheduling/ClaimPanel.tsx`. Where it renders a claim's status/result, add a payment block shown when `claim.status` is `paid`/`partially_paid`/`denied`. Use the existing styling/components in that file; the data is now on the `Claim` type:

```tsx
{(claim.status === "paid" ||
  claim.status === "partially_paid" ||
  claim.status === "denied") && (
  <div className="mt-2 space-y-1 text-sm">
    <div>Insurance paid: ${((claim.insurancePaidCents ?? 0) / 100).toFixed(2)}</div>
    <div>
      Patient responsibility: $
      {((claim.patientResponsibilityCents ?? 0) / 100).toFixed(2)}
    </div>
    {claim.denialCodes && claim.denialCodes.length > 0 && (
      <div className="text-destructive">Denial codes: {claim.denialCodes.join(", ")}</div>
    )}
  </div>
)}
```

If `ClaimPanel.tsx` does not exist or is structured differently, skip this step and note it — the readout is a nice-to-have; the Remittances page is the required surface.

- [ ] **Step 5: Typecheck the frontend**

Run (repo root): `pnpm -C apps/web typecheck`
Expected: no type errors.

- [ ] **Step 6: Commit**

```bash
git add apps/web/lib/api/era.ts apps/web/lib/api/claims.ts \
  "apps/web/app/(app)/billing/remittances/page.tsx" \
  apps/web/components/scheduling/ClaimPanel.tsx
git commit -m "feat(7b): frontend — ERA hooks, remittances + unmatched worklist, claim payment readout"
```

---

## Task 12: Manual sandbox smoke script (not in CI)

**Files:**
- Create: `apps/api/scripts/stedi_era_smoke.py`

Mirror `apps/api/scripts/stedi_claim_smoke.py` (env-driven, no CI). This is run by hand at
Staging Checkpoint 5 with a full-access key + the Stedi Test Payer.

- [ ] **Step 1: Write the script**

Create `apps/api/scripts/stedi_era_smoke.py`:

```python
"""Manual Stedi 835 ERA smoke test (NOT run in CI).

Polls Stedi for recent 835 transactions, fetches the first ERA, and prints the parsed
ERAPayment. Requires a full-access Stedi key (test-mode cannot pull ERAs) and, for a
test ERA, a claim previously submitted to the Stedi Test Payer.

Usage (from apps/api/):
    STEDI_API_KEY=... python scripts/stedi_era_smoke.py
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta

from app.services.era.parser import parse_stedi_era
from app.services.era.stedi import StediRemittanceClient


async def main() -> None:
    api_key = os.environ["STEDI_API_KEY"]
    client = StediRemittanceClient(api_key=api_key)
    since = datetime.now(UTC) - timedelta(days=30)

    txns = await client.poll_transactions(since)
    print(f"Found {len(txns)} 835 transaction(s)")
    if not txns:
        return

    raw = await client.fetch_era(txns[0].transaction_id)
    era = parse_stedi_era(raw)
    print(f"Payer: {era.payer_name}  Trace: {era.trace_number}  Total: {era.payment_cents}")
    for cp in era.claim_payments:
        print(
            f"  PCN={cp.patient_control_number} status={cp.claim_status_code} "
            f"paid={cp.paid_cents} pr={cp.patient_responsibility_cents}"
        )


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify it imports (do not run live)**

Run (from `apps/api/`): `python -c "import scripts.stedi_era_smoke; print('ok')"`
Expected: `ok` (do NOT execute the live poll in CI/dev without a real key).

- [ ] **Step 3: Commit**

```bash
git add apps/api/scripts/stedi_era_smoke.py
git commit -m "chore(7b): manual Stedi 835 ERA sandbox smoke script (not in CI)"
```

---

## Task 13: Full verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full unit suite**

Run (from `apps/api/`): `pytest -q`
Expected: all pass (includes the new era unit tests + the modified PCN/validator tests).

- [ ] **Step 2: Run the full integration suite**

Run (from `apps/api/`): `pytest -m integration -q`
Expected: all pass (includes `test_era_service.py` + `test_era_endpoints.py`).

- [ ] **Step 3: Type-check + lint the backend**

Run (from `apps/api/`): `mypy app` then `ruff check app tests`
Expected: clean. Fix any issues (do not silence with ignores unless a pattern already exists).

- [ ] **Step 4: Typecheck the frontend**

Run (repo root): `pnpm -C apps/web typecheck`
Expected: clean.

- [ ] **Step 5: Confirm migration round-trips**

Run (from `apps/api/`): `alembic downgrade -1 && alembic upgrade head`
Expected: `0033` downgrades and re-applies with no error.

- [ ] **Step 6: Final commit (if any lint/type fixups were made)**

```bash
git add -A
git commit -m "chore(7b): lint/type fixups + full-suite green"
```

---

## Self-review checklist (completed during authoring)

- **Spec coverage:** §3 architecture → Tasks 2,4,5,6,7,9; §4 data model → Task 1 + Task 8 (claim fields); §5 endpoints → Task 6; §6 flow + status mapping → Tasks 5,7; §2.6 PCN fix → Task 3; §7 API → Task 9; §8 frontend → Task 11; §9 testing → Tasks 4–7,10 + smoke Task 12; §10 deferred → intentionally NOT built (async/webhook, COB, claim_service_lines, ledger). All covered.
- **Money:** integer cents everywhere; dollar→cents only in `parser._to_cents`. ✓
- **CLP02 mapping:** corrected (4=denied, 19≠denied) in `posting.py` with a comment citing the research-doc error. ✓
- **Type consistency:** `ERAPayment`/`ClaimPayment`/`ClaimAdjustment`/`Transaction` defined in Task 2 and used unchanged in Tasks 4–7; `poll_and_post_eras(...)` signature identical in service (Task 7) and router (Task 9) and tests. `claim_payment_fields` keys match the columns added in Task 1. ✓
- **External-contract risks flagged:** Stedi ERA JSON nesting (`_iter_claim_payment_objs`), poll item shape (`_is_835`/`_transaction_id`), and endpoint URLs are isolated and marked verify-at-Checkpoint-5. ✓
