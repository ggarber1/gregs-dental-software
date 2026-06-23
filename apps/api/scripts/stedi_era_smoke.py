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
