# Dev Reference

## Prerequisites

- Node.js >= 20
- pnpm >= 9: `npm install -g pnpm`
- Python 3.12: `brew install python@3.12`
- uv: `brew install uv`
- Docker Desktop

## First-time setup

```bash
pnpm install                        # install JS dependencies
cd apps/api && uv sync && cd ../..  # install Python dependencies + create lockfile
cp .env.example .env                # fill in any local overrides if needed
```

## Daily dev

```bash
docker compose up                   # start everything (postgres, redis, localstack, api, web)
docker compose up postgres redis    # start just the data services (if running api/web locally)
```

API: http://localhost:8000
API docs (dev only): http://localhost:8000/docs
Web: http://localhost:3000

## Running api/web outside Docker

```bash
# API
cd apps/api
uv run uvicorn app.main:app --reload --port 8000

# Web
cd apps/web
pnpm dev
```

## Codegen (Zod → Pydantic)

Run whenever you change anything in `packages/shared-types/src/schemas/`:

```bash
pnpm generate
```

This regenerates `apps/api/app/schemas/generated.py`.

## Build (production)

```bash
pnpm build      # builds all packages in dependency order
```

## Useful one-liners

```bash
# Lint all packages
pnpm lint

# Type-check all packages
pnpm type-check

# Run a command in a specific package
pnpm --filter @dental/web dev
pnpm --filter @dental/shared-types build

# Python linting
cd apps/api && uv run ruff check .
cd apps/api && uv run ruff format .
cd apps/api && uv run mypy app/

# Reset local DB (nuclear)
docker compose down -v && docker compose up postgres
```

## Database migrations (Alembic — set up in 1.4)

```bash
cd apps/api
uv run alembic upgrade head          # apply all migrations
uv run alembic revision --autogenerate -m "description"  # create new migration
uv run alembic downgrade -1          # roll back one
```

## LocalStack (local AWS)

```bash
# Check what's been created
AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test \
  aws --endpoint-url http://localhost:4566 s3 ls

AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test \
  aws --endpoint-url http://localhost:4566 sqs list-queues
```

## Adding a new shared-types schema

1. Add Zod schema in `packages/shared-types/src/schemas/`
2. Export it from `packages/shared-types/src/index.ts`
3. Run `pnpm generate` to regenerate Pydantic models
4. Import the Pydantic model in the API from `app.schemas.generated`
