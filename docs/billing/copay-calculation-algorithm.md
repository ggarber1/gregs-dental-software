# Co-pay / Patient-Responsibility Calculation Algorithm

Canonical written explanation of the Module 6 co-pay engine
(`apps/api/app/services/copay/engine.py`). The engine is a **pure function** — no
I/O, no DB, no clock — so it can be exhaustively unit-tested. All money is integer
cents; `Decimal` is used only for the coinsurance percentage and rounded to whole
cents exactly once per line item.

Implementation: `apps/api/app/services/copay/engine.py`
Inputs/outputs: `apps/api/app/services/copay/models.py`
Tests (19 scenarios): `apps/api/tests/services/test_copay_engine.py`
Source research: `research/14_module6_copay_calculation.md`

---

## The accounting identity

Every line item must satisfy, exactly:

```
provider_fee_cents == write_off_cents + patient_owes_cents + insurance_owes_cents
```

The totals re-assert it. This is the engine's primary correctness backstop — every
test calls `_assert_identity`. Because rounding happens once per line (see below), a
violation is a real bug, not rounding drift.

---

## Dispatch by plan type

`calculate_patient_responsibility(snapshot, procedures, service_date)` dispatches on
`snapshot.plan_type`:

- **`ppo` / `premier` / `indemnity`** → the standard pipeline (OON is a branch inside,
  keyed on `network_status`).
- **`medicaid`** → the Medicaid pipeline (patient owes $0 on covered procedures).
- **`dhmo` / anything else** → every line flagged `needs_manual_entry` (DHMO fixed-copay
  schedules are a deferred slice — see "Deferred").

---

## Standard pipeline (PPO / Premier / Indemnity)

Procedures are first **sorted** by `CATEGORY_ORDER`
(`preventive → diagnostic → basic → major → ortho → other`) so the running
deductible/annual-max state is consumed deterministically: preventive/diagnostic
first (usually deductible-waived), then basic before major per industry convention.

Two running counters thread across the sorted line items: `deductible_remaining` and
`annual_max_remaining` (plus `ortho_lifetime_remaining` for ortho). Per procedure:

### 1. Allowed amount, write-off, balance bill

- `allowed = allowed_amount_cents` if the contracted-fee table returned one, else the
  provider's billed fee.
- **In-network:** `effective = min(fee, allowed)` (an in-network provider can't collect
  above the billed fee), and `write_off = max(0, fee − allowed)`.
- **Out-of-network:** `write_off = 0`, the coinsurance is computed on the allowed/UCR
  amount, and the `fee − allowed` gap becomes the patient's **balance bill**.

### 2. Short-circuit gates (insurance pays $0; patient owes the effective amount + any balance bill)

Checked in order; the first match short-circuits the line:

- **`not_covered`** (from the contracted-fee table).
- **Waiting period active** — `coverage_start_date + waiting_period_months[category] >
  service_date`. A waiting period of `0`/null months means no wait; this is also how
  "waived for prior continuous coverage" is represented (the parser sets the months to
  `0`). No separate `waived` flag.
- **Frequency exceeded** — `frequency_used_count >= frequency_limit_count`. (See the
  frequency note below.)
- **Coinsurance unknown** — neither the per-CDT-code 271 map nor the per-category
  fallback yielded a rate. The line is flagged `needs_manual_entry`; the engine does
  **not** guess.

### 3. Deductible

If `category` is not in `deductible_waived_categories`:
`applied = min(deductible_remaining, effective)`; decrement `deductible_remaining`;
`amount = effective − applied`.

### 4. Coinsurance split (the only `Decimal` math)

```
gross_insurance = round_half_up(amount × (1 − patient_share))   # rounded once, here
patient_coins   = amount − gross_insurance                       # exact complement
```

`patient_coins` is the integer complement, never separately rounded, so no cent leaks.

### 5. Annual-max / ortho-lifetime cap

Ortho procedures draw the **separate `ortho_lifetime_max` bucket** when the plan
returned one; every other category draws the **annual max**. (If no ortho lifetime max
was returned, ortho falls back to the annual max.)

