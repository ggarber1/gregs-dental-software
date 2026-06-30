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


def generate_pcn(claim_id: str, attempt: int = 1) -> str:
    if attempt < 1:
        raise ValueError(f"attempt must be >= 1, got {attempt}")
    """Patient Control Number (CLM01).

    Deterministic from the claim UUID + attempt number; <= 17 chars and X12-safe.
    attempt=1 preserves the original derivation (UUID hex prefix) so existing
    claims are unaffected. attempt>1 appends a version suffix so each resubmission
    gets a distinct PCN that the new ERA can match back to.
    """
    base = claim_id.replace("-", "")
    if attempt == 1:
        return base[:17].upper()
    suffix = f"V{attempt}"
    return (base[: 17 - len(suffix)] + suffix).upper()
