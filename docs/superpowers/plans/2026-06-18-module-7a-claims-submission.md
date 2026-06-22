# Module 7a — Claims Submission (837D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an opted-in practice build, validate, and synchronously submit an 837D dental claim for an appointment's procedures to Stedi, persisting the result and surfacing it in a claim panel + claims worklist.

**Architecture:** Mirror the established eligibility/copay slice — a `ClearinghouseClient` ABC with a single `StediClaimsClient` adapter using Stedi's **Dental Claims (837D) JSON** endpoint (Stedi translates JSON→X12 and returns a synchronous 277CA). A pure `DentalClaimInput` domain model + builder + validator + deterministic idempotency feed an orchestration service called inline from a feature-gated FastAPI router. Money is integer cents end-to-end; cents→dollar strings happen only at the Stedi edge. No worker/queue (deferred).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (async), Alembic, httpx, pytest; Zod→Pydantic schema generation (`pnpm generate`); Next.js 15 + React Query + Tailwind frontend.

**Spec:** `docs/superpowers/specs/2026-06-18-module-7a-claims-submission-design.md`

**Conventions to follow (verified in codebase):**
- Models: `app/models/base.py` `Base` + `PHIMixin` (gives `id`, `created_at`, `updated_at`, `deleted_at`, `last_accessed_by`, `last_accessed_at`). Money = `Integer` cents. Register every model in `app/models/__init__.py`.
- Migrations: `apps/api/alembic/versions/NNNN_*.py`, `revision`/`down_revision` string vars. Current head is `0031`; this plan adds **`0032`** (`down_revision = "0031"`).
- Router pattern: `app/routers/copay.py` — `_require_practice_scope(request)`, `_require_write_role(request)` (from `app.routers.patients`), `require_feature(session, practice_id, feature)` (from `app.core.features`), `get_session_factory()` context manager, `_err(status, code, message)` returning `ApiError(error=Error(...))`. Mutations get `Idempotency-Key` from `request.headers.get("Idempotency-Key")`. Audit is middleware — no manual audit calls. Register router in `app/main.py` after `copay.router`.
- Encryption: `app.core.encryption.encrypt(str)->bytes` / `decrypt(bytes)->str` (AES-256-GCM) for `practices.billing_tax_id_encrypted`.
- SSM: `app.core.ssm.get_ssm_parameter(path)->str|None` for the clearinghouse API key.
- Stedi auth header: `{"Authorization": f"Key {api_key}"}` (same as `app/services/eligibility/stedi.py`).
- Tests: unit tests run by default (`pytest`); integration tests need Postgres and are marked `@pytest.mark.integration` / `pytestmark = pytest.mark.integration` (run with `pytest -m integration`). Integration fixtures live in `apps/api/tests/integration/conftest.py` (`db_session`, `client`, `mut(headers)` for fresh idempotency keys, `_auth_patches`). HTTP is mocked with `httpx.MockTransport`.
- Frontend types are **hand-written** per domain in `apps/web/lib/api/*.ts` (mirror `apps/web/lib/api/copay.ts`), not generated. Backend Pydantic IS generated from Zod.

**Run commands (from `apps/api/`):**
- Unit test file: `pytest tests/services/test_<x>.py -v`
- Integration test file: `pytest -m integration tests/integration/test_<x>.py -v`
- Type check: `mypy app` (or the repo's configured command — check `pyproject.toml`)

---

## File structure (what each new file owns)

```
apps/api/app/services/claims/
  __init__.py
  base.py        # ClaimLine, DentalClaimInput, ClaimResult, ClearinghouseClient (ABC), ClaimSubmissionError
  idempotency.py # generate_claim_idempotency_key(), generate_pcn()
  validator.py   # ValidationResult, validate_claim()
  stedi.py       # StediClaimsClient(ClearinghouseClient): to_stedi_payload(), submit_dental_claim()
  builder.py     # build_claim_input(...) — ORM rows → DentalClaimInput
  service.py     # submit_claim_for_appointment(...) orchestration + ClaimSubmissionPrereqError
apps/api/app/models/claim.py                 # Claim ORM model
apps/api/alembic/versions/0032_claims.py     # claims table
apps/api/app/routers/claims.py               # endpoints
apps/api/scripts/stedi_claim_smoke.py        # manual sandbox smoke (not in CI)
packages/shared-types/src/schemas/claims.ts  # Zod schemas → generated.py
apps/web/lib/api/claims.ts                   # types + React Query hooks
apps/web/components/scheduling/ClaimPanel.tsx
apps/web/app/(app)/billing/claims/page.tsx   # worklist (replaces placeholder)
```

Tests:
```
apps/api/tests/services/test_claim_idempotency.py
apps/api/tests/services/test_claim_validator.py
apps/api/tests/services/test_claim_builder.py
apps/api/tests/services/test_stedi_claims_client.py
apps/api/tests/integration/test_claims_service.py
apps/api/tests/integration/test_claims_endpoints.py
```

---

## Task 1: `claims` table — model + migration

**Files:**
- Create: `apps/api/app/models/claim.py`
- Modify: `apps/api/app/models/__init__.py`
- Create: `apps/api/alembic/versions/0032_claims.py`

- [ ] **Step 1: Write the Claim model**

Create `apps/api/app/models/claim.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PHIMixin

# 7a writes: draft | submitted | clearinghouse_rejected | submission_failed
# Reserved for 7b / status-polling worker:
#   acknowledged | pending | paid | partially_paid | denied | appealing
_CLAIM_STATUSES = (
    "draft",
    "submitted",
    "clearinghouse_rejected",
    "submission_failed",
    "acknowledged",
    "pending",
    "paid",
    "partially_paid",
    "denied",
    "appealing",
)


class Claim(Base, PHIMixin):
    """One 837D dental claim for an appointment's procedures, billed to primary insurance.

    Holds PHI -> PHIMixin. Money is integer cents. The full status enum is defined
    in the check constraint so Module 7b and the status-polling worker never migrate;
    7a only writes draft/submitted/clearinghouse_rejected/submission_failed.
    """

    __tablename__ = "claims"

    practice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    appointment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    insurance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    submission_attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    patient_control_number: Mapped[str] = mapped_column(String(38), nullable=False)
    payer_id: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")

    total_charge_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    clearinghouse_claim_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    clearinghouse_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    submission_errors: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    raw_submission: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN " + str(_CLAIM_STATUSES),
            name="ck_claims_status",
        ),
        UniqueConstraint("idempotency_key", name="uq_claims_idempotency_key"),
        UniqueConstraint("patient_control_number", "payer_id", name="uq_claims_pcn_payer"),
        Index("ix_claims_appointment_id", "appointment_id"),
        Index("ix_claims_status", "status"),
        Index("ix_claims_patient_control_number", "patient_control_number"),
        Index("ix_claims_practice_deleted", "practice_id", "deleted_at"),
    )
```

- [ ] **Step 2: Register the model**

In `apps/api/app/models/__init__.py`, add (keep alphabetical-ish grouping near other models):

```python
from app.models.claim import Claim as Claim
```

- [ ] **Step 3: Write the migration**

Create `apps/api/alembic/versions/0032_claims.py`:

```python
"""claims table (Module 7a — 837D submission)

Revision ID: 0032
Revises: 0031
Create Date: 2026-06-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0032"
down_revision: str | Sequence[str] | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("practice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("appointment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("insurance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("submission_attempt", sa.Integer, nullable=False, server_default="1"),
        sa.Column("patient_control_number", sa.String(38), nullable=False),
        sa.Column("payer_id", sa.String(20), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("total_charge_cents", sa.Integer, nullable=False),
        sa.Column("clearinghouse_claim_id", sa.String(64), nullable=True),
        sa.Column("clearinghouse_status", sa.String(50), nullable=True),
        sa.Column("submission_errors", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("raw_submission", postgresql.JSONB, nullable=True),
        sa.Column("raw_response", postgresql.JSONB, nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_check_constraint(
        "ck_claims_status",
        "claims",
        "status IN ('draft', 'submitted', 'clearinghouse_rejected', 'submission_failed', "
        "'acknowledged', 'pending', 'paid', 'partially_paid', 'denied', 'appealing')",
    )
    op.create_unique_constraint("uq_claims_idempotency_key", "claims", ["idempotency_key"])
    op.create_unique_constraint(
        "uq_claims_pcn_payer", "claims", ["patient_control_number", "payer_id"]
    )
    op.create_index("ix_claims_appointment_id", "claims", ["appointment_id"])
    op.create_index("ix_claims_status", "claims", ["status"])
    op.create_index("ix_claims_patient_control_number", "claims", ["patient_control_number"])
    op.create_index("ix_claims_practice_deleted", "claims", ["practice_id", "deleted_at"])


def downgrade() -> None:
    op.drop_table("claims")
```

- [ ] **Step 4: Apply the migration to the local/test DB**

Run (from `apps/api/`): `alembic upgrade head`
Expected: `Running upgrade 0031 -> 0032, claims table (Module 7a — 837D submission)` and no errors.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/models/claim.py apps/api/app/models/__init__.py apps/api/alembic/versions/0032_claims.py
git commit -m "feat(7a): claims table — model + migration 0032"
```

---

## Task 2: Domain types + `ClearinghouseClient` ABC

**Files:**
- Create: `apps/api/app/services/claims/__init__.py` (empty)
- Create: `apps/api/app/services/claims/base.py`

- [ ] **Step 1: Create the package init**

Create empty file `apps/api/app/services/claims/__init__.py`.

- [ ] **Step 2: Write `base.py`**

Create `apps/api/app/services/claims/base.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True, kw_only=True)
class ClaimLine:
    procedure_id: str          # appointment_procedure.id -> lineItemControlNumber (835 correlation)
    cdt_code: str              # D####
    fee_cents: int
    tooth_number: str | None
    surface: str | None
    procedure_name: str


