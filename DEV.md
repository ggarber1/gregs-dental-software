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

### Cognito setup (required for auth)

The web app uses Amplify Auth (SRP) to sign in directly against a Cognito User Pool — no hosted UI, no OAuth redirects, no client secret needed.

1. Create a **User Pool** in the AWS Console:
   - **Sign-in**: email
   - **MFA**: optional for local dev (staging enforces TOTP)
   - **Self-registration**: disabled (admin creates users only)
   - **Custom attributes**: `custom:practice_id` (String), `custom:role` (String)

2. Under **App clients**, create an app client:
   - **Client secret**: disabled (not needed for SRP)
   - **Auth flows**: `ALLOW_USER_SRP_AUTH`, `ALLOW_REFRESH_TOKEN_AUTH`
   - No OAuth / hosted UI configuration needed

3. Create a test user in the console (or via CLI):
   ```bash
   aws cognito-idp admin-create-user \
     --user-pool-id <pool-id> \
     --username you@example.com \
     --temporary-password TempPass123!
   ```

4. Populate `.env`:
   ```bash
   # API — server-side JWT validation
   COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX
   COGNITO_CLIENT_ID=<app-client-id>
   COGNITO_REGION=us-east-1

   # Web — client-side Amplify Auth (same values, NEXT_PUBLIC_ prefix)
   NEXT_PUBLIC_COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX
   NEXT_PUBLIC_COGNITO_CLIENT_ID=<app-client-id>
   NEXT_PUBLIC_COGNITO_REGION=us-east-1
   ```

**Note:** The staging Cognito pool (provisioned by Terraform) has TOTP MFA enforced. For easier local dev, set MFA to optional on your personal dev pool.

---

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

# Run JS tests
pnpm --filter @dental/web test

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

---

## Terraform — AWS Infrastructure

### First-time bootstrap (one-time, do by hand)

MAKE SURE IN CORRECT AWS CONFIG

Before running any Terraform, create the state backend manually:

```bash
# Create S3 state bucket (already created: greg-dental-terraform-state)
aws s3api create-bucket \
  --bucket greg-dental-terraform-state \
  --region us-east-1

aws s3api put-bucket-versioning \
  --bucket dental-terraform-state \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket dental-terraform-state \
  --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"aws:kms"}}]}'

# Create DynamoDB lock table
aws dynamodb create-table \
  --table-name dental-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

Then initialise Terraform:

```bash
cd infra/terraform/environments/staging
terraform init
```

---

### First apply (staging)

**Step 1 — Create a tfvars file (gitignored, never commit this):**

```bash
cat > infra/terraform/environments/staging/terraform.tfvars <<EOF
alert_email = "your@email.com"
db_password = "$(openssl rand -hex 16)"
EOF
```

**Step 2 — Init and apply:**

```bash
cd infra/terraform/environments/staging
terraform init
terraform plan   # read the output carefully — ~50 resources on first apply
terraform apply
```

**Step 3 — Populate SSM parameters from outputs:**

After apply, Terraform creates placeholder SSM parameters. Replace them with real values:

```bash
# Get values from terraform outputs
RDS_ENDPOINT=$(terraform output -raw rds_endpoint)
REDIS_ENDPOINT=$(terraform output -json | jq -r '.elasticache_endpoint.value // empty' 2>/dev/null || echo "run make staging-up first")
USER_POOL_ID=$(terraform output -raw cognito_user_pool_id)
APP_CLIENT_ID=$(terraform output -raw cognito_app_client_id)

# Populate SSM (run from infra/terraform/environments/staging)
aws ssm put-parameter --name /dental/staging/db/url \
  --value "postgresql://dental_admin:YOUR_DB_PASSWORD@${RDS_ENDPOINT}/dental" \
  --type SecureString --overwrite

aws ssm put-parameter --name /dental/staging/redis/url \
  --value "redis://${REDIS_ENDPOINT}:6379" \
  --type SecureString --overwrite

aws ssm put-parameter --name /dental/staging/cognito/user_pool_id \
  --value "${USER_POOL_ID}" --type String --overwrite

aws ssm put-parameter --name /dental/staging/cognito/app_client_id \
  --value "${APP_CLIENT_ID}" --type String --overwrite

