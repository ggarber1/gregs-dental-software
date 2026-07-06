// apps/web/lib/carc-codes.ts

interface CarcEntry {
  description: string;
  hint: string;
}

const CARC_CODES: Record<string, CarcEntry> = {
  "1":   { description: "Deductible amount", hint: "Patient deductible applies — verify deductible balance." },
  "2":   { description: "Coinsurance amount", hint: "Patient coinsurance applies — verify plan coinsurance rate." },
  "3":   { description: "Co-payment amount", hint: "Patient copay applies — collect from patient." },
  "4":   { description: "Service requires prior authorization", hint: "Obtain prior authorization from carrier, then resubmit." },
  "16":  { description: "Claim missing required information", hint: "Check submission errors for the specific missing field." },
  "18":  { description: "Duplicate claim", hint: "This claim was already submitted. Check for duplicate." },
  "22":  { description: "Payment adjusted — coordination of benefits", hint: "COB adjustment from secondary insurance." },
  "26":  { description: "Expenses incurred prior to coverage", hint: "Service date is before patient's coverage effective date." },
  "27":  { description: "Expenses incurred after coverage terminated", hint: "Verify patient's coverage end date." },
  "45":  { description: "Charge exceeds contracted fee schedule", hint: "Contractual adjustment — verify fee schedule with this carrier." },
  "49":  { description: "Claim not covered by this payer — send to correct payer", hint: "Verify payer ID and resubmit to the correct carrier." },
  "50":  { description: "Non-covered service", hint: "Verify that this CDT code is covered under this patient's plan." },
  "55":  { description: "Procedure incompatible with procedure already adjudicated", hint: "Check for bundling rules — may need to remove a procedure." },
  "57":  { description: "Payment denied — plan does not cover this service", hint: "This service is not covered. Consider writing off or billing patient." },
  "96":  { description: "Non-covered charge", hint: "Verify this CDT code is covered under this patient's plan before resubmitting." },
  "97":  { description: "Included in payment for another procedure", hint: "Check for bundling — carrier may have paid this under a different code." },
  "119": { description: "Benefit maximum for this time period has been reached", hint: "Patient's annual maximum is exhausted. Patient is responsible." },
  "125": { description: "Submission/billing error", hint: "Check the specific error code from the carrier for details." },
  "167": { description: "Patient not eligible on date of service", hint: "Verify patient eligibility for the date of service — coverage may have lapsed." },
  "170": { description: "Payment denied — not covered by this payer", hint: "Verify correct insurance plan and payer ID." },
  "197": { description: "Precertification/authorization absent", hint: "Obtain prior authorization from carrier, then resubmit." },
  "204": { description: "Service not covered by this plan", hint: "This service is excluded from this plan. Bill patient or write off." },
  "253": { description: "Sequencing of therapy requires prior adjudication", hint: "A prerequisite claim must be adjudicated first." },
};

export function getCarcDescription(code: string): CarcEntry {
  return (
    CARC_CODES[code] ?? {
      description: `Adjustment code ${code}`,
      hint: "See explanation from carrier for details.",
    }
  );
}

export function formatDenialReason(
  denialCodes: string[],
  carrierName: string,
  cdtCodes: string[],
): string {
  if (denialCodes.length === 0) return "Denied by carrier.";
  const primary = denialCodes[0]!;
  const { description, hint } = getCarcDescription(primary);
  const cdt = cdtCodes.length > 0 ? ` for ${cdtCodes.join(", ")}` : "";
  return `${carrierName} denied${cdt}: ${description} (CARC ${primary}). ${hint}`;
}