```
cap     = ortho_lifetime_remaining (ortho w/ a lifetime max) else annual_max_remaining
capped  = min(gross_insurance, cap)            # cap == None ⇒ no cap
overflow = gross_insurance − capped            # overflow goes to the patient
<decrement the bucket that was used>
insurance_owes = capped
```

`annual_max_cap_applied` is set when a cap reduced the insurance payment.

### 6. Line total

```
patient_owes = deductible_applied + patient_coins + overflow + balance_bill
```

---

## Worked examples (from the test suite)

**Basic filling, fresh deductible** (`test_scenario2_...`): fee $200, allowed $180, 20%
patient, $50 deductible. write-off $20; deductible $50; insurance `round(130 × 0.80)` =
$104; patient `$50 + $26` = $76. Identity: 20 + 76 + 104 = 200. ✓

**Annual max exhausted** (`test_scenario4_...`): major, allowed $800, 50/50, annual-max
remaining $200. gross insurance $400 → capped $200, overflow $200 → patient. patient
`$400 coinsurance + $200 overflow` = $600. Identity: 0 + 600 + 200 = 800. ✓

**OON balance billing** (`test_scenario12_...`): fee $1400, allowed/UCR $900, 50%,
deductible met. write-off $0; insurance `$900 × 0.50` = $450; patient `$450 coinsurance +
$500 balance bill` = $950. Identity: 0 + 950 + 450 = 1400. ✓

**Ortho lifetime bucket** (`test_ortho_draws_lifetime_bucket_not_annual_max`): ortho,
allowed $3000, 50%, ortho lifetime remaining $1500, annual max $2000. insurance $1500
(fits the lifetime cap), patient $1500, **annual max untouched** ($2000 remains). ✓

**Deductible split across two procedures** (`test_scenario7_...`): $50 deductible, two
basic procedures — $30 applied to the first, $20 to the second; deductible exhausted.

---

## Medicaid pipeline

`patient_owes = 0` on covered procedures; `insurance_owes = allowed`;
`write_off = max(0, fee − allowed)`. `not_covered` codes (e.g. adult implants) → patient
owes the allowed amount, insurance $0. `requires_prior_auth` is surfaced for Module 7 to
gate claim generation. No deductible/coinsurance/annual-max.

---

## Coinsurance resolution (in the service, not the engine)

`CopayService` resolves each procedure's `coinsurance_patient_share` before calling the
engine: the per-CDT-code map parsed from the 271 (`coinsurance_by_code[code]`) → the
per-category fallback field (`coinsurance_<category>`) → `None` (→ `needs_manual_entry`).
The per-code map is the faithful path; real dental 271s return coinsurance per procedure
code, not by category.

## Frequency note (best-effort until claims exist)

`frequency_used_count` is counted from completed `appointment_procedures` history this
calendar year (excluding the current appointment), because paid-claims history does not
exist until Module 7/8. The UI labels the result an **estimate, not a guarantee of
payment**. The engine logic is final; only the input count improves once claims land.

## Rounding

`ROUND_HALF_UP` to whole cents, applied once per line to `gross_insurance`; the patient
coinsurance is the integer complement. Never round intermediate values.

---

## Deferred (not implemented here)

- **DHMO (capitation)** fixed-copay schedules — `plan_type='dhmo'` currently flags every
  line for manual entry.
- **Alternate-benefit / downgrade** (e.g. posterior composite D2394 → amalgam D2161): the
  carrier pays against the cheaper procedure's allowed amount and the gap between the two
  allowed amounts is patient responsibility (NOT a write-off). Research example (`§5`):
  composite fee $300 / allowed $260, amalgam allowed $140, 80/20 → write-off $40,
  insurance $112, patient $148 ($28 coinsurance + $120 gap). Needs per-carrier downgrade
  maps; deferred to its own slice.
- **Secondary-insurance COB** — v1 flags a secondary plan (`has_secondary_insurance`) with
  a "submit manually after primary EOB" note; it does not coordinate benefits.
