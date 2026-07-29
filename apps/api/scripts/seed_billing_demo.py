"""Seed billing demo data for Module 8b manual testing.

Creates patients, appointments, claims, copay calculations, and ledger entries
that exercise every scenario in the claims hub and billing dashboard:

  All tab          — 8 claims in various statuses
  Awaiting tab     — 2 claims submitted, no ERA yet
  Underpaid tab    — 2 claims where insurance paid < 95% of estimate
  Problem tab      — 2 claims (denied + clearinghouse_rejected)
  Appealing tab    — 1 claim flagged for appeal
  Reconciled tab   — 3 ERA-settled claims:
                       overpaid (insurance paid more than estimate)
                       within_tolerance (paid 97% of estimate)
                       no_estimate (ERA posted, no copay calc)

Run from apps/api:
    uv run python scripts/seed_billing_demo.py
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_engine

PRACTICE_ID = uuid.UUID("d6c98183-fd13-4dd3-addd-33f0fd9a3a41")
PROVIDER_ID = uuid.UUID("ca99bde0-77eb-4e8f-938f-09e6d4d3b823")
DEMO_INSURANCE_ID = uuid.uuid4()  # no FK constraint, just needs to be non-null
NOW = datetime.now(UTC)


def _days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


def _pid() -> str:
    return str(uuid.uuid4())


PATIENTS = [
    {"id": _pid(), "first_name": "Sarah",  "last_name": "Demo-Mitchell"},
    {"id": _pid(), "first_name": "James",  "last_name": "Demo-Okafor"},
    {"id": _pid(), "first_name": "Linda",  "last_name": "Demo-Huang"},
    {"id": _pid(), "first_name": "Robert", "last_name": "Demo-Torres"},
    {"id": _pid(), "first_name": "Amy",    "last_name": "Demo-Nakamura"},
    {"id": _pid(), "first_name": "David",  "last_name": "Demo-Patel"},
    {"id": _pid(), "first_name": "Carol",  "last_name": "Demo-Freeman"},
    {"id": _pid(), "first_name": "Kevin",  "last_name": "Demo-Walsh"},
]

PAYERS = [
    ("DELTA-DEMO", "Delta Dental"),
    ("CIGNA-DEMO", "Cigna Dental"),
    ("AETNA-DEMO", "Aetna"),
    ("UNITED-DEMO", "United Healthcare"),
]

# Each scenario:
# (patient_idx, payer_idx, status, billed, estimate, paid, paid_days_ago, sub_days_ago, notes)
SCENARIOS = [
    # --- Awaiting (submitted, no ERA) ---
    (0, 0, "submitted",  35000, 28000, None,  None, 14, "routine cleaning + exam"),
    (1, 1, "submitted",  85000, 68000, None,  None, 21, "crown prep"),

    # --- Underpaid (paid < 95% of estimate) ---
    (2, 2, "paid",       45000, 36000, 27000, 10, 40, "filling — paid $270, est $360"),
    (3, 3, "paid",      120000, 96000, 70000,  7, 35, "root canal — paid $700, est $960"),

    # --- Problem: denied ---
    (4, 0, "denied",     55000, 44000, None,  None, 60, "missing tooth exclusion"),
    # --- Problem: clearinghouse_rejected ---
    (5, 1, "clearinghouse_rejected", 32000, 25600, None, None, 5, "invalid subscriber ID"),

    # --- Appealing ---
    (6, 2, "appealing",  78000, 62400, None,  None, 30, "flagged by staff — prior auth dispute"),

    # --- Reconciled: overpaid ---
    (7, 3, "paid",       40000, 32000, 35000,  3, 50, "overpaid by $30"),
    # --- Reconciled: within_tolerance (paid 97% of estimate) ---
    (0, 0, "paid",       60000, 48000, 46560,  5, 45, "within tolerance — $14.40 short"),
    # --- Reconciled: no_estimate (ERA posted, no copay calc) ---
    (1, 1, "paid",       25000,  None, 20000,  8, 55, "no estimate on file"),
]


async def seed(session: AsyncSession) -> None:
    # ------------------------------------------------------------------
    # 0. Wipe any previous demo run (PCN prefix DEMO*)
    # ------------------------------------------------------------------
    demo_claim_ids = (
        await session.execute(
            text(
                "SELECT id FROM claims"
                " WHERE patient_control_number LIKE 'DEMO%'"
                " AND practice_id = :pr"
            ),
            {"pr": str(PRACTICE_ID)},
        )
    ).scalars().all()
    if demo_claim_ids:
        await session.execute(
            text("DELETE FROM ledger_entries WHERE claim_id = ANY(:ids)"),
            {"ids": list(demo_claim_ids)},
        )
        await session.execute(
            text(
                "DELETE FROM copay_calculations"
                " WHERE appointment_id IN"
                " (SELECT appointment_id FROM claims WHERE id = ANY(:ids))"
            ),
            {"ids": list(demo_claim_ids)},
        )
        await session.execute(
            text("DELETE FROM claims WHERE id = ANY(:ids)"),
            {"ids": list(demo_claim_ids)},
        )
    # Wipe demo patients (tagged by last_name prefix 'Demo-')
    await session.execute(
        text(
            "DELETE FROM appointments WHERE patient_id IN"
            " (SELECT id FROM patients WHERE last_name LIKE 'Demo-%' AND practice_id = :pr)"
        ),
        {"pr": str(PRACTICE_ID)},
    )
    await session.execute(
        text("DELETE FROM patients WHERE last_name LIKE 'Demo-%' AND practice_id = :pr"),
        {"pr": str(PRACTICE_ID)},
    )
    # Wipe demo insurance plans
    await session.execute(
        text("DELETE FROM insurance_plans WHERE payer_id LIKE '%-DEMO' AND practice_id = :pr"),
        {"pr": str(PRACTICE_ID)},
    )
    await session.commit()

    # ------------------------------------------------------------------
    # 1. Insert insurance plans so carrier names resolve
    # ------------------------------------------------------------------
    for payer_id, carrier_name in PAYERS:
        await session.execute(
            text("""
                INSERT INTO insurance_plans (id, practice_id, payer_id, carrier_name,
                    group_number, created_at, updated_at)
                VALUES (:id, :practice_id, :payer_id, :carrier_name,
                    'GRP-DEMO', now(), now())
            """),
            {
                "id": str(uuid.uuid4()),
                "practice_id": str(PRACTICE_ID),
                "payer_id": payer_id,
                "carrier_name": carrier_name,
            },
        )

    # ------------------------------------------------------------------
    # 2. Insert patients
    # ------------------------------------------------------------------
    for p in PATIENTS:
        await session.execute(
            text("""
                INSERT INTO patients (id, practice_id, first_name, last_name,
                    date_of_birth, created_at, updated_at)
                VALUES (:id, :practice_id, :first_name, :last_name,
                    '1980-01-01', now(), now())
                            """),
            {
                "id": p["id"],
                "practice_id": str(PRACTICE_ID),
                "first_name": p["first_name"],
                "last_name": p["last_name"],
            },
        )

    # ------------------------------------------------------------------
    # 3. Insert appointments, claims, copay calcs, ledger entries
    # ------------------------------------------------------------------
    for i, (pat_idx, payer_idx, status, billed, estimate, paid, paid_ago, sub_ago, _) in (
        enumerate(SCENARIOS)
    ):
        patient_id = PATIENTS[pat_idx]["id"]
        payer_id, _ = PAYERS[payer_idx]
        appt_id = str(uuid.uuid4())
        claim_id = str(uuid.uuid4())
        appt_time = _days_ago(sub_ago + 2)

        # Appointment
        await session.execute(
            text("""
                INSERT INTO appointments (id, practice_id, patient_id,
                    start_time, end_time, status, created_at, updated_at)
                VALUES (:id, :practice_id, :patient_id,
                    :start_time, :end_time, 'completed', now(), now())
                            """),
            {
                "id": appt_id,
                "practice_id": str(PRACTICE_ID),
                "patient_id": patient_id,
                "start_time": appt_time,
                "end_time": appt_time + timedelta(hours=1),
            },
        )

        # Claim
        submitted_at = _days_ago(sub_ago) if status != "draft" else None
        paid_at = _days_ago(paid_ago) if paid_ago is not None else None
        pcn = f"DEMO{i+1:04d}"

        await session.execute(
            text("""
                INSERT INTO claims (id, practice_id, appointment_id, patient_id,
                    insurance_id, provider_id, idempotency_key,
                    patient_control_number, payer_id, status,
                    total_charge_cents, insurance_paid_cents,
                    submitted_at, paid_at, created_at, updated_at)
                VALUES (:id, :practice_id, :appointment_id, :patient_id,
                    :insurance_id, :provider_id, :idem_key,
                    :pcn, :payer_id, :status,
                    :total_charge_cents, :insurance_paid_cents,
                    :submitted_at, :paid_at, now(), now())
                ON CONFLICT (patient_control_number, payer_id) DO NOTHING
            """),
            {
                "id": claim_id,
                "practice_id": str(PRACTICE_ID),
                "appointment_id": appt_id,
                "patient_id": patient_id,
                "insurance_id": str(DEMO_INSURANCE_ID),
                "provider_id": str(PROVIDER_ID),
                "idem_key": f"demo-claim-{i}",
                "pcn": pcn,
                "payer_id": payer_id,
                "status": status,
                "total_charge_cents": billed,
                "insurance_paid_cents": paid,
                "submitted_at": submitted_at,
                "paid_at": paid_at,
            },
        )

        # Copay calculation (skip for no_estimate scenario)
        if estimate is not None:
            patient_owes = billed - estimate
            await session.execute(
                text("""
                    INSERT INTO copay_calculations (
                        id, practice_id, patient_id, appointment_id,
                        calculated_at, plan_type,
                        total_provider_fee_cents, total_write_off_cents,
                        total_insurance_owes_cents, total_patient_owes_cents,
                        line_items, idempotency_key, created_at, updated_at)
                    VALUES (
                        :id, :practice_id, :patient_id, :appointment_id,
                        :calc_at, 'PPO',
                        :billed, 0,
                        :insurance_owes, :patient_owes,
                        '[]', :idem_key, now(), now())
                                    """),
                {
                    "id": str(uuid.uuid4()),
                    "practice_id": str(PRACTICE_ID),
                    "patient_id": patient_id,
                    "appointment_id": appt_id,
                    "calc_at": appt_time - timedelta(hours=1),
                    "billed": billed,
                    "insurance_owes": estimate,
                    "patient_owes": patient_owes,
                    "idem_key": f"demo-copay-{i}",
                },
            )

        # Ledger entries for paid claims
        if status == "paid" and paid is not None:
            # Charge entry
            await session.execute(
                text("""
                    INSERT INTO ledger_entries (id, practice_id, patient_id,
                        claim_id, entry_type, amount_cents,
                        posted_at, created_at, updated_at)
                    VALUES (:id, :practice_id, :patient_id,
                        :claim_id, 'charge', :amount,
                        :posted_at, now(), now())
                                    """),
                {
                    "id": str(uuid.uuid4()),
                    "practice_id": str(PRACTICE_ID),
                    "patient_id": patient_id,
                    "claim_id": claim_id,
                    "amount": billed,
                    "posted_at": appt_time,
                },
            )
            # Insurance payment entry (negative — reduces balance)
            await session.execute(
                text("""
                    INSERT INTO ledger_entries (id, practice_id, patient_id,
                        claim_id, entry_type, amount_cents,
                        posted_at, created_at, updated_at)
                    VALUES (:id, :practice_id, :patient_id,
                        :claim_id, 'insurance_payment', :amount,
                        :posted_at, now(), now())
                                    """),
                {
                    "id": str(uuid.uuid4()),
                    "practice_id": str(PRACTICE_ID),
                    "patient_id": patient_id,
                    "claim_id": claim_id,
                    "amount": -paid,
                    "posted_at": paid_at,
                },
            )

    await session.commit()
    print("✓ Demo data seeded successfully.")
    print()
    print("Scenarios created:")
    print("  Awaiting:          Sarah Mitchell (Delta), James Okafor (Cigna)")
    print("  Underpaid:         Linda Huang (Aetna), Robert Torres (United)")
    print("  Problem/denied:    Amy Nakamura (Delta)")
    print("  Problem/rejected:  David Patel (Cigna)")
    print("  Appealing:         Carol Freeman (Aetna)")
    print("  Reconciled/overpaid:    Kevin Walsh (United) — paid $350, est $320")
    print("  Reconciled/tolerance:   Sarah Mitchell (Delta) — paid $465.60, est $480")
    print("  Reconciled/no-estimate: James Okafor (Cigna) — paid $200, no estimate")


async def main() -> None:
    engine = get_engine()
    async with AsyncSession(engine) as session:
        await seed(session)


if __name__ == "__main__":
    asyncio.run(main())