@dataclass(frozen=True, kw_only=True)
class DentalClaimInput:
    patient_control_number: str       # CLM01; <= 20 chars for Stedi JSON
    payer_id: str
    usage_indicator: str              # "T" (test) or "P" (production)
    # Billing provider (the practice)
    billing_npi: str
    billing_tax_id: str               # decrypted, digits only
    billing_taxonomy_code: str
    billing_org_name: str
    submitter_id: str
    # Rendering provider
    rendering_npi: str
    rendering_first_name: str
    rendering_last_name: str
    # Subscriber / insured
    subscriber_first_name: str
    subscriber_last_name: str
    subscriber_dob: date
    member_id: str
    group_number: str | None
    relationship_to_insured: str      # 'self' | 'spouse' | 'child' | 'other'
    # Patient (used when relationship != self; equals subscriber when self)
    patient_first_name: str
    patient_last_name: str
    patient_dob: date
    # Claim
    date_of_service: date
    lines: tuple[ClaimLine, ...]

    @property
    def total_charge_cents(self) -> int:
        return sum(line.fee_cents for line in self.lines)


@dataclass(frozen=True)
class ClaimResult:
    accepted: bool
    clearinghouse_claim_id: str | None
    clearinghouse_status: str | None
    errors: list[str]
    raw_request: dict[str, Any]
    raw_response: dict[str, Any]


class ClaimSubmissionError(Exception):
    """Raised by a clearinghouse client on a transport/server failure.

    `retryable` -> timeout/5xx/transport: the router marks the claim
    'submission_failed' and the same idempotency key may be retried safely.
    """

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class ClearinghouseClient(ABC):
    @abstractmethod
    async def submit_dental_claim(
        self, claim: DentalClaimInput, idempotency_key: str
    ) -> ClaimResult: ...
```

- [ ] **Step 3: Sanity-import to verify no syntax/type errors**

Run (from `apps/api/`): `python -c "from app.services.claims.base import DentalClaimInput, ClaimLine, ClaimResult, ClearinghouseClient, ClaimSubmissionError; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/services/claims/__init__.py apps/api/app/services/claims/base.py
git commit -m "feat(7a): claims domain types + ClearinghouseClient ABC"
```

---

## Task 3: Idempotency key + PCN generation

**Files:**
- Create: `apps/api/app/services/claims/idempotency.py`
- Test: `apps/api/tests/services/test_claim_idempotency.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/services/test_claim_idempotency.py`:

```python
from app.services.claims.idempotency import generate_claim_idempotency_key, generate_pcn


def test_idempotency_key_is_deterministic():
    a = generate_claim_idempotency_key("appt-1", "pat-1", "ins-1", 1)
    b = generate_claim_idempotency_key("appt-1", "pat-1", "ins-1", 1)
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_idempotency_key_changes_with_attempt():
    v1 = generate_claim_idempotency_key("appt-1", "pat-1", "ins-1", 1)
    v2 = generate_claim_idempotency_key("appt-1", "pat-1", "ins-1", 2)
    assert v1 != v2


def test_idempotency_key_changes_with_inputs():
    base = generate_claim_idempotency_key("appt-1", "pat-1", "ins-1", 1)
    assert generate_claim_idempotency_key("appt-2", "pat-1", "ins-1", 1) != base
    assert generate_claim_idempotency_key("appt-1", "pat-2", "ins-1", 1) != base


def test_pcn_is_deterministic_and_within_stedi_limit():
    cid = "0d2b9f3a-1c4e-4a8b-9f2a-123456789abc"
    pcn = generate_pcn(cid)
    assert pcn == generate_pcn(cid)
    assert 1 <= len(pcn) <= 20
    # only X12-safe chars (no reserved delimiters ~ * : ^)
    assert all(c not in "~*:^" for c in pcn)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/services/test_claim_idempotency.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.claims.idempotency'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/app/services/claims/idempotency.py`:

```python
from __future__ import annotations

import hashlib


def generate_claim_idempotency_key(
    appointment_id: str,
    patient_id: str,
    insurance_id: str,
    submission_attempt: int = 1,
) -> str:
    """Deterministic claim idempotency key.

    Same inputs always produce the same key, so a network retry reuses it and the
    clearinghouse de-dupes. Increment `submission_attempt` ONLY for an intentional
    resubmission after a denial — NEVER for a network retry.
    """
    raw = f"claim:{appointment_id}:{patient_id}:{insurance_id}:v{submission_attempt}"
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_pcn(claim_id: str) -> str:
    """Patient Control Number (CLM01).

    Deterministic from the claim's own UUID; <= 20 chars (Stedi JSON limit) and
    uses only X12-safe characters. The 835 ERA (Module 7b) matches payments back
    to claims on this value.
    """
    return claim_id.replace("-", "")[:20].upper()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/services/test_claim_idempotency.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/claims/idempotency.py apps/api/tests/services/test_claim_idempotency.py
git commit -m "feat(7a): deterministic claim idempotency key + PCN"
```

---

## Task 4: Claim validator

**Files:**
- Create: `apps/api/app/services/claims/validator.py`
- Test: `apps/api/tests/services/test_claim_validator.py`

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/services/test_claim_validator.py`:

```python
from datetime import date

from app.services.claims.base import ClaimLine, DentalClaimInput
from app.services.claims.validator import validate_claim


def _claim(**overrides) -> DentalClaimInput:
    base = dict(
        patient_control_number="ABC123",
        payer_id="CDLA1",
        usage_indicator="T",
        billing_npi="1234567890",
        billing_tax_id="123456789",
        billing_taxonomy_code="1223G0001X",
        billing_org_name="Downtown Dental",
        submitter_id="SUB1",
        rendering_npi="1234567890",
        rendering_first_name="Jane",
        rendering_last_name="Dentist",
        subscriber_first_name="John",
        subscriber_last_name="Smith",
        subscriber_dob=date(1980, 1, 1),
        member_id="U123",
        group_number="GRP1",
        relationship_to_insured="self",
        patient_first_name="John",
        patient_last_name="Smith",
        patient_dob=date(1980, 1, 1),
        date_of_service=date(2026, 6, 18),
        lines=(
            ClaimLine(
                procedure_id="p1", cdt_code="D2392", fee_cents=20000,
                tooth_number="14", surface="O", procedure_name="Resin composite",
            ),
        ),
    )
    base.update(overrides)
    return DentalClaimInput(**base)


def test_valid_claim_has_no_errors():
    result = validate_claim(_claim())
    assert result.valid is True
    assert result.errors == []


def test_invalid_billing_npi_is_error():
    result = validate_claim(_claim(billing_npi="12345"))
    assert result.valid is False
    assert any("NPI" in e for e in result.errors)


def test_bad_cdt_code_is_error():
    result = validate_claim(
        _claim(lines=(ClaimLine(
            procedure_id="p1", cdt_code="X999", fee_cents=100,
            tooth_number=None, surface=None, procedure_name="bad",
        ),))
    )
    assert result.valid is False
    assert any("CDT" in e for e in result.errors)


def test_no_procedures_is_error():
    result = validate_claim(_claim(lines=()))
    assert result.valid is False
    assert any("procedure" in e.lower() for e in result.errors)


def test_pcn_over_20_chars_is_error():
    result = validate_claim(_claim(patient_control_number="X" * 21))
    assert result.valid is False
    assert any("control number" in e.lower() for e in result.errors)


def test_zero_fee_is_error():
    result = validate_claim(
        _claim(lines=(ClaimLine(
            procedure_id="p1", cdt_code="D0120", fee_cents=0,
            tooth_number=None, surface=None, procedure_name="Exam",
        ),))
    )
    assert result.valid is False
    assert any("fee" in e.lower() for e in result.errors)


def test_restorative_without_tooth_is_warning_not_error():
    result = validate_claim(
        _claim(lines=(ClaimLine(
            procedure_id="p1", cdt_code="D2740", fee_cents=90000,
            tooth_number=None, surface=None, procedure_name="Crown",
        ),))
    )
    assert result.valid is True
    assert any("tooth" in w.lower() for w in result.warnings)


def test_high_fee_is_warning():
    result = validate_claim(
        _claim(lines=(ClaimLine(
            procedure_id="p1", cdt_code="D2740", fee_cents=600000,
            tooth_number="14", surface=None, procedure_name="Crown",
        ),))
    )
    assert result.valid is True
    assert any("high" in w.lower() for w in result.warnings)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/services/test_claim_validator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.claims.validator'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/app/services/claims/validator.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.claims.base import DentalClaimInput

_VALID_CDT = re.compile(r"^D\d{4}$")
_VALID_NPI = re.compile(r"^\d{10}$")
_VALID_TAX_ID = re.compile(r"^\d{9}$")
_TOOTH_REQUIRED_PREFIXES = ("D2", "D3", "D4")  # restorative / endo / perio
_HIGH_FEE_CENTS = 500000  # $5,000


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_claim(claim: DentalClaimInput) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not _VALID_NPI.match(claim.billing_npi or ""):
        errors.append(f"Billing NPI invalid: {claim.billing_npi!r}")
    if not _VALID_NPI.match(claim.rendering_npi or ""):
        errors.append(f"Rendering NPI invalid: {claim.rendering_npi!r}")
    if not _VALID_TAX_ID.match(re.sub(r"-", "", claim.billing_tax_id or "")):
        errors.append("Billing tax ID (EIN) must be 9 digits")
    if not claim.billing_taxonomy_code:
        errors.append("Billing taxonomy code is required")
    if not claim.submitter_id:
        errors.append("Clearinghouse submitter ID is required")

    if not claim.lines:
        errors.append("Claim has no procedures")
    for i, line in enumerate(claim.lines, 1):
        if not _VALID_CDT.match(line.cdt_code or ""):
            errors.append(f"Line {i}: CDT code {line.cdt_code!r} must be D + 4 digits")
        if line.fee_cents <= 0:
            errors.append(f"Line {i}: fee must be greater than 0")
        if line.fee_cents > _HIGH_FEE_CENTS:
            warnings.append(f"Line {i}: fee ${line.fee_cents / 100:.2f} is unusually high — verify")
        if (
            any(line.cdt_code.startswith(p) for p in _TOOTH_REQUIRED_PREFIXES)
            and not line.tooth_number
        ):
            warnings.append(f"Line {i}: {line.cdt_code} typically requires a tooth number")

    if len(claim.patient_control_number) > 20:
        errors.append("Patient control number must be 20 characters or fewer")

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/services/test_claim_validator.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/claims/validator.py apps/api/tests/services/test_claim_validator.py
git commit -m "feat(7a): claim pre-submission validator"
```

---

## Task 5: Stedi claims client (payload mapper + submit)

**Files:**
- Create: `apps/api/app/services/claims/stedi.py`
- Test: `apps/api/tests/services/test_stedi_claims_client.py`

> **External-contract note:** field names for the Stedi Dental Claims (837D) JSON endpoint
> are taken from the Stedi reference (`https://www.stedi.com/docs/healthcare/api-reference/post-healthcare-dental-claims`):
> top-level `billing`, `subscriber`, `dependent`, `receiver`, `claimInformation`; and
> `claimInformation.serviceLines[]` with `procedureCodeQualifier="AD"`, `procedureCode`,
> `lineItemChargeAmount`, `toothNumber`, `lineItemControlNumber`,
> `unitOrBasisForMeasurementCode="UN"`, `serviceDate` (YYYYMMDD). The exact endpoint
> path/version and the nested `billing`/`subscriber` sub-field names must be confirmed
> against that reference + the Task 13 sandbox smoke test. The unit tests below assert on
> the parts of the payload we control and do NOT depend on the exact URL (httpx is mocked).

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/services/test_stedi_claims_client.py`:

```python
from datetime import date

