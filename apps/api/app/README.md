# API App — Dental PMS Backend

FastAPI-based REST API backend for a multi-tenant dental practice management system.

---

## Directory Structure

```
app/
├── main.py                  # Application factory and entry point
├── core/
│   ├── config.py            # Settings (env vars, AWS, Cognito, encryption)
│   ├── db.py                # Async SQLAlchemy engine and session management
│   └── redis.py             # Redis async client singleton
├── middleware/
│   ├── security.py          # HIPAA-aligned security response headers
│   ├── auth.py              # Cognito JWT authentication + practice scoping
│   ├── audit.py             # PHI access audit logging (insert-only)
│   └── idempotency.py       # Redis-backed idempotency for mutations
├── models/
│   ├── base.py              # SQLAlchemy base and shared column mixins
│   ├── user.py              # User + PracticeUser (multi-tenant junction)
│   ├── practice.py          # Practice (the tenant entity)
│   ├── provider.py          # Provider (dentists, hygienists, etc.)
│   ├── operatory.py         # Treatment rooms / operatories
│   └── audit_log.py         # Append-only PHI audit trail
└── schemas/
    ├── generated.py         # Auto-generated Pydantic models from schemas.json
    └── __init__.py          # Hand-written schema extensions (currently empty)
```

---

## Entry Point

### `main.py`

The application factory. Calls `create_app()` which returns a fully configured FastAPI instance.

**Responsibilities:**
- Manages DB and Redis connection lifecycle via FastAPI lifespan hooks
- Registers the middleware stack in order (see Middleware section)
- Mounts CORS with configurable allowed origins
- Exposes `/health` — validates both DB and Redis connectivity
- Swagger/ReDoc docs only enabled in development

---

## Core

### `core/config.py`

Pydantic Settings class loaded from environment variables / `.env`. Retrieved via a cached singleton `get_settings()`.

| Category | Key Fields |
|---|---|
| App | `api_env`, `api_port`, `api_cors_origins` |
| Database | `database_url`, `async_database_url` (auto-derived) |
| Redis | `redis_url` |
| AWS | `aws_region`, `aws_endpoint_url`, S3 bucket names, SQS queue names |
| Cognito | `cognito_user_pool_id`, `cognito_client_id`, `cognito_region` |
| Encryption | `app_encryption_key` (32-byte base64, used for AES-256 PHI encryption) |

Helper properties: `is_development`, `is_production`.

---

### `core/db.py`

Async SQLAlchemy connection management. All functions are lazy-initialized singletons.

| Export | Purpose |
|---|---|
| `get_engine()` | Returns `AsyncEngine` with pool_size=10, max_overflow=20 |
| `get_session_factory()` | Returns `async_sessionmaker` |
| `get_db()` | Async generator for route dependency injection |
| `dispose_engine()` | Graceful shutdown; resets singleton state |

Pool pre-ping is enabled. Sessions are created with `expire_on_commit=False` to avoid lazy-load issues in async contexts.

---

### `core/redis.py`

Lazy-initialized async Redis client.

| Export | Purpose |
|---|---|
| `get_redis()` | Returns singleton `redis.asyncio.Redis` client |
| `close_redis()` | Graceful shutdown |

Configured with 2-second connect/read timeouts and auto string decoding.

---

## Middleware

Middleware is applied in the following order (outermost to innermost):

```
Request →  SecurityHeaders → CognitoAuth → AuditLog → Idempotency → Route Handler
Response ←                                                                         ←
```

---

### `middleware/security.py` — `SecurityHeadersMiddleware`

Applied first (outermost), ensuring headers appear on all responses including errors.

HIPAA-aligned headers added to every response:

| Header | Value |
|---|---|
| `Strict-Transport-Security` | 2-year max-age, includeSubDomains |
| `X-Content-Type-Options` | nosniff |
| `X-Frame-Options` | DENY |
| `Referrer-Policy` | no-referrer |
| `Cache-Control` | no-store |
| `Content-Security-Policy` | Restrictive policy, inline styles only |

---

### `middleware/auth.py` — `CognitoAuthMiddleware`

JWT authentication via AWS Cognito. Populates `request.state.user` on success.

**Public paths** (no auth required): `/health`, `/intake/*`

**Flow:**
1. Extract Bearer token from `Authorization` header
2. Validate signature using JWKS (fetched from Cognito, cached 1 hour, embedded at build time as fallback)
3. Verify `aud` claim matches configured `cognito_client_id`
4. If `X-Practice-ID` header present, look up `PracticeUser` membership in DB
5. Return 403 if user is not active in the requested practice

**`AuthenticatedUser`** (attached to `request.state.user`):

```python
sub: str           # Cognito subject (stable identity)
email: str
user_id: UUID      # Internal user ID
practice_id: UUID  # Active practice scope
role: str          # admin | provider | front_desk | billing | read_only
groups: list[str]  # Cognito groups
```

Returns `401` for invalid/missing tokens, `503` for auth service failures.

---

### `middleware/audit.py` — `AuditLogMiddleware`

Fire-and-forget async task that records every PHI-touching request. Failures are logged but never block the response.

**Skipped paths:** `/health`, `/docs`, `/redoc`, `/openapi.json`

