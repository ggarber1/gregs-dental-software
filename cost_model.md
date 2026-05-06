# Molar — Running Cost Model

Last updated: 2026-05-05

All costs in USD/month unless noted. AWS costs are us-east-1 on-demand pricing.

---

## Base Infrastructure (per environment)

| Layer | Service | Cost |
|---|---|---|
| Networking | VPC, NAT Gateway, Flow Logs | ~$35 |
| Data | RDS PostgreSQL `db.t4g.small` + ElastiCache Redis | ~$34 |
| Compute | ECS Fargate (API + Web tasks), ALB | ~$50 |
| CDN + Security | WAF, CloudFront | ~$8 |
| Storage & messaging | S3, SQS | ~$3 |
| Auth & secrets | Cognito, SSM Parameter Store | ~$1 |
| Observability | CloudWatch, AWS Backup | ~$8 |
| **Total per environment** | | **~$139/mo** |

**Staging:** Torn down between dev sessions → ~$20/mo during active development.

**Running total (production + staging active dev):** ~$159/mo

---

## Feature Add-Ons

Costs added on top of base infrastructure as features are enabled.

### 4.1 Ambient Clinical Notes

| Item | Cost | Notes |
|---|---|---|
| Whisper EC2 `t3.medium` | ~$30/mo | Always-on, shared across all practices |
| Claude Haiku 4.5 (per note) | ~$0.002 | Prompt caching applied |

**Claude at scale:**

| Scale | Notes/month | Claude cost/month |
|---|---|---|
| 1 practice (dad) | ~600 | ~$1.20 |
| 10 practices | ~6,000 | ~$12 |
| 50 practices | ~30,000 | ~$60 |
| 100 practices | ~60,000 | ~$120 |

**4.1 fixed cost:** +$30/mo (EC2 flat, regardless of usage)
**4.1 variable cost:** ~$0.002/note

---

### 4.2A No-Show Risk Scoring (Rule-Based)

| Item | Cost | Notes |
|---|---|---|
| Risk scoring Lambda | ~$0/mo | Nightly batch, well within Lambda free tier |
| EventBridge rule | ~$0/mo | Negligible |

**4.2A cost:** ~$0/mo additional

---

### 4.2B No-Show Risk Scoring (ML Model) — Future

| Item | Cost | Notes |
|---|---|---|
| Monthly retrain Lambda | ~$1/mo | Longer-running but infrequent |
| S3 model artifact storage | ~$0/mo | Model file is ~50MB |
| SageMaker | $0 | Not used — retrain runs in Lambda |

**4.2B cost:** ~$1/mo additional (when built)

---

## Development Tooling

| Tool | Cost | Notes |
|---|---|---|
| Claude Code subscription | $100/mo | AI-assisted development — drops to $0 once product is shipping and paying |

---

## Variable Costs (scale with usage)

These are not AWS infrastructure — they scale per message/claim and must be factored into pricing tiers.

| Cost | Rate | 1 practice | 10 practices | 50 practices |
|---|---|---|---|---|
| Twilio SMS reminders | $0.0079/msg | ~$5/mo | ~$47/mo | ~$237/mo |
| Twilio SMS (extra high-risk reminders) | $0.0079/msg | ~$1/mo | ~$8/mo | ~$40/mo |
| SES email reminders | $0.0001/email | <$1/mo | <$1/mo | ~$1/mo |
| Claim.MD Unlimited (tiered by Tax ID count) | $120–$336/mo | $120 | $336 | ~$900 (est.) |
| Claim.MD attachments | $0.60/each | ~$15/mo | ~$150/mo | ~$750/mo |

---

## Total Monthly Cost by Phase

### Today (Phase 1 + 2, no AI features)

| Item | Cost |
|---|---|
| Production infrastructure | ~$139 |
| Staging (active dev) | ~$20 |
| Twilio SMS (1 practice) | ~$5 |
| Claude Code subscription | ~$100 |
| **Total** | **~$264/mo** |

### After 4.1 Ambient Notes ships

| Item | Cost |
|---|---|
| Production infrastructure | ~$139 |
| Whisper EC2 | ~$30 |
| Claude API (1 practice) | ~$1 |
| Staging | ~$20 |
| Twilio SMS (1 practice) | ~$5 |
| **Total** | **~$195/mo** |

### At 10 practices (Phase 4 features live)

| Item | Cost |
|---|---|
| Production infrastructure | ~$155 (slightly larger RDS) |
| Whisper EC2 | ~$30 |
| Claude API | ~$12 |
| Staging | ~$20 |
| Twilio SMS | ~$55 |
| **Total** | **~$272/mo** |

---

## Margin Model

Pricing target: **$349/mo per practice** (flat rate, all features included)

| Practices | Revenue | Total Infra + Variable | Gross Margin |
|---|---|---|---|
| 1 (dad) | $349 | ~$195 | **44%** |
| 5 | $1,745 | ~$230 | **87%** |
| 10 | $3,490 | ~$272 | **92%** |
| 25 | $8,725 | ~$350 | **96%** |
| 50 | $17,450 | ~$500 | **97%** |