import httpx
import pytest

from app.services.claims.base import ClaimLine, ClaimSubmissionError, DentalClaimInput
from app.services.claims.stedi import StediClaimsClient

_CLAIM = DentalClaimInput(
    patient_control_number="ABC123",
    payer_id="CDLA1",
    usage_indicator="T",
    billing_npi="1234567890",
    billing_tax_id="123456789",
    billing_taxonomy_code="1223G0001X",
    billing_org_name="Downtown Dental",
    submitter_id="SUB1",
    rendering_npi="1234567890",
    rendering_first_name="Jane",
    rendering_last_name="Dentist",
    subscriber_first_name="John",
    subscriber_last_name="Smith",
    subscriber_dob=date(1980, 1, 1),
    member_id="U123",
    group_number="GRP1",
    relationship_to_insured="self",
    patient_first_name="John",
    patient_last_name="Smith",
    patient_dob=date(1980, 1, 1),
    date_of_service=date(2026, 6, 18),
    lines=(
        ClaimLine(
            procedure_id="proc-1", cdt_code="D2392", fee_cents=20000,
            tooth_number="14", surface="O", procedure_name="Resin composite",
        ),
        ClaimLine(
            procedure_id="proc-2", cdt_code="D0120", fee_cents=5000,
            tooth_number=None, surface=None, procedure_name="Periodic exam",
        ),
    ),
)


def test_payload_maps_money_to_dollar_strings_and_lines():
    client = StediClaimsClient(api_key="k")
    payload = client.to_stedi_payload(_CLAIM)
    assert payload["usageIndicator"] == "T"
    assert payload["tradingPartnerServiceId"] == "CDLA1"
    info = payload["claimInformation"]
    assert info["patientControlNumber"] == "ABC123"
    assert info["claimChargeAmount"] == "250.00"  # 20000 + 5000 cents
    lines = info["serviceLines"]
    assert len(lines) == 2
    assert lines[0]["procedureCodeQualifier"] == "AD"
    assert lines[0]["procedureCode"] == "D2392"
    assert lines[0]["lineItemChargeAmount"] == "200.00"
    assert lines[0]["toothNumber"] == "14"
    assert lines[0]["lineItemControlNumber"] == "proc-1"
    assert lines[0]["serviceDate"] == "20260618"
    # subscriber omitted dependent when relationship is self
    assert "dependent" not in payload


def _client_returning(status_code: int, json_body: dict) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=json_body)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_accepted_response_returns_accepted_result():
    body = {
        "transactionId": "txn-1",
        "businessIdentifier": "biz-1",
        "submissionStatus": "ACCEPTED",
    }
    client = StediClaimsClient(api_key="k", client=_client_returning(200, body))
    result = await client.submit_dental_claim(_CLAIM, "idem-1")
    assert result.accepted is True
    assert result.clearinghouse_claim_id == "txn-1"
    assert result.errors == []


@pytest.mark.asyncio
async def test_edit_rejection_returns_not_accepted_with_errors():
    body = {
        "transactionId": "txn-2",
        "submissionStatus": "REJECTED",
        "errors": [{"description": "Invalid member ID"}],
    }
    client = StediClaimsClient(api_key="k", client=_client_returning(200, body))
    result = await client.submit_dental_claim(_CLAIM, "idem-2")
    assert result.accepted is False
    assert any("member" in e.lower() for e in result.errors)


@pytest.mark.asyncio
async def test_server_error_raises_retryable():
    client = StediClaimsClient(api_key="k", client=_client_returning(503, {}))
    with pytest.raises(ClaimSubmissionError) as exc:
        await client.submit_dental_claim(_CLAIM, "idem-3")
    assert exc.value.retryable is True


