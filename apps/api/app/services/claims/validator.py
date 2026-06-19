from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.claims.base import DentalClaimInput

_VALID_CDT = re.compile(r"^D\d{4}$")
_VALID_NPI = re.compile(r"^\d{10}$")
_VALID_TAX_ID = re.compile(r"^\d{9}$")
_TOOTH_REQUIRED_PREFIXES = ("D2", "D3", "D4")  # restorative / endo / perio
_HIGH_FEE_CENTS = 500000  # $5,000


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_claim(claim: DentalClaimInput) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not _VALID_NPI.match(claim.billing_npi or ""):
        errors.append(f"Billing NPI invalid: {claim.billing_npi!r}")
    if not _VALID_NPI.match(claim.rendering_npi or ""):
        errors.append(f"Rendering NPI invalid: {claim.rendering_npi!r}")
    if not _VALID_TAX_ID.match(re.sub(r"-", "", claim.billing_tax_id or "")):
        errors.append("Billing tax ID (EIN) must be 9 digits")
    if not claim.billing_taxonomy_code:
        errors.append("Billing taxonomy code is required")
    if not claim.submitter_id:
        errors.append("Clearinghouse submitter ID is required")

    if not claim.lines:
        errors.append("Claim has no procedures")
    for i, line in enumerate(claim.lines, 1):
        if not _VALID_CDT.match(line.cdt_code or ""):
            errors.append(f"Line {i}: CDT code {line.cdt_code!r} must be D + 4 digits")
        if line.fee_cents <= 0:
            errors.append(f"Line {i}: fee must be greater than 0")
        if line.fee_cents > _HIGH_FEE_CENTS:
            warnings.append(f"Line {i}: fee ${line.fee_cents / 100:.2f} is unusually high — verify")
        if (
            any(line.cdt_code.startswith(p) for p in _TOOTH_REQUIRED_PREFIXES)
            and not line.tooth_number
        ):
            warnings.append(f"Line {i}: {line.cdt_code} typically requires a tooth number")

    if len(claim.patient_control_number) > 20:
        errors.append("Patient control number must be 20 characters or fewer")

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