**Fields recorded:** `practice_id`, `user_id` (Cognito sub), `action` (HTTP method), `path`, `resource_type`, `resource_id` (parsed from URL), `ip_address`, `user_agent`, `status_code`, `timestamp`.

URL parsing strips `/api/v1/` prefix — e.g. `/api/v1/patients/abc-123` → `resource_type=patients`, `resource_id=abc-123`.

---

### `middleware/idempotency.py` — `IdempotencyMiddleware`

Enforces idempotent mutations using Redis. Prevents duplicate side effects from retried requests.

**Applies to:** `POST`, `PATCH`, `PUT`, `DELETE`

**Behavior:**

| Scenario | Result |
|---|---|
| Missing `Idempotency-Key` header | `422 Unprocessable Entity` |
| Key seen before | Returns cached response with `X-Idempotent-Replayed: true` |
| New key, 2xx/4xx response | Caches for 24 hours |
| New key, 5xx response | Not cached (transient errors should be retried) |

Cache key format: `idempotency:{practice_id}:{idempotency_key}` — scoped per practice to prevent cross-tenant collisions. Redis failures degrade gracefully.

---

## Models

All models extend `Base` (SQLAlchemy `DeclarativeBase`) from `models/base.py`.

### Mixins (`models/base.py`)

| Mixin | Adds |
|---|---|
| `UUIDMixin` | UUID primary key `id` |
| `TimestampMixin` | `created_at`, `updated_at`, `deleted_at` (soft delete) |
| `PHIMixin` | Timestamps + `last_accessed_by`, `last_accessed_at` |

---

### `models/practice.py` — `Practice`

The central tenant entity. Every other data table is scoped to a `practice_id`.

Key fields: `name`, `phone`, `timezone`, full address, `features` (JSONB feature flags), clearinghouse config (`stedi` or `dentalxchange`), billing identifiers (`billing_npi`, `billing_tax_id_encrypted`, `billing_taxonomy_code`).

`billing_tax_id_encrypted` is stored as `BYTEA` — encrypted at the application layer with AES-256.

**Feature flags** (via `features` JSONB) gate optional modules:
- `eligibility_verification`
- `copay_estimation`
- `claims_submission`

---

### `models/user.py` — `User` + `PracticeUser`

`User` represents any system login. `cognito_sub` is the stable identity anchor joining Cognito to internal records.

`PracticeUser` is the multi-tenant junction table. A user can belong to multiple practices with different roles per practice.

**Roles** (enforced by DB CHECK constraint): `admin`, `provider`, `front_desk`, `billing`, `read_only`

Composite PK on `(practice_id, user_id)`. Includes `is_active` per membership for per-practice deactivation.

---

### `models/provider.py` — `Provider`

Dental providers within a practice (dentists, hygienists, specialists).

Key fields: `practice_id`, `user_id` (nullable — not all providers have logins), `npi`, `provider_type`, `license_number`, `specialty`, `color` (hex, for calendar), `display_order`.

Composite index on `(practice_id, is_active)` for scheduling queries. NPI is required for 837D claim generation.

---

### `models/operatory.py` — `Operatory`

Physical treatment rooms within a practice. Used for room-view scheduling.

Key fields: `practice_id`, `name`, `color` (hex), `is_active`, `display_order`.

Composite index on `(practice_id, is_active)`.

---

### `models/audit_log.py` — `AuditLog`

Append-only HIPAA audit trail. The database user has INSERT-only privileges; a Postgres trigger prevents `UPDATE`/`DELETE`.

**Do not add update or delete methods to this model.**

Fully denormalized (no foreign keys) to preserve immutability. Composite index on `(practice_id, timestamp)`.

---

## Schemas

### `schemas/generated.py`

Auto-generated Pydantic models produced by `datamodel-codegen` from `schemas.json` (source of truth). Run `pnpm generate` to regenerate.

Key exports:

| Category | Models |
|---|---|
| Enums | `Role`, `Sex` |
| Practice | `Practice`, `CreatePractice`, `Features` |
| Provider | `Provider`, `CreateProvider` |
| Operatory | `Operatory`, `CreateOperatory` |
| Patient (PHI) | `Patient`, `CreatePatient`, `UpdatePatient` |
| Pagination | `PaginationQuery`, `PaginationMeta`, `PatientSearchQuery` |
| Errors | `Error`, `ApiError` |

All models use `ConfigDict(extra='forbid')` and field aliases for camelCase ↔ snake_case conversion.

### `schemas/__init__.py`

Location for hand-written schemas that extend or compose generated models. Currently empty.

---

## Design Notes

**Multi-tenancy:** All data is scoped to `practice_id`. The auth middleware enforces practice isolation by validating `X-Practice-ID` against the user's active memberships.

**Graceful degradation:** Redis failures (idempotency, caching) and audit log failures never block API responses — they log and continue.

**PHI encryption:** Sensitive billing fields (tax IDs) are encrypted at the application layer with AES-256 before persisting to the database.

**Soft deletes:** All entities include `deleted_at`; hard deletes are never performed to preserve audit history.

**Schema generation:** `schemas/generated.py` is not hand-edited. Extend in `schemas/__init__.py` or add new fields to `schemas.json` and regenerate.
