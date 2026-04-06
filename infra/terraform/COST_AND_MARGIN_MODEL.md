# Infrastructure Cost & Margin Model

## Per-Environment Infrastructure Cost

| Layer | Cost |
|---|---|
| Networking (VPC, NAT Gateway, Flow Logs) | ~$35/mo |
| Data (RDS PostgreSQL + ElastiCache Redis) | ~$34/mo |
| Compute + routing (ECS Fargate, ALB, WAF, CloudFront) | ~$50/mo |
| Storage & messaging (S3, SQS) | ~$3/mo |
| Auth & secrets (Cognito, SSM) | ~$1/mo |
| Observability (CloudWatch, AWS Backup) | ~$8/mo |
| **Total per environment** | **~$131/mo** |
| **Staging + Production (staging always-on)** | **~$262/mo** |

> Staging can be torn down between dev sessions, reducing it to ~$20/mo while building. Real cost during active development: ~$151/mo.

---

## Margin Model (pricing at $349/mo average)

| Practices | Revenue | Prod Infra | Staging | Total Infra | Gross Margin |
|---|---|---|---|---|---|
| 1 (dad) | $349 | ~$131 | ~$20 | ~$151 | **57%** |
| 5 | $1,745 | ~$150 | ~$20 | ~$170 | **90%** |
| 10 | $3,490 | ~$175 | ~$20 | ~$195 | **94%** |
| 25 | $8,725 | ~$220 | ~$20 | ~$240 | **97%** |
| 50 | $17,450 | ~$320 | ~$20 | ~$340 | **98%** |

Margins get healthy at 5 practices. Infrastructure is largely fixed — revenue scales, infra barely moves.

---

## How Prod Infrastructure Grows

**1–10 practices:** Almost nothing changes. Same RDS instance, Lambda absorbs worker load.

**10–25 practices:** 
- RDS instance size up: `db.t4g.small` → `db.t4g.medium` (~$30 → ~$60/mo)
- ECS `api` second task instance (~+$15/mo)

**25–50 practices:**
- RDS read replica for reporting queries
- ECS autoscaling
- Possibly ElastiCache cluster mode

**50+ practices:** Multi-region, PgBouncer connection pooling, CDN tuning. At this point revenue ($17k+ MRR) makes infra spend a rounding error.

---

## Variable Costs to Watch (not AWS infra)

These scale with usage and should be factored into pricing tiers:

| Cost | Rate | Example at 50 practices |
|---|---|---|
| Twilio SMS | ~$0.0079/message | 50 practices × 20 reminders/day × 30 days = ~$237/mo |
| Clearinghouse (DentalXChange) | ~$0.25–0.45/claim | Depends on claim volume — consider per-claim fee or billing module tier |

---

## Pricing Notes

- Current target: $299–$399/month flat
- Modules 5/6/7 (insurance, co-pay, claims) are opt-in — consider a higher tier ($399+) for practices that enable billing features, to cover clearinghouse transaction costs
- Don't race to the bottom on pricing — 90%+ gross margins at 5 practices is a good business