@pytest.mark.asyncio
async def test_sends_key_auth_and_idempotency_header():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        captured["idem"] = request.headers.get("Idempotency-Key")
        return httpx.Response(200, json={"transactionId": "t", "submissionStatus": "ACCEPTED"})

    client = StediClaimsClient(
        api_key="secret", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    await client.submit_dental_claim(_CLAIM, "idem-9")
    assert captured["auth"] == "Key secret"
    assert captured["idem"] == "idem-9"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/services/test_stedi_claims_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.claims.stedi'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/app/services/claims/stedi.py`:

```python
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.services.claims.base import (
    ClaimResult,
    ClaimSubmissionError,
    ClearinghouseClient,
    DentalClaimInput,
)

logger = logging.getLogger(__name__)

# NOTE: confirm the exact path/version against the Stedi Dental Claims (837D) JSON
# reference and the Task 13 sandbox smoke test before going live. Unit tests do not
# depend on this value (httpx is mocked).
_STEDI_DENTAL_CLAIMS_URL = (
    "https://healthcare.us.stedi.com/2024-04-01/change/medicalnetwork/dentalclaims/v3"
)
_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=15.0, pool=5.0)

# Stedi "paymentResponsibilityLevelCode": P = primary.
_PRIMARY = "P"


def _cents_to_dollars(cents: int) -> str:
    return f"{cents / 100:.2f}"


class StediClaimsClient(ClearinghouseClient):
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._client = client  # injected in tests; created per-call in prod

    def to_stedi_payload(self, claim: DentalClaimInput) -> dict[str, Any]:
        service_date = claim.date_of_service.strftime("%Y%m%d")
        service_lines: list[dict[str, Any]] = []
        for line in claim.lines:
            entry: dict[str, Any] = {
                "procedureCodeQualifier": "AD",
                "procedureCode": line.cdt_code,
                "lineItemChargeAmount": _cents_to_dollars(line.fee_cents),
                "unitOrBasisForMeasurementCode": "UN",
                "serviceUnitCount": "1",
                "serviceDate": service_date,
                "lineItemControlNumber": line.procedure_id,
            }
            if line.tooth_number:
                entry["toothNumber"] = line.tooth_number
            service_lines.append(entry)

        subscriber = {
            "memberId": claim.member_id,
            "paymentResponsibilityLevelCode": _PRIMARY,
            "firstName": claim.subscriber_first_name,
            "lastName": claim.subscriber_last_name,
            "dateOfBirth": claim.subscriber_dob.strftime("%Y%m%d"),
        }
        if claim.group_number:
            subscriber["groupNumber"] = claim.group_number

        payload: dict[str, Any] = {
            "usageIndicator": claim.usage_indicator,
            "controlNumber": claim.patient_control_number,
            "tradingPartnerServiceId": claim.payer_id,
            "submitter": {
                "organizationName": claim.billing_org_name,
                "contactInformation": {"name": claim.billing_org_name},
            },
            "receiver": {"organizationName": claim.payer_id},
            "billing": {
                "providerType": "BillingProvider",
                "npi": claim.billing_npi,
                "employerId": claim.billing_tax_id,
                "taxonomyCode": claim.billing_taxonomy_code,
                "organizationName": claim.billing_org_name,
            },
            "rendering": {
                "providerType": "RenderingProvider",
                "npi": claim.rendering_npi,
                "firstName": claim.rendering_first_name,
                "lastName": claim.rendering_last_name,
            },
            "subscriber": subscriber,
            "claimInformation": {
                "patientControlNumber": claim.patient_control_number,
                "claimChargeAmount": _cents_to_dollars(claim.total_charge_cents),
                "placeOfServiceCode": "11",  # office
                "claimFrequencyCode": "1",   # original
                "benefitsAssignmentCertificationIndicator": "Y",
                "serviceLines": service_lines,
            },
        }

        if claim.relationship_to_insured != "self":
            payload["dependent"] = {
                "firstName": claim.patient_first_name,
                "lastName": claim.patient_last_name,
                "dateOfBirth": claim.patient_dob.strftime("%Y%m%d"),
                "relationshipToSubscriberCode": _relationship_code(claim.relationship_to_insured),
            }

        return payload

    async def submit_dental_claim(
        self, claim: DentalClaimInput, idempotency_key: str
    ) -> ClaimResult:
        payload = self.to_stedi_payload(claim)
        headers = {"Authorization": f"Key {self._api_key}", "Idempotency-Key": idempotency_key}

        client = self._client or httpx.AsyncClient(timeout=_TIMEOUT)
        owns_client = self._client is None
        try:
            resp = await client.post(_STEDI_DENTAL_CLAIMS_URL, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ClaimSubmissionError(f"Stedi timeout: {exc}", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ClaimSubmissionError(f"Stedi transport error: {exc}", retryable=True) from exc
        finally:
            if owns_client:
                await client.aclose()

        if resp.status_code >= 500:
            raise ClaimSubmissionError(
                f"Stedi server error {resp.status_code}", retryable=True
            )

        try:
            body = resp.json()
        except ValueError as exc:
            raise ClaimSubmissionError(
                f"Stedi returned a non-JSON body: {resp.text[:200]}", retryable=True
            ) from exc

        errors = _extract_errors(body)
        # A 4xx or an explicit error/rejection is a clearinghouse edit failure (not retryable).
        status = str(body.get("submissionStatus", "")).upper()
        accepted = resp.status_code < 400 and not errors and status not in ("REJECTED", "ERROR")

        return ClaimResult(
            accepted=accepted,
            clearinghouse_claim_id=body.get("transactionId"),
            clearinghouse_status=body.get("submissionStatus"),
            errors=errors,
            raw_request=payload,
            raw_response=body,
        )


def _relationship_code(relationship: str) -> str:
    # X12 individual relationship codes: 01 spouse, 19 child, G8 other.
    return {"spouse": "01", "child": "19", "other": "G8"}.get(relationship, "G8")


def _extract_errors(body: dict[str, Any]) -> list[str]:
    raw = body.get("errors") or []
    out: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(str(item.get("description") or item.get("message") or item))
        else:
            out.append(str(item))
    return out
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/services/test_stedi_claims_client.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/claims/stedi.py apps/api/tests/services/test_stedi_claims_client.py
git commit -m "feat(7a): Stedi dental claims client — JSON mapper + submit + 277CA parse"
```

---

## Task 6: Claim builder (ORM rows → DentalClaimInput)

**Files:**
- Create: `apps/api/app/services/claims/builder.py`
- Test: `apps/api/tests/services/test_claim_builder.py`

The builder is a pure function taking already-fetched ORM rows (the service does the DB
queries) so it is unit-testable without a database.

- [ ] **Step 1: Write the failing test**

Create `apps/api/tests/services/test_claim_builder.py`:

```python
from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.services.claims.builder import build_claim_input


@dataclass
class _Practice:
    name: str = "Downtown Dental"
    billing_npi: str | None = "1234567890"
    billing_taxonomy_code: str | None = "1223G0001X"
    clearinghouse_submitter_id: str | None = "SUB1"


@dataclass
class _Provider:
    npi: str = "1234567890"
    first_name: str = "Jane"
    last_name: str = "Dentist"


@dataclass
class _Patient:
    first_name: str = "John"
    last_name: str = "Smith"
    date_of_birth: date = date(1980, 1, 1)


@dataclass
class _Insurance:
    relationship_to_insured: str = "self"
    member_id: str | None = "U123"
    group_number: str | None = "GRP1"
    insured_first_name: str | None = None
    insured_last_name: str | None = None
    insured_date_of_birth: date | None = None


@dataclass
class _Proc:
    id: str
    procedure_code: str
    procedure_name: str
    fee_cents: int
    tooth_number: str | None = None
    surface: str | None = None


@dataclass
class _Appt:
    start_time: datetime = datetime(2026, 6, 18, 14, 0, tzinfo=timezone.utc)


def test_builds_self_subscriber_and_sums_charges():
    claim = build_claim_input(
        appt=_Appt(),
        procedures=[
            _Proc("p1", "D2392", "Resin", 20000, "14", "O"),
            _Proc("p2", "D0120", "Exam", 5000),
        ],
        patient=_Patient(),
        insurance=_Insurance(),
        payer_id="CDLA1",
        practice=_Practice(),
        provider=_Provider(),
        billing_tax_id="123456789",
        pcn="ABC123",
        usage_indicator="T",
    )
    assert claim.total_charge_cents == 25000
    assert claim.subscriber_first_name == "John"   # self -> patient identity
    assert claim.relationship_to_insured == "self"
    assert len(claim.lines) == 2
    assert claim.lines[0].procedure_id == "p1"
    assert claim.lines[0].cdt_code == "D2392"
    assert claim.date_of_service == date(2026, 6, 18)


def test_non_self_uses_insured_identity_for_subscriber():
    claim = build_claim_input(
        appt=_Appt(),
        procedures=[_Proc("p1", "D0120", "Exam", 5000)],
        patient=_Patient(),
        insurance=_Insurance(
            relationship_to_insured="child",
            insured_first_name="Mary",
            insured_last_name="Smith",
            insured_date_of_birth=date(1975, 3, 3),
        ),
        payer_id="CDLA1",
        practice=_Practice(),
        provider=_Provider(),
        billing_tax_id="123456789",
        pcn="ABC123",
        usage_indicator="T",
    )
    assert claim.subscriber_first_name == "Mary"
    assert claim.subscriber_dob == date(1975, 3, 3)
    assert claim.patient_first_name == "John"     # patient stays the patient
    assert claim.relationship_to_insured == "child"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/services/test_claim_builder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.claims.builder'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/app/services/claims/builder.py`:

```python
from __future__ import annotations

from datetime import date
from typing import Any

from app.services.claims.base import ClaimLine, DentalClaimInput


def build_claim_input(
    *,
    appt: Any,
    procedures: list[Any],
    patient: Any,
    insurance: Any,
    payer_id: str,
    practice: Any,
    provider: Any,
    billing_tax_id: str,
    pcn: str,
    usage_indicator: str,
) -> DentalClaimInput:
    """Assemble a DentalClaimInput from already-fetched ORM rows (pure; no DB)."""
    if insurance.relationship_to_insured == "self":
        sub_first = patient.first_name
        sub_last = patient.last_name
        sub_dob = patient.date_of_birth
    else:
        sub_first = insurance.insured_first_name or ""
        sub_last = insurance.insured_last_name or ""
        sub_dob = insurance.insured_date_of_birth or patient.date_of_birth

    lines = tuple(
        ClaimLine(
            procedure_id=str(p.id),
            cdt_code=p.procedure_code or "",
            fee_cents=p.fee_cents,
            tooth_number=p.tooth_number,
            surface=p.surface,
            procedure_name=p.procedure_name,
        )
        for p in procedures
    )

    service_date: date = appt.start_time.date() if appt.start_time else date.today()

    return DentalClaimInput(
        patient_control_number=pcn,
        payer_id=payer_id,
        usage_indicator=usage_indicator,
        billing_npi=practice.billing_npi or "",
        billing_tax_id=billing_tax_id,
        billing_taxonomy_code=practice.billing_taxonomy_code or "",
        billing_org_name=practice.name,
        submitter_id=practice.clearinghouse_submitter_id or "",
        rendering_npi=provider.npi,
        rendering_first_name=provider.first_name,
        rendering_last_name=provider.last_name,
        subscriber_first_name=sub_first,
        subscriber_last_name=sub_last,
        subscriber_dob=sub_dob,
        member_id=insurance.member_id or "",
        group_number=insurance.group_number,
        relationship_to_insured=insurance.relationship_to_insured,
        patient_first_name=patient.first_name,
        patient_last_name=patient.last_name,
        patient_dob=patient.date_of_birth,
        date_of_service=service_date,
        lines=lines,
    )
```

> **Check the `provider` row exposes `first_name`/`last_name`.** If `app/models/provider.py`
> uses different attribute names (e.g. a single `name`), adjust `rendering_first_name`/
> `rendering_last_name` here and in the test accordingly. Verify before implementing.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/services/test_claim_builder.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/claims/builder.py apps/api/tests/services/test_claim_builder.py
git commit -m "feat(7a): claim builder — ORM rows to DentalClaimInput"
```

---

## Task 7: Claims orchestration service

**Files:**
- Create: `apps/api/app/services/claims/service.py`
- Test: `apps/api/tests/integration/test_claims_service.py`

- [ ] **Step 1: Write the failing integration test**

Create `apps/api/tests/integration/test_claims_service.py`. Model the seed fixtures on
`tests/integration/test_copay_service.py` (same `db_session` fixture, `_seed_*` helpers).
The Stedi client is injected so no network happens.

```python
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt
from app.models.appointment import Appointment
from app.models.appointment_procedure import AppointmentProcedure
from app.models.claim import Claim
from app.models.patient import Patient
from app.models.patient_insurance import PatientInsurance
from app.models.insurance_plan import InsurancePlan
from app.models.practice import Practice
from app.models.provider import Provider
from app.services.claims.base import ClaimResult, ClearinghouseClient, DentalClaimInput
from app.services.claims.service import (
    ClaimSubmissionPrereqError,
    submit_claim_for_appointment,
)

pytestmark = pytest.mark.integration


class _FakeClient(ClearinghouseClient):
    def __init__(self, result: ClaimResult):
        self._result = result
        self.calls = 0

    async def submit_dental_claim(self, claim: DentalClaimInput, idempotency_key: str) -> ClaimResult:
        self.calls += 1
        return self._result


def _ok_result() -> ClaimResult:
    return ClaimResult(
        accepted=True, clearinghouse_claim_id="txn-1", clearinghouse_status="ACCEPTED",
        errors=[], raw_request={"k": "v"}, raw_response={"transactionId": "txn-1"},
    )


async def _seed(session: AsyncSession):
    practice = Practice(
        id=uuid.uuid4(), name="Downtown Dental",
        features={"claims_submission": True},
        billing_npi="1234567890", billing_taxonomy_code="1223G0001X",
        billing_tax_id_encrypted=encrypt("123456789"),
        clearinghouse_submitter_id="SUB1", clearinghouse_provider="stedi",
        clearinghouse_api_key_ssm_path="/dental/staging/clearinghouse/api_key",
    )
    session.add(practice)
    provider = Provider(
        id=uuid.uuid4(), practice_id=practice.id, npi="1234567890",
        first_name="Jane", last_name="Dentist", provider_type="dentist",
    )
    patient = Patient(
        id=uuid.uuid4(), practice_id=practice.id, first_name="John", last_name="Smith",
        date_of_birth=date(1980, 1, 1),
    )
    plan = InsurancePlan(
        id=uuid.uuid4(), practice_id=practice.id, payer_id="CDLA1", name="Cigna DPPO",
    )
    session.add_all([provider, patient, plan])
    insurance = PatientInsurance(
        id=uuid.uuid4(), practice_id=practice.id, patient_id=patient.id, priority="primary",
        carrier="Cigna", member_id="U123", group_number="GRP1",
        relationship_to_insured="self", insurance_plan_id=plan.id,
    )
    appt = Appointment(
        id=uuid.uuid4(), practice_id=practice.id, patient_id=patient.id,
        provider_id=provider.id, start_time=datetime(2026, 6, 18, 14, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 6, 18, 15, 0, tzinfo=timezone.utc),
    )
    session.add_all([insurance, appt])
    proc = AppointmentProcedure(
        id=uuid.uuid4(), practice_id=practice.id, appointment_id=appt.id, patient_id=patient.id,
        procedure_code="D2392", procedure_name="Resin", fee_cents=20000, tooth_number="14",
    )
    session.add(proc)
    await session.commit()
    return practice, appt


@pytest.mark.asyncio
async def test_submits_and_persists_submitted(db_session: AsyncSession):
    practice, appt = await _seed(db_session)
    client = _FakeClient(_ok_result())

    claim = await submit_claim_for_appointment(
        db_session, practice.id, appt.id, "idem-1", client=client, usage_indicator="T",
        user_sub="sub-1",
    )
    assert claim.status == "submitted"
    assert claim.clearinghouse_claim_id == "txn-1"
    assert claim.total_charge_cents == 20000
    assert client.calls == 1


@pytest.mark.asyncio
async def test_idempotent_second_call_returns_same_row(db_session: AsyncSession):
    practice, appt = await _seed(db_session)
    client = _FakeClient(_ok_result())
    first = await submit_claim_for_appointment(
        db_session, practice.id, appt.id, "idem-1", client=client, usage_indicator="T",
        user_sub="sub-1",
    )
    second = await submit_claim_for_appointment(
        db_session, practice.id, appt.id, "idem-1", client=client, usage_indicator="T",
        user_sub="sub-1",
    )
    assert first.id == second.id
    assert client.calls == 1  # no second network call


@pytest.mark.asyncio
async def test_rejected_result_marks_clearinghouse_rejected(db_session: AsyncSession):
    practice, appt = await _seed(db_session)
    rejected = ClaimResult(
        accepted=False, clearinghouse_claim_id="txn-x", clearinghouse_status="REJECTED",
        errors=["Invalid member ID"], raw_request={}, raw_response={},
    )
    claim = await submit_claim_for_appointment(
        db_session, practice.id, appt.id, "idem-2", client=_FakeClient(rejected),
        usage_indicator="T", user_sub="sub-1",
    )
    assert claim.status == "clearinghouse_rejected"
    assert claim.submission_errors == ["Invalid member ID"]


@pytest.mark.asyncio
async def test_no_procedures_raises_prereq_error(db_session: AsyncSession):
    practice, appt = await _seed(db_session)
    # delete the procedure
    proc = await db_session.scalar(
        __import__("sqlalchemy").select(AppointmentProcedure).where(
            AppointmentProcedure.appointment_id == appt.id
        )
    )
    await db_session.delete(proc)
    await db_session.commit()
    with pytest.raises(ClaimSubmissionPrereqError) as exc:
        await submit_claim_for_appointment(
            db_session, practice.id, appt.id, "idem-3", client=_FakeClient(_ok_result()),
            usage_indicator="T", user_sub="sub-1",
        )
    assert exc.value.code == "NO_PROCEDURES"
```

> Adjust model constructor kwargs above to match the real column names if any differ
> (verify against the model files before running). The intent — seed practice/provider/
> patient/plan/insurance/appointment/procedure — is what matters.

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest -m integration tests/integration/test_claims_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.claims.service'`

- [ ] **Step 3: Write the implementation**

Create `apps/api/app/services/claims/service.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt
from app.models.appointment import Appointment
from app.models.appointment_procedure import AppointmentProcedure
from app.models.claim import Claim
from app.models.insurance_plan import InsurancePlan
from app.models.patient import Patient
from app.models.patient_insurance import PatientInsurance
from app.models.practice import Practice
from app.models.provider import Provider
from app.services.claims.base import ClearinghouseClient, ClaimSubmissionError
from app.services.claims.builder import build_claim_input
from app.services.claims.idempotency import generate_pcn
from app.services.claims.validator import validate_claim


class ClaimSubmissionPrereqError(Exception):
    """A prerequisite for building/submitting a claim is missing or invalid."""

    def __init__(self, code: str, message: str, *, errors: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.errors = errors or []


async def submit_claim_for_appointment(
    session: AsyncSession,
    practice_id: uuid.UUID,
    appointment_id: uuid.UUID,
    idempotency_key: str,
    *,
    client: ClearinghouseClient,
    usage_indicator: str,
    user_sub: str | None,
) -> Claim:
    # 1. Idempotency — return the existing claim unchanged, no second network call.
    existing = await session.scalar(
        select(Claim).where(
            Claim.idempotency_key == idempotency_key,
            Claim.practice_id == practice_id,
        )
    )
    if existing is not None:
        return existing

    # 2. Load appointment + scope check.
    appt = await session.scalar(
        select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.practice_id == practice_id,
            Appointment.deleted_at.is_(None),
        )
    )
    if appt is None or appt.patient_id is None:
        raise ClaimSubmissionPrereqError("APPOINTMENT_NOT_FOUND", "Appointment not found")
    if appt.provider_id is None:
        raise ClaimSubmissionPrereqError(
            "NO_PROVIDER", "Appointment has no provider; a rendering provider is required"
        )

    procedures = (
        await session.scalars(
            select(AppointmentProcedure).where(
                AppointmentProcedure.appointment_id == appointment_id,
                AppointmentProcedure.deleted_at.is_(None),
            )
        )
    ).all()
    if not procedures:
        raise ClaimSubmissionPrereqError("NO_PROCEDURES", "Appointment has no procedures")

    patient = await session.scalar(select(Patient).where(Patient.id == appt.patient_id))
    if patient is None:
        raise ClaimSubmissionPrereqError("PATIENT_NOT_FOUND", "Patient not found")

    insurance = await session.scalar(
        select(PatientInsurance).where(
            PatientInsurance.patient_id == appt.patient_id,
            PatientInsurance.practice_id == practice_id,
            PatientInsurance.priority == "primary",
            PatientInsurance.deleted_at.is_(None),
        )
    )
    if insurance is None or insurance.insurance_plan_id is None:
        raise ClaimSubmissionPrereqError(
            "NO_INSURANCE", "Patient has no primary insurance with a linked plan"
        )
    plan = await session.scalar(
        select(InsurancePlan).where(InsurancePlan.id == insurance.insurance_plan_id)
    )
    if plan is None:
        raise ClaimSubmissionPrereqError("NO_PAYER_ID", "Linked insurance plan not found")

    provider = await session.scalar(select(Provider).where(Provider.id == appt.provider_id))
    if provider is None:
        raise ClaimSubmissionPrereqError("NO_PROVIDER", "Rendering provider not found")

    practice = await session.scalar(select(Practice).where(Practice.id == practice_id))
    if practice is None or not practice.billing_npi:
        raise ClaimSubmissionPrereqError("MISSING_NPI", "Practice billing NPI is not configured")
    if not practice.clearinghouse_submitter_id:
        raise ClaimSubmissionPrereqError(
            "MISSING_CLEARINGHOUSE", "Clearinghouse submitter ID is not configured"
        )
    if not practice.billing_tax_id_encrypted:
        raise ClaimSubmissionPrereqError(
            "MISSING_TAX_ID", "Practice billing tax ID is not configured"
        )
    billing_tax_id = decrypt(practice.billing_tax_id_encrypted)

    # 3. Persist a draft BEFORE the network call so a crash leaves a retryable record.
    claim_id = uuid.uuid4()
    pcn = generate_pcn(str(claim_id))
    claim_input = build_claim_input(
        appt=appt,
        procedures=list(procedures),
        patient=patient,
        insurance=insurance,
        payer_id=plan.payer_id,
        practice=practice,
        provider=provider,
        billing_tax_id=billing_tax_id,
        pcn=pcn,
        usage_indicator=usage_indicator,
    )

    # 4. Validate before any network call.
    validation = validate_claim(claim_input)
    if not validation.valid:
        raise ClaimSubmissionPrereqError(
            "CLAIM_INVALID", "Claim failed validation", errors=validation.errors
        )

    payload = client.to_stedi_payload(claim_input) if hasattr(client, "to_stedi_payload") else None
    claim = Claim(
        id=claim_id,
        practice_id=practice_id,
        appointment_id=appointment_id,
        patient_id=patient.id,
        insurance_id=insurance.id,
        provider_id=provider.id,
        idempotency_key=idempotency_key,
        patient_control_number=pcn,
        payer_id=plan.payer_id,
        status="draft",
        total_charge_cents=claim_input.total_charge_cents,
        raw_submission=payload,
        last_accessed_by=user_sub,
        last_accessed_at=datetime.now(UTC),
    )
    session.add(claim)
    await session.commit()

    # 5. Submit.
    try:
        result = await client.submit_dental_claim(claim_input, idempotency_key)
    except ClaimSubmissionError as exc:
        claim.status = "submission_failed"
        claim.submission_errors = [str(exc)]
        await session.commit()
        await session.refresh(claim)
        return claim

    # 6. Apply result.
    claim.raw_submission = result.raw_request
    claim.raw_response = result.raw_response
    claim.clearinghouse_claim_id = result.clearinghouse_claim_id
    claim.clearinghouse_status = result.clearinghouse_status
    if result.accepted:
        claim.status = "submitted"
        claim.submitted_at = datetime.now(UTC)
    else:
        claim.status = "clearinghouse_rejected"
        claim.submission_errors = result.errors
    await session.commit()
    await session.refresh(claim)
    return claim
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest -m integration tests/integration/test_claims_service.py -v`
Expected: PASS (4 passed). If a seed kwarg mismatches a real column, fix the test seed (not the model) and re-run.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/claims/service.py apps/api/tests/integration/test_claims_service.py
git commit -m "feat(7a): claims orchestration service (idempotent, persist-before-network)"
```

---

## Task 8: Zod schemas → generated Pydantic

**Files:**
- Create: `packages/shared-types/src/schemas/claims.ts`
- Modify: `packages/shared-types/src/index.ts`
- Modify: `packages/shared-types/scripts/generate-pydantic.ts`
- Generated (do not hand-edit): `apps/api/app/schemas/generated.py`

- [ ] **Step 1: Write the Zod schemas**

Create `packages/shared-types/src/schemas/claims.ts` (mirror `copay.ts` conventions — camelCase, `UuidSchema`, int cents, `z.string().datetime()`):

```typescript
import { z } from "zod";
import { UuidSchema } from "./common.js";

export const ClaimStatusSchema = z.enum([
  "draft",
  "submitted",
  "clearinghouse_rejected",
  "submission_failed",
  "acknowledged",
  "pending",
  "paid",
  "partially_paid",
  "denied",
  "appealing",
]);
export type ClaimStatus = z.infer<typeof ClaimStatusSchema>;

export const ClaimSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  appointmentId: UuidSchema,
  patientId: UuidSchema,
  insuranceId: UuidSchema,
  providerId: UuidSchema,
  idempotencyKey: z.string(),
  submissionAttempt: z.number().int(),
  patientControlNumber: z.string(),
  payerId: z.string(),
  status: ClaimStatusSchema,
  totalChargeCents: z.number().int(),
  clearinghouseClaimId: z.string().nullable(),
  clearinghouseStatus: z.string().nullable(),
  submissionErrors: z.array(z.string()).nullable(),
  submittedAt: z.string().datetime().nullable(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});
