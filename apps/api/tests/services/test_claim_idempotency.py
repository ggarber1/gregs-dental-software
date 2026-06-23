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
