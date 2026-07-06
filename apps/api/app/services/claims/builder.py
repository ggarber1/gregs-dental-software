from __future__ import annotations

from datetime import date
from typing import Any

from app.services.claims.base import Address, ClaimLine, DentalClaimInput


def _gender(sex: str | None) -> str:
    return {"male": "M", "female": "F"}.get((sex or "").lower(), "U")


def _split_full_name(full_name: str) -> tuple[str, str]:
    """Split 'First Last' into (first, last).

    The real Provider model stores a single `full_name` column.  For 837D we
    need separate first/last on the NM1 segment.  We split on the first space;
    if there's no space the whole value becomes the last name and first is "".
    """
    parts = full_name.strip().split(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", parts[0]


def build_claim_input(
    *,
    appt: Any,
    procedures: list[Any],
    patient: Any,
    insurance: Any,
    payer_id: str,
    practice: Any,
    provider: Any,
    billing_tax_id: str,
    pcn: str,
    usage_indicator: str,
    claim_frequency_code: str = "1",
    original_claim_reference: str | None = None,
) -> DentalClaimInput:
    """Assemble a DentalClaimInput from already-fetched ORM rows (pure; no DB).

    Provider note: the Provider model stores a single `full_name` field.
    This function splits it on the first space to produce rendering_first_name
    and rendering_last_name for the 837D NM1 segment.
    """
    if insurance.relationship_to_insured == "self":
        sub_first = patient.first_name
        sub_last = patient.last_name
        sub_dob = patient.date_of_birth
    else:
        sub_first = insurance.insured_first_name or ""
        sub_last = insurance.insured_last_name or ""
        sub_dob = insurance.insured_date_of_birth or patient.date_of_birth

    rendering_first, rendering_last = _split_full_name(provider.full_name)

    lines = tuple(
        ClaimLine(
            procedure_id=str(p.id),
            cdt_code=p.procedure_code or "",
            fee_cents=p.fee_cents,
            tooth_number=p.tooth_number,
            surface=p.surface,
            procedure_name=p.procedure_name,
        )
        for p in procedures
    )

    service_date: date = appt.start_time.date() if appt.start_time else date.today()

    billing_address = Address(
        line1=practice.address_line1 or "",
        city=practice.city or "",
        state=practice.state or "",
        postal_code=(practice.zip or "").replace("-", ""),
    )
    # For a non-self subscriber we have no insured address/gender on file, so fall back
    # to the patient's address and an unknown gender (best-effort; most claims are self).
    subscriber_address = Address(
        line1=patient.address_line1 or "",
        city=patient.city or "",
        state=patient.state or "",
        postal_code=(patient.zip or "").replace("-", ""),
    )
    subscriber_gender = _gender(patient.sex) if insurance.relationship_to_insured == "self" else "U"

    return DentalClaimInput(
        patient_control_number=pcn,
        payer_id=payer_id,
        usage_indicator=usage_indicator,
        billing_npi=practice.billing_npi or "",
        billing_tax_id=billing_tax_id,
        billing_taxonomy_code=practice.billing_taxonomy_code or "",
        billing_org_name=practice.name,
        billing_address=billing_address,
        submitter_id=practice.clearinghouse_submitter_id or "",
        rendering_npi=provider.npi,
        rendering_first_name=rendering_first,
        rendering_last_name=rendering_last,
        subscriber_first_name=sub_first,
        subscriber_last_name=sub_last,
        subscriber_dob=sub_dob,
        subscriber_gender=subscriber_gender,
        subscriber_address=subscriber_address,
        member_id=insurance.member_id or "",
        group_number=insurance.group_number,
        relationship_to_insured=insurance.relationship_to_insured,
        patient_first_name=patient.first_name,
        patient_last_name=patient.last_name,
        patient_dob=patient.date_of_birth,
        patient_gender=_gender(patient.sex),
        date_of_service=service_date,
        lines=lines,
        claim_frequency_code=claim_frequency_code,
        original_claim_reference=original_claim_reference,
    )
