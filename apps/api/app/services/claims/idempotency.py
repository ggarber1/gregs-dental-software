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