export type Claim = z.infer<typeof ClaimSchema>;
```

- [ ] **Step 2: Register the schema barrel export**

In `packages/shared-types/src/index.ts`, add:

```typescript
export * from "./schemas/claims.js";
```

- [ ] **Step 3: Register the schemas in the codegen script**

In `packages/shared-types/scripts/generate-pydantic.ts`: import the new schemas alongside the existing imports, and add them to the `schemas` registry object (follow exactly how `CopayEstimate`/`CopayLineItem` are registered):

```typescript
import { ClaimSchema, ClaimStatusSchema } from "../src/schemas/claims.js";
// ... in the schemas registry object:
//   Claim: ClaimSchema,
//   ClaimStatus: ClaimStatusSchema,
```

- [ ] **Step 4: Regenerate Pydantic models**

Run from repo root: `pnpm generate`
Expected: completes without error; `apps/api/app/schemas/generated.py` now contains a `Claim` class with `alias='...'` camelCase fields and a `ClaimStatus` enum.

- [ ] **Step 5: Verify the generated class imports**

Run from `apps/api/`: `python -c "from app.schemas.generated import Claim, ClaimStatus; print('ok')"`
Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add packages/shared-types/src/schemas/claims.ts packages/shared-types/src/index.ts packages/shared-types/scripts/generate-pydantic.ts apps/api/app/schemas/generated.py
git commit -m "feat(7a): claims Zod schemas + regenerated Pydantic"
```

