# Terraform Infrastructure — Open Questions

## Decided

### General
- **Environments:** Separate root configs (`environments/staging/`, `environments/production/`). No Terraform workspaces.
- **KMS:** One CMK per environment shared across RDS, S3, SSM. Key aliases distinguish purpose.

### Staging (side project optimisation)
- **NAT:** NAT instance (`t4g.nano` EC2) instead of managed NAT Gateway. Stoppable, ~$1/mo when running.
- **Staging lifecycle:** Manual start via `make staging-up` / `make staging-down`. Midnight Lambda checks if anything is running and shuts it down automatically (emails you if it had to stop something). No fixed schedule.
- **WAF:** Disabled in staging.
- **CloudFront:** Disabled in staging. Hit ALB directly.
- **ElastiCache in staging:** Deleted on `staging-down`, recreated on `staging-up` via `terraform destroy/apply -target=module.elasticache`. Adds ~5 min to startup but saves $12/mo. Total staging cost ~$3/mo at 10hrs/week.
- **Production:** Don't spin up until dad is actually onboarding. Until then staging is effectively prod. When ready, `cd environments/production && terraform apply` builds the identical stack in minutes.
- **Bootstrap (one-time, do now):** Create S3 state bucket + DynamoDB lock table by hand. One bucket serves both staging and prod state files. Everything else waits.

### HTTPS / TLS
- **ACM cert is conditional on `var.domain_name`.** When empty (default): ALB has HTTP-only listener — no cert created, staging works immediately. When set: ACM cert + HTTPS listener + HTTP->HTTPS redirect created automatically. No domain picked yet — leave as empty default until ready.

### Networking
- **NAT Gateway:** Single NAT Gateway per environment (not per-AZ). AZ outages are rare and brief; consequence for a dental practice is acceptable. Revisit if SLA requirements change.

### Data layer
- **RDS instances:** Separate instance per environment (staging + production). Prevents a bad migration in staging from touching prod data.
- **RDS instance class:** `db.t4g.micro` for staging and initial production.
- **RDS Multi-AZ:** Single AZ for MVP. Restore from automated backup if catastrophic failure. Revisit when SLA requirements change.
- **ElastiCache:** Single node (`cache.t4g.micro`). Cluster mode not needed for MVP scale.

### Compute
- **Workers:** `reminder-worker`, `eligibility-worker`, `era-worker` -> Lambda with SQS triggers (not Fargate). Pay per invocation, scale to zero, simpler ops. Fargate only for `api` and `web`.
- **Lambda runtime:** Python 3.12 (matches API).
- **ECS task sizing (MVP, no autoscaling):**
  - `api`: 512 CPU / 1024 MB
  - `web`: 256 CPU / 512 MB

### Alerts
- **SNS email target:** Single personal email for all alarms and staging-lifecycle notifications.

### Offline / local agent
- **Model:** Cloud-primary, local hot standby. Local agent runs on the practice's existing front desk PC (Docker: FastAPI + Postgres). UI detects connectivity and switches API target automatically.
- **Sync primitive:** Transactional outbox pattern. Every mutation writes to a local outbox table first. Agent drains outbox to AWS on reconnect. Idempotency keys prevent duplicate replay.
- **UI offline:** PWA service worker caches app shell on first load. App loads from cache when internet is down. Staff see a small "working offline" banner; otherwise identical experience.
- **External calls offline:** Twilio, clearinghouse, eligibility checks queue in SQS and drain when connectivity restores.
- **Conflicts:** Last-write-wins on timestamp. Acceptable for single front-desk operator model.
- **Local agent is a LAN service, not browser storage.** All devices at the practice point at it by local IP. Browser-local storage (IndexedDB) is not used — wrong device = empty cache.
- **Connectivity detector:** UI tries AWS first, falls back to `LOCAL_AGENT_URL` (e.g. `http://192.168.1.50:8000`) configured per practice.
- **Onboarding step (Phase 2):** Install local agent via Docker on one machine, assign static local IP, enter address in practice settings. UI picks it up automatically.
- **Schema:** `practices.local_agent_url` field needed from day one (1.6).
- **Phase split:**
  - Phase 1: cloud-only. Design for offline from the start — outbox table in 1.6 schema, `local_agent_url` in practices table, connectivity-aware API client in 1.5.
  - Phase 2: build and ship local agent + service worker app shell caching.

---

## Pending

### 1. Domain name
Leave as `var.domain_name` placeholder in Terraform until ready. Defaults to `""` — ALB runs HTTP-only until set.
