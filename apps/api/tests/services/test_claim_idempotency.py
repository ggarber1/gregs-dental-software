from app.services.claims.idempotency import generate_claim_idempotency_key, generate_pcn


def test_idempotency_key_is_deterministic():
    a = generate_claim_idempotency_key("appt-1", "pat-1", "ins-1", 1)
    b = generate_claim_idempotency_key("appt-1", "pat-1", "ins-1", 1)
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_idempotency_key_changes_with_attempt():
    v1 = generate_claim_idempotency_key("appt-1", "pat-1", "ins-1", 1)
    v2 = generate_claim_idempotency_key("appt-1", "pat-1", "ins-1", 2)
    assert v1 != v2


def test_idempotency_key_changes_with_inputs():
    base = generate_claim_idempotency_key("appt-1", "pat-1", "ins-1", 1)
    assert generate_claim_idempotency_key("appt-2", "pat-1", "ins-1", 1) != base
    assert generate_claim_idempotency_key("appt-1", "pat-2", "ins-1", 1) != base


def test_pcn_is_deterministic_and_within_stedi_limit():
    cid = "0d2b9f3a-1c4e-4a8b-9f2a-123456789abc"
    pcn = generate_pcn(cid)
    assert pcn == generate_pcn(cid)
    assert 1 <= len(pcn) <= 17  # Stedi: payers may truncate beyond 17 chars
    # only X12-safe chars (no reserved delimiters ~ * : ^)
    assert all(c not in "~*:^" for c in pcn)


# --- attempt parameter tests ---

CLAIM_ID = "550e8400-e29b-41d4-a716-446655440000"


def test_generate_pcn_attempt_1_unchanged():
    # attempt=1 (default) must produce the same value as before
    pcn = generate_pcn(CLAIM_ID)
    assert pcn == generate_pcn(CLAIM_ID, attempt=1)
    assert len(pcn) <= 17
    assert pcn == pcn.upper()


def test_generate_pcn_attempt_2_different_from_1():
    assert generate_pcn(CLAIM_ID, attempt=2) != generate_pcn(CLAIM_ID, attempt=1)


def test_generate_pcn_attempt_2_max_17_chars():
    assert len(generate_pcn(CLAIM_ID, attempt=2)) <= 17


def test_generate_pcn_attempt_2_x12_safe():
    pcn = generate_pcn(CLAIM_ID, attempt=2)
    assert all(c not in "~*:^" for c in pcn)


def test_generate_pcn_invalid_attempt_raises():
    import pytest
    with pytest.raises(ValueError, match="attempt must be >= 1"):
        generate_pcn(CLAIM_ID, attempt=0)