---

## Task 9: Claims router + registration

**Files:**
- Create: `apps/api/app/routers/claims.py`
- Modify: `apps/api/app/main.py`

- [ ] **Step 1: Write the router**

Create `apps/api/app/routers/claims.py`:

```python
from __future__ import annotations

import logging
import uuid
from datetime import UTC

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session_factory
from app.core.features import require_feature
from app.core.ssm import get_ssm_parameter
from app.models.claim import Claim as ClaimModel
from app.models.practice import Practice as PracticeModel
from app.routers.patients import _require_practice_scope, _require_write_role
from app.schemas.generated import ApiError, Claim, Error
from app.services.claims.base import ClaimSubmissionError
from app.services.claims.service import (
    ClaimSubmissionPrereqError,
    submit_claim_for_appointment,
)
from app.services.claims.stedi import StediClaimsClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["claims"])

_FEATURE = "claims_submission"

# 'T' for any non-production environment; 'P' only in production.
def _usage_indicator(practice: PracticeModel) -> str:
    import os

    return "P" if os.getenv("APP_ENV") == "production" else "T"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail=ApiError(error=Error(code=code, message=message)).model_dump(by_alias=True),
    )


def _to_schema(row: ClaimModel) -> Claim:
    return Claim(
        id=row.id,
        practiceId=row.practice_id,
        appointmentId=row.appointment_id,
        patientId=row.patient_id,
        insuranceId=row.insurance_id,
        providerId=row.provider_id,
        idempotencyKey=row.idempotency_key,
        submissionAttempt=row.submission_attempt,
        patientControlNumber=row.patient_control_number,
        payerId=row.payer_id,
        status=row.status,  # type: ignore[arg-type]
        totalChargeCents=row.total_charge_cents,
        clearinghouseClaimId=row.clearinghouse_claim_id,
        clearinghouseStatus=row.clearinghouse_status,
        submissionErrors=row.submission_errors,
        submittedAt=row.submitted_at.replace(tzinfo=UTC) if row.submitted_at else None,
        createdAt=(row.created_at).replace(tzinfo=UTC),
        updatedAt=(row.updated_at).replace(tzinfo=UTC),
    )


@router.post(
    "/appointments/{appointment_id}/claim", status_code=201, response_model=Claim
)
async def submit_claim(appointment_id: uuid.UUID, request: Request) -> Claim:
    practice_id = _require_practice_scope(request)
    _require_write_role(request)
    user_sub = getattr(request.state.user, "sub", None)
    idempotency_key = request.headers.get("Idempotency-Key") or str(uuid.uuid4())

    async with get_session_factory()() as session:
        practice = await session.scalar(
            select(PracticeModel).where(PracticeModel.id == practice_id)
        )
        await require_feature(session, practice_id, _FEATURE, practice=practice)
        assert practice is not None

        if not practice.clearinghouse_api_key_ssm_path:
            raise _err(422, "MISSING_CLEARINGHOUSE", "Clearinghouse credentials are not configured")
        api_key = get_ssm_parameter(practice.clearinghouse_api_key_ssm_path)
        if not api_key:
            raise _err(422, "MISSING_CLEARINGHOUSE", "Clearinghouse API key unavailable")

        client = StediClaimsClient(api_key=api_key)
        try:
            claim = await submit_claim_for_appointment(
                session,
                practice_id,
                appointment_id,
                idempotency_key,
                client=client,
                usage_indicator=_usage_indicator(practice),
                user_sub=user_sub,
            )
        except ClaimSubmissionPrereqError as exc:
            status = 404 if exc.code == "APPOINTMENT_NOT_FOUND" else 422
            detail = ApiError(
                error=Error(code=exc.code, message=exc.message)
            ).model_dump(by_alias=True)
            if exc.errors:
                detail["error"]["details"] = exc.errors  # type: ignore[index]
            raise HTTPException(status_code=status, detail=detail) from exc
        except ClaimSubmissionError as exc:
            raise _err(502, "CLEARINGHOUSE_ERROR", str(exc)) from exc
        return _to_schema(claim)


@router.get("/appointments/{appointment_id}/claim", response_model=list[Claim])
async def list_appointment_claims(appointment_id: uuid.UUID, request: Request) -> list[Claim]:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        rows = (
            await session.scalars(
                select(ClaimModel)
                .where(
                    ClaimModel.appointment_id == appointment_id,
                    ClaimModel.practice_id == practice_id,
                    ClaimModel.deleted_at.is_(None),
                )
                .order_by(ClaimModel.created_at.desc())
            )
        ).all()
        return [_to_schema(r) for r in rows]


@router.get("/claims/{claim_id}", response_model=Claim)
async def get_claim(claim_id: uuid.UUID, request: Request) -> Claim:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        row = await session.scalar(
            select(ClaimModel).where(
                ClaimModel.id == claim_id,
                ClaimModel.practice_id == practice_id,
                ClaimModel.deleted_at.is_(None),
            )
        )
        if row is None:
            raise _err(404, "CLAIM_NOT_FOUND", "Claim not found")
        return _to_schema(row)


@router.get("/claims", response_model=list[Claim])
async def list_claims(request: Request, status: str | None = None) -> list[Claim]:
    practice_id = _require_practice_scope(request)
    async with get_session_factory()() as session:
        await require_feature(session, practice_id, _FEATURE)
        stmt = select(ClaimModel).where(
            ClaimModel.practice_id == practice_id,
            ClaimModel.deleted_at.is_(None),
        )
        if status:
            stmt = stmt.where(ClaimModel.status == status)
        rows = (await session.scalars(stmt.order_by(ClaimModel.created_at.desc()))).all()
        return [_to_schema(r) for r in rows]
```

> If `ApiError`/`Error` has no `details` field, drop the `detail["error"]["details"]` line
> and return just code+message (the validator errors are then surfaced only in logs). Verify
> the generated `Error` shape before relying on `details`.

- [ ] **Step 2: Register the router**

In `apps/api/app/main.py`: add `claims` to the routers import block (near `copay, eligibility,`) and add the include after `app.include_router(copay.router)`:

```python
    app.include_router(claims.router)
```

- [ ] **Step 3: Verify the app imports cleanly**

Run from `apps/api/`: `python -c "from app.main import app; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/routers/claims.py apps/api/app/main.py
git commit -m "feat(7a): claims router + registration"
```

---

## Task 10: Router integration tests (happy path + failure)

**Files:**
- Create: `apps/api/tests/integration/test_claims_endpoints.py`

- [ ] **Step 1: Write the tests**

Model auth/feature fixtures on `tests/integration/test_copay_endpoints.py`. Mock SSM so the
key resolves, and mock the Stedi HTTP call with `httpx.MockTransport` by patching
`app.services.claims.stedi.httpx.AsyncClient` — OR (simpler) patch
`app.routers.claims.StediClaimsClient` to return a fake client. Use the latter.

Create `apps/api/tests/integration/test_claims_endpoints.py`:

