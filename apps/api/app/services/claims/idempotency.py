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

    Deterministic from the claim's own UUID; <= 17 chars and X12-safe. Stedi warns
    that some payers truncate the PCN beyond 17 chars in 835 ERAs / 277CAs, which
    breaks match-back; keeping it <= 17 makes Module 7b's ERA matching reliable.
    """
    return claim_id.replace("-", "")[:17].upper()