Margins compress slightly vs. the old model once Whisper EC2 is added (it's a fixed $30 regardless of practice count), but recover quickly past 5 practices.

---

## Infrastructure Scaling Triggers

| Milestone | Change | Cost Impact |
|---|---|---|
| 10 practices | RDS `t4g.small` → `t4g.medium` | +$30/mo |
| 10 practices | ECS API second task | +$15/mo |
| 25 practices | RDS read replica for reporting | +$50/mo |
| 50 practices | ECS autoscaling, ElastiCache cluster mode | +$30/mo |
| 100 practices | Evaluate Aurora, PgBouncer, dedicated analytics DB | TBD |

---

## Pricing Decisions

### Current assumption: $349/mo flat

This is the midpoint of a rough $299–$399 range — not a researched number. Do not treat it as final.

### What we know

| Reference point | Price | Notes |
|---|---|---|
| Dad's current Eaglesoft bill | ~$380/mo | Eaglesoft + reminder add-on; no accurate co-pay calculation |
| Archy (flat-rate cloud PMS) | $299/mo | Marketed as saving $8k/year vs. incumbents; this is the floor |
| Dentrix Ascend (cloud) | $399–500/mo | Quote-based, not published; mid-size practice estimate |
| Curve Dental | Quote-based | Not published |

### Open pricing decisions

**1. Clearinghouse: Claim.MD**

Claim.MD plans (claim.md/pricing):

| Plan | Monthly fee | Includes | Overage |
|---|---|---|---|
| Basic | $30/mo | Nothing — pure pay-per-use | Claims $0.50, eligibility $0.30 |
| Small Volume | $60/mo | 100 combined claims + eligibility | Excess claims $0.30, eligibility $0.50 |
| **Unlimited** | **$120/mo** | **Unlimited claims + ERA, 1,000 eligibility checks** | Additional eligibility: $0.02 (Prime) / $0.10 (Non-Prime) |

**Decision: Unlimited plan.** Truly unlimited claims and ERA. Rendering provider count doesn't affect price.

**Pricing is tiered by number of billing providers (Tax IDs) — each practice = 1 Tax ID:**

| Billing providers (practices) | Claim.MD cost | Cost per practice |
|---|---|---|
| 1 | $120/mo | $120 |
| 2 | $150/mo | $75 |
| 10 | $336/mo | $33.60 |

Per-practice cost drops sharply at scale — much better than a flat per-practice fee.

**Eligibility checks:** 1,000/month included. At 2,000 checks the price is ~$140–$220/month (varies with billing provider count). Monitor once live but unlikely to be a significant cost for small practices.

**Attachments:** $0.60 each (X-rays, perio charts submitted with claims). Not all claims need attachments — estimate ~20–30% of claims for a typical practice.

**Revised margin model (Unlimited plan, tiered by Tax ID count):**

| Practices | Revenue ($349/mo) | Infra (shared) | Claim.MD (tiered) | Twilio | Gross Margin |
|---|---|---|---|---|---|
| 1 (dad) | $349 | ~$159 | ~$120 | ~$5 | **19%** |
| 2 | $698 | ~$162 | ~$150 | ~$10 | **54%** |
| 10 | $3,490 | ~$185 | ~$336 | ~$50 | **84%** |
| 25 | $8,725 | ~$240 | ~$600 (est.) | ~$125 | **90%** |
| 50 | $17,450 | ~$340 | ~$900 (est.) | ~$250 | **92%** |

Margins are still thin at 1 practice but recover very quickly — by 2 practices it's already 54%, and the tiered Claim.MD structure means margins at scale are much healthier than the flat per-practice assumption. The $25–50 range estimate for Claim.MD at 25–50 practices needs to be confirmed with their estimator.

Two structural options still worth deciding:
- **Option A:** Billing included in base price — clean, simple, good margins past practice 2
- **Option B:** Billing as a separate add-on tier — keeps base tier accessible to practices that don't submit claims electronically

**2. Per-provider vs. per-practice pricing?**
Most incumbents charge per provider or per seat. Flat-rate-per-practice is the disruptor play (Archy's angle) and simpler to sell to solo practices. Reconsider if multi-provider group practices become a target segment.

**3. What to charge dad?**
Options: full price (validates real willingness to pay), heavily discounted (fair given he's the test subject), or free (acceptable if treated as a development cost). Decide before onboarding.

### Decision needed before first external practice

Lock the pricing page before onboarding anyone beyond dad. At minimum decide:
- [ ] Base price
- [ ] Whether billing is a separate tier
- [ ] How to handle the clearinghouse variable cost in the margin model

---

## Costs Not Yet Estimated

| Item | When needed |
|---|---|
| Claim.MD overage eligibility checks (above 1,000/mo per practice) | Phase 3 billing — monitor once live |
| 4.3 AI insurance verification (Claude calls on ERA data) | Phase 4 |
| 4.5 Recall automation SMS volume | Phase 4 |
| React Native mobile build tooling (Expo, App Store fees) | Phase 5 |
| Patient portal hosting (separate subdomain/service) | Phase 5 |