```python
import uuid
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt
from app.models.appointment import Appointment
from app.models.appointment_procedure import AppointmentProcedure
from app.models.insurance_plan import InsurancePlan
from app.models.patient import Patient
from app.models.patient_insurance import PatientInsurance
from app.models.practice import Practice
from app.models.provider import Provider
from app.models.user import PracticeUser, User
from app.services.claims.base import ClaimResult, ClearinghouseClient, DentalClaimInput

pytestmark = pytest.mark.integration

# Auth patch targets — copy the exact constants used in test_copay_endpoints.py
_P_HEADER = "app.core.auth.jwt.get_unverified_header"
_P_KEY = "app.core.auth._get_public_key"
_P_DECODE = "app.core.auth.jwt.decode"


class _FakeClient(ClearinghouseClient):
    def __init__(self, result: ClaimResult):
        self._result = result

    def to_stedi_payload(self, claim: DentalClaimInput) -> dict:
        return {"ok": True}

    async def submit_dental_claim(self, claim, idempotency_key) -> ClaimResult:
        return self._result


def _accepted() -> ClaimResult:
    return ClaimResult(
        accepted=True, clearinghouse_claim_id="txn-1", clearinghouse_status="ACCEPTED",
        errors=[], raw_request={}, raw_response={"transactionId": "txn-1"},
    )


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession):
    practice = Practice(
        id=uuid.uuid4(), name="Downtown Dental",
        features={"claims_submission": True},
        billing_npi="1234567890", billing_taxonomy_code="1223G0001X",
        billing_tax_id_encrypted=encrypt("123456789"),
        clearinghouse_submitter_id="SUB1", clearinghouse_provider="stedi",
        clearinghouse_api_key_ssm_path="/dental/staging/clearinghouse/api_key",
    )
    user = User(id=uuid.uuid4(), email="staff@example.com", cognito_sub="sub-staff")
    member = PracticeUser(id=uuid.uuid4(), user_id=user.id, practice_id=practice.id, role="admin")
    provider = Provider(
        id=uuid.uuid4(), practice_id=practice.id, npi="1234567890",
        first_name="Jane", last_name="Dentist", provider_type="dentist",
    )
    patient = Patient(
        id=uuid.uuid4(), practice_id=practice.id, first_name="John", last_name="Smith",
        date_of_birth=date(1980, 1, 1),
    )
    plan = InsurancePlan(
        id=uuid.uuid4(), practice_id=practice.id, payer_id="CDLA1", name="Cigna DPPO",
    )
    insurance = PatientInsurance(
        id=uuid.uuid4(), practice_id=practice.id, patient_id=patient.id, priority="primary",
        carrier="Cigna", member_id="U123", relationship_to_insured="self",
        insurance_plan_id=plan.id,
    )
    appt = Appointment(
        id=uuid.uuid4(), practice_id=practice.id, patient_id=patient.id, provider_id=provider.id,
        start_time=datetime(2026, 6, 18, 14, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 6, 18, 15, 0, tzinfo=timezone.utc),
    )
    proc = AppointmentProcedure(
        id=uuid.uuid4(), practice_id=practice.id, appointment_id=appt.id, patient_id=patient.id,
        procedure_code="D2392", procedure_name="Resin", fee_cents=20000, tooth_number="14",
    )
    db_session.add_all([practice, user, member, provider, patient, plan, insurance, appt, proc])
    await db_session.commit()
    return practice, appt, user


def _auth_headers(practice_id, cognito_sub, email):
    return patch(_P_HEADER, return_value={"kid": "k"}), email, cognito_sub


@pytest.mark.asyncio
async def test_submit_claim_201(client: AsyncClient, seeded):
    practice, appt, user = seeded
    headers = {"Authorization": "Bearer t", "X-Practice-ID": str(practice.id),
               "Idempotency-Key": str(uuid.uuid4())}
    with (
        patch(_P_HEADER, return_value={"kid": "k"}),
        patch(_P_KEY, return_value="pk"),
        patch(_P_DECODE, return_value={"sub": user.cognito_sub, "email": user.email,
                                       "cognito:groups": ["admin"]}),
        patch("app.routers.claims.get_ssm_parameter", return_value="fake-key"),
        patch("app.routers.claims.StediClaimsClient", return_value=_FakeClient(_accepted())),
    ):
        resp = await client.post(
            f"/api/v1/appointments/{appt.id}/claim", headers=headers
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "submitted"
    assert body["totalChargeCents"] == 20000
    assert body["clearinghouseClaimId"] == "txn-1"


@pytest.mark.asyncio
async def test_submit_without_feature_403(client: AsyncClient, db_session: AsyncSession):
    practice = Practice(
        id=uuid.uuid4(), name="No Feature", features={"claims_submission": False},
    )
    user = User(id=uuid.uuid4(), email="s2@example.com", cognito_sub="sub-2")
    member = PracticeUser(id=uuid.uuid4(), user_id=user.id, practice_id=practice.id, role="admin")
    db_session.add_all([practice, user, member])
    await db_session.commit()
    headers = {"Authorization": "Bearer t", "X-Practice-ID": str(practice.id),
               "Idempotency-Key": str(uuid.uuid4())}
    with (
        patch(_P_HEADER, return_value={"kid": "k"}),
        patch(_P_KEY, return_value="pk"),
        patch(_P_DECODE, return_value={"sub": user.cognito_sub, "email": user.email,
                                       "cognito:groups": ["admin"]}),
    ):
        resp = await client.post(
            f"/api/v1/appointments/{uuid.uuid4()}/claim", headers=headers
        )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_submit_missing_appointment_404(client: AsyncClient, seeded):
    practice, _appt, user = seeded
    headers = {"Authorization": "Bearer t", "X-Practice-ID": str(practice.id),
               "Idempotency-Key": str(uuid.uuid4())}
    with (
        patch(_P_HEADER, return_value={"kid": "k"}),
        patch(_P_KEY, return_value="pk"),
        patch(_P_DECODE, return_value={"sub": user.cognito_sub, "email": user.email,
                                       "cognito:groups": ["admin"]}),
        patch("app.routers.claims.get_ssm_parameter", return_value="fake-key"),
        patch("app.routers.claims.StediClaimsClient", return_value=_FakeClient(_accepted())),
    ):
        resp = await client.post(
            f"/api/v1/appointments/{uuid.uuid4()}/claim", headers=headers
        )
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "APPOINTMENT_NOT_FOUND"
```

> Confirm the exact auth-patch constants and `User`/`PracticeUser` field names against
> `test_copay_endpoints.py` and the model files; adjust if they differ. The three behaviors
> under test — 201 happy path, 403 feature gate, 404 missing appointment — are the contract.

- [ ] **Step 2: Run the tests**

Run: `pytest -m integration tests/integration/test_claims_endpoints.py -v`
Expected: PASS (3 passed)

- [ ] **Step 3: Run the whole claims unit + integration suite**

Run: `pytest tests/services/test_claim_*.py tests/services/test_stedi_claims_client.py -v && pytest -m integration tests/integration/test_claims_*.py -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/api/tests/integration/test_claims_endpoints.py
git commit -m "test(7a): claims endpoint integration tests (201 / 403 / 404)"
```

---

## Task 11: Frontend — API hooks (`claims.ts`)

**Files:**
- Create: `apps/web/lib/api/claims.ts`

- [ ] **Step 1: Write the API module**

Mirror `apps/web/lib/api/copay.ts` (types + React Query hooks + `apiClient` + `generateId`).
Create `apps/web/lib/api/claims.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";

export type ClaimStatus =
  | "draft"
  | "submitted"
  | "clearinghouse_rejected"
  | "submission_failed"
  | "acknowledged"
  | "pending"
  | "paid"
  | "partially_paid"
  | "denied"
  | "appealing";

export interface Claim {
  id: string;
  practiceId: string;
  appointmentId: string;
  patientId: string;
  insuranceId: string;
  providerId: string;
  idempotencyKey: string;
  submissionAttempt: number;
  patientControlNumber: string;
  payerId: string;
  status: ClaimStatus;
  totalChargeCents: number;
  clearinghouseClaimId: string | null;
  clearinghouseStatus: string | null;
  submissionErrors: string[] | null;
  submittedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export const claimsKeys = {
  all: ["claims"] as const,
  list: (status?: string) => ["claims", { status: status ?? null }] as const,
  appointment: (appointmentId: string) => ["claims", "appointment", appointmentId] as const,
};

export function useAppointmentClaims(appointmentId: string) {
  return useQuery({
    queryKey: claimsKeys.appointment(appointmentId),
    queryFn: () => apiClient.get<Claim[]>(`/api/v1/appointments/${appointmentId}/claim`),
  });
}

export function useClaimsList(status?: string) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return useQuery({
    queryKey: claimsKeys.list(status),
    queryFn: () => apiClient.get<Claim[]>(`/api/v1/claims${query}`),
  });
}

export function useSubmitClaim(appointmentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiClient.post<Claim>(`/api/v1/appointments/${appointmentId}/claim`, undefined, {
        idempotencyKey: generateId(),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: claimsKeys.appointment(appointmentId) });
      void qc.invalidateQueries({ queryKey: claimsKeys.all });
    },
  });
}
```

> Confirm `apiClient.post(path, body, { idempotencyKey })` accepts `undefined` body. If it
> requires a body object, pass `{}`. Check the signature in `apps/web/lib/api-client.ts`.

- [ ] **Step 2: Type-check**

Run from `apps/web/`: `pnpm type-check`
Expected: no errors in `lib/api/claims.ts`.

- [ ] **Step 3: Commit**

```bash
git add apps/web/lib/api/claims.ts
git commit -m "feat(7a): frontend claims API hooks"
```

---

## Task 12: Frontend — Claim panel + worklist page

**Files:**
- Create: `apps/web/components/scheduling/ClaimPanel.tsx`
- Modify: `apps/web/components/scheduling/AppointmentModal.tsx`
- Modify: `apps/web/app/(app)/billing/claims/page.tsx`

- [ ] **Step 1: Write the ClaimPanel component**

Mirror `apps/web/components/scheduling/CopayEstimateCard.tsx` (Card structure, status badge,
mutation button, `centsToUsd`). Create `apps/web/components/scheduling/ClaimPanel.tsx`:

