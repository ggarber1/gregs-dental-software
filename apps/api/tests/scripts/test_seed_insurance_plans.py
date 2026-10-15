"""Unit tests for the insurance-plan seed's id derivation."""

from __future__ import annotations

import uuid

from scripts.seed_insurance_plans import _CARRIERS, carrier_plan_uuid


def test_plan_ids_are_unique_per_carrier_and_never_the_practice_id() -> None:
    practice_id = uuid.uuid4()

    ids = {carrier_plan_uuid(practice_id, payer_id) for _, payer_id in _CARRIERS}

    assert len(ids) == len(_CARRIERS)
    assert practice_id not in ids


def test_plan_id_is_stable_for_a_practice_and_differs_across_practices() -> None:
    practice_a, practice_b = uuid.uuid4(), uuid.uuid4()

    assert carrier_plan_uuid(practice_a, "CKMA1") == carrier_plan_uuid(practice_a, "CKMA1")
    assert carrier_plan_uuid(practice_a, "CKMA1") != carrier_plan_uuid(practice_b, "CKMA1")