# API URL — the public-facing URL of the FastAPI ALB (used by the browser to call the API).
# The deploy workflow reads this from SSM and bakes it into the Next.js bundle at build time.
aws ssm put-parameter --name /dental/staging/app/api_url \
  --value "https://api.staging.yourdomain.com" \
  --type String --overwrite

# Twilio — set when building Module 4 (reminders). Leave as placeholder until then.
# aws ssm put-parameter --name /dental/staging/twilio/account_sid \
#   --value "ACxxx" --type SecureString --overwrite
# aws ssm put-parameter --name /dental/staging/twilio/auth_token \
#   --value "xxx" --type SecureString --overwrite
# aws ssm put-parameter --name /dental/staging/twilio/phone_number \
#   --value "+1xxxxxxxxxx" --type SecureString --overwrite

# Clearinghouse — set when building Module 5/7 (eligibility/claims). Leave as placeholder until then.
# aws ssm put-parameter --name /dental/staging/clearinghouse/api_key \
#   --value "xxx" --type SecureString --overwrite

# Generate a random secret key for the API
aws ssm put-parameter --name /dental/staging/app/secret_key \
  --value "$(openssl rand -hex 32)" --type SecureString --overwrite
```

**Step 4 — Bring staging up:**

```bash
# Run from repo root
make staging-up
```

Staging is now live. The ALB DNS name is printed at the end.

**Step 5 — Verify everything is healthy:**

```bash
# Run from repo root — checks every layer and prints OK / FAIL / NEEDS POPULATING
make staging-verify
```

Fix anything marked `FAIL` or `NEEDS POPULATING` before moving on. The SSM population commands are in Step 3 above.

> The ElastiCache endpoint is only available after `make staging-up` runs (it's
> destroyed when staging is down). Run `make staging-up` before populating the
> redis/url SSM parameter.

---

### Safe daily workflow

```bash
cd infra/terraform/environments/staging

# 1. See exactly what will change — read this carefully
terraform plan

# 2. Only once you're happy with the plan
terraform apply
```

**Never run `terraform apply` without reviewing `plan` output first.**

---

### Staging start / stop

```bash
make staging-up    # starts RDS, ElastiCache, NAT instance, ECS (~3 min to be ready)
make staging-down  # stops everything manually
```

A midnight Lambda shuts down anything left running and emails you if it had to stop something.

---

### Working on production

Production is not provisioned until dad is onboarding. When ready:

```bash
cd infra/terraform/environments/production
terraform init
terraform plan    # review carefully — this is real infra
terraform apply
```

**Never run `terraform destroy` on production without an explicit decision.**

---

### Environment state files

| Environment | State file |
|---|---|
| Staging | `s3://dental-terraform-state/staging/terraform.tfstate` |
| Production | `s3://dental-terraform-state/production/terraform.tfstate` |

Staging and production are fully independent. Destroying staging has zero effect on production.

---

### CI / CD

**CI** runs automatically on every PR and push to `main`:
- Python: ruff, mypy, pytest
- Node: ESLint, tsc

**Deploying** is always manual — trigger from the GitHub Actions tab:
- `Deploy Staging` — use when staging is up (`make staging-up` first)
- `Deploy Production` — use when you're ready to ship

Both workflows build Docker images, push to ECR, run `alembic upgrade head` as a one-off ECS task, deploy the services, and wait for stability. If the migration exits non-zero the deploy stops.

**Before triggering the first deploy on a new environment**, all SSM parameters must be populated (the deploy workflow reads Cognito IDs and the API URL from SSM at build time and bakes them into the Next.js bundle):

1. Run `terraform apply` to create the SSM placeholders and grant the GitHub Actions role SSM read access
2. Populate the required parameters (see Step 3 of "First apply" above for the full list)
3. Bring the environment up: `make staging-up`
4. Then trigger the deploy from GitHub Actions

If SSM parameters still contain `placeholder` values when the deploy runs, the web container will ship with missing Cognito config and Amplify Auth will fail on every page load.

**One-time setup** (after first `terraform apply` on a new account):
```bash
# Add this as a GitHub Actions secret called AWS_ACCOUNT_ID
aws sts get-caller-identity --query Account --output text
```
Subnet and SG IDs are looked up at deploy time from EC2 tags — nothing else to configure.

**`terraform apply`:** Always manual, never automated in CI.