```tsx
"use client";

import { Send } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAppointmentClaims, useSubmitClaim, type Claim } from "@/lib/api/claims";

function centsToUsd(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function statusVariant(status: Claim["status"]): "default" | "secondary" | "destructive" {
  if (status === "submitted" || status === "paid" || status === "acknowledged") return "default";
  if (status === "clearinghouse_rejected" || status === "submission_failed" || status === "denied")
    return "destructive";
  return "secondary";
}

export function ClaimPanel({ appointmentId }: { appointmentId: string }) {
  const { data: claims = [], isLoading } = useAppointmentClaims(appointmentId);
  const submit = useSubmitClaim(appointmentId);
  const latest = claims[0];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">Insurance Claim</CardTitle>
        <Button
          size="sm"
          disabled={submit.isPending}
          onClick={() => submit.mutate()}
        >
          <Send className="mr-2 h-4 w-4" />
          {latest ? "Resubmit Claim" : "Submit Claim"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {isLoading && <p className="text-muted-foreground">Loading…</p>}
        {!isLoading && !latest && (
          <p className="text-muted-foreground">
            No claim submitted yet. Submitting bills this appointment&apos;s procedures to the
            patient&apos;s primary insurance.
          </p>
        )}
        {latest && (
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Status</span>
              <Badge variant={statusVariant(latest.status)}>{latest.status}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Total charge</span>
              <span>{centsToUsd(latest.totalChargeCents)}</span>
            </div>
            {latest.submissionErrors && latest.submissionErrors.length > 0 && (
              <ul className="mt-2 list-disc pl-5 text-destructive">
                {latest.submissionErrors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        {submit.isError && (
          <p className="text-destructive">
            Submission failed. Check that the practice NPI, tax ID, taxonomy, and clearinghouse
            credentials are configured, and that the appointment has procedures.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Mount the panel in AppointmentModal**

In `apps/web/components/scheduling/AppointmentModal.tsx`, import the panel and render it
directly after `<CopayEstimateCard appointmentId={appointment.id} />` (edit mode only),
following the existing guarded pattern:

```tsx
import { ClaimPanel } from "@/components/scheduling/ClaimPanel";
// ...
{isEditing && appointment && <ClaimPanel appointmentId={appointment.id} />}
```

- [ ] **Step 3: Build the claims worklist page**

Replace the placeholder `apps/web/app/(app)/billing/claims/page.tsx`, mirroring the table
pattern in `apps/web/app/(app)/treatment-plans/open/page.tsx` (PageHeader + 3-state render +
Table). Add a status `<select>` filter bound to `useClaimsList(status)`:

```tsx
"use client";

import { useState } from "react";

import { PageHeader } from "@/components/ui/page-header";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { useClaimsList, type ClaimStatus } from "@/lib/api/claims";

const STATUS_OPTIONS: (ClaimStatus | "")[] = [
  "",
  "submitted",
  "clearinghouse_rejected",
  "submission_failed",
  "paid",
  "denied",
];

export default function ClaimsPage() {
  const [status, setStatus] = useState<string>("");
  const { data: claims = [], isLoading } = useClaimsList(status || undefined);

  return (
    <div className="flex flex-col gap-6 p-6">
      <PageHeader title="Claims" description="Submitted insurance claims and their status." />

      <select
        className="w-56 rounded-md border border-border px-2 py-1 text-sm"
        value={status}
        onChange={(e) => setStatus(e.target.value)}
      >
        {STATUS_OPTIONS.map((s) => (
          <option key={s} value={s}>
            {s === "" ? "All statuses" : s}
          </option>
        ))}
      </select>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {!isLoading && claims.length === 0 && (
        <div className="rounded-lg border border-border py-16 text-center">
          <p className="text-sm text-muted-foreground">No claims.</p>
        </div>
      )}

      {!isLoading && claims.length > 0 && (
        <div className="rounded-lg border border-border">
          <Table>
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
                  <TableCell>{c.payerId}</TableCell>
                  <TableCell className="text-right">
                    ${(c.totalChargeCents / 100).toFixed(2)}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{c.status}</Badge>
                  </TableCell>
                  <TableCell>{c.submittedAt ? c.submittedAt.slice(0, 10) : "—"}</TableCell>
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

> Confirm the exact import paths for `PageHeader`, `Table*`, `Badge`, and the existing
> billing/claims placeholder path against the repo (the Explore report cited
> `app/(app)/billing/claims/page.tsx` as an existing placeholder and
> `components/ui/page-header`). Adjust imports to match.

- [ ] **Step 4: Type-check + lint**

Run from `apps/web/`: `pnpm type-check && pnpm lint`
Expected: no errors in the new/edited files.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/scheduling/ClaimPanel.tsx apps/web/components/scheduling/AppointmentModal.tsx "apps/web/app/(app)/billing/claims/page.tsx"
git commit -m "feat(7a): claim panel on appointment + claims worklist page"
```

---

## Task 13: Sandbox smoke script (manual, not in CI)

**Files:**
- Create: `apps/api/scripts/stedi_claim_smoke.py`

- [ ] **Step 1: Write the smoke script**

Mirror `apps/api/scripts/stedi_eligibility_smoke.py`. It builds a `DentalClaimInput` for a
Stedi dental sandbox test patient, submits with `usage_indicator="T"`, and prints the result.
Create `apps/api/scripts/stedi_claim_smoke.py`:

```python
"""Manual Stedi dental-claim sandbox smoke test. NOT run in CI.

Usage:
    source apps/api/.stedi-smoke.env   # exports STEDI_TEST_API_KEY
    python apps/api/scripts/stedi_claim_smoke.py

Verifies the real Stedi Dental Claims (837D) JSON endpoint path, payload shape, and the
synchronous 277CA response against a sandbox test claim (usageIndicator='T' — Stedi
processes but does not forward to a payer).
"""

import asyncio
import os
from datetime import date

from app.services.claims.base import ClaimLine, DentalClaimInput
from app.services.claims.stedi import StediClaimsClient


async def main() -> None:
    api_key = os.environ["STEDI_TEST_API_KEY"]
    claim = DentalClaimInput(
        patient_control_number="SMOKE0001",
        payer_id="CIGNA",            # adjust to the Stedi dental sandbox payer id
        usage_indicator="T",
        billing_npi="1999999984",    # Stedi sandbox billing NPI — confirm in Stedi docs
        billing_tax_id="123456789",
        billing_taxonomy_code="1223G0001X",
        billing_org_name="Downtown Dental",
        submitter_id="SUBMITTER",
        rendering_npi="1999999984",
        rendering_first_name="Jane",
        rendering_last_name="Dentist",
        subscriber_first_name="Jaguar",
        subscriber_last_name="Dent",
        subscriber_dob=date(1996, 5, 5),
        member_id="U3141592653",
        group_number=None,
        relationship_to_insured="self",
        patient_first_name="Jaguar",
        patient_last_name="Dent",
        patient_dob=date(1996, 5, 5),
        date_of_service=date.today(),
        lines=(
            ClaimLine(
                procedure_id="line-1", cdt_code="D0120", fee_cents=5000,
                tooth_number=None, surface=None, procedure_name="Periodic exam",
            ),
        ),
    )
    client = StediClaimsClient(api_key=api_key)
    result = await client.submit_dental_claim(claim, "smoke-claim-0001")
    print("accepted:", result.accepted)
    print("clearinghouse_claim_id:", result.clearinghouse_claim_id)
    print("status:", result.clearinghouse_status)
    print("errors:", result.errors)
    print("raw_response:", result.raw_response)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: (Manual, optional now) Note in the PR description**

This script is **not** run in CI and requires a Stedi sandbox key. It is the Staging
Checkpoint 5 verification artifact. Do not run it as part of this task unless a key is
available — just commit it.

- [ ] **Step 3: Commit**

```bash
git add apps/api/scripts/stedi_claim_smoke.py
git commit -m "chore(7a): Stedi dental-claim sandbox smoke script (manual)"
```

---

## Task 14: Docs — update roadmap + build order

**Files:**
- Modify: `longterm_build_plan.md`
- Modify: `docs/superpowers/specs/phase3-build-order.md`

- [ ] **Step 1: Mark Module 7a status in the roadmap**

In `longterm_build_plan.md` Phase 3 section, update the Module 7 line to reflect 7a built /
7b next, and add the deferred items from the spec §11 to the "Deferred Follow-Ups & Backlog"
table (async submit worker, DentalXChange prod client, 277CA/276/277 polling, MassHealth,
secondary/COB, multiple providers per appointment, claim_service_lines, attachments).

- [ ] **Step 2: Update the Phase 3 build-order table**

In `docs/superpowers/specs/phase3-build-order.md`, set the Module 7 row spec link to
`2026-06-18-module-7a-claims-submission-design.md` and note the 7a/7b split.

- [ ] **Step 3: Commit**

```bash
git add longterm_build_plan.md docs/superpowers/specs/phase3-build-order.md
git commit -m "docs(7a): roadmap + build-order — 7a built, 7b next, deferred items logged"
```

---

## Task 15: Full verification + finish

- [ ] **Step 1: Run the full backend test suite**

Run from `apps/api/`: `pytest && pytest -m integration`
Expected: all green (unit suite + integration suite). Investigate and fix any failure — do
not edit assertions to pass.

- [ ] **Step 2: Type-check backend + frontend**

Run: (`apps/api/`) `mypy app` and (`apps/web/`) `pnpm type-check`
Expected: no new errors introduced by 7a files.

- [ ] **Step 3: Finish the branch**

Use the superpowers:finishing-a-development-branch skill to open the PR for
`module-7a-claims-submission`. PR body should summarize: Stedi-JSON 837D submission (no raw
X12), synchronous slice, integer-cents money, deterministic idempotency, claims table +
panel + worklist, and the deferred list (7b ERA next).

---

## Self-review notes (addressed)

- **Spec coverage:** §3 layout → Tasks 2/3/4/5/6/7/9; §4 data model → Task 1; §5 data sources → Task 6 (+ service Task 7); §6 flow → Task 7; §7 validation → Task 4; §8 API → Task 9; §9 frontend → Tasks 11/12; §10 testing → Tasks 3–7,10 + smoke Task 13; §11 deferred → Task 14 docs.
- **Stedi external contract:** field names/endpoint flagged for doc + smoke verification (Task 5 note, Task 13); unit tests are URL-independent.
- **Verify-before-implement flags:** provider name attributes (Task 6), `Error.details` field (Task 9), `apiClient.post` body signature (Task 11), frontend import paths (Task 12), auth-patch constants + model kwargs (Tasks 7/10) — each called out inline so the implementer confirms against the real file rather than trusting the plan blind.
- **Type consistency:** `DentalClaimInput`/`ClaimLine`/`ClaimResult`/`ClearinghouseClient`/`ClaimSubmissionError` (Task 2) used identically in Tasks 5/6/7/10; `ClaimSubmissionPrereqError.code` set in Task 7 and branched in Task 9; PCN ≤20 enforced in Task 3 and validated in Task 4.
