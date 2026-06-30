// apps/web/lib/submission-error-hints.ts

interface ErrorHint {
  plain: string;
  fixIn: string;
}

const ERROR_PATTERNS: Array<{ pattern: RegExp; hint: ErrorHint }> = [
  {
    pattern: /NPI|billing provider npi/i,
    hint: { plain: "Billing NPI not recognized by this payer.", fixIn: "Settings → Practice → Billing NPI" },
  },
  {
    pattern: /tax.?id|ein/i,
    hint: { plain: "Tax ID / EIN is invalid or missing.", fixIn: "Settings → Practice → Billing Tax ID" },
  },
  {
    pattern: /payer.?id|payer not found/i,
    hint: { plain: "Payer ID not recognized.", fixIn: "the patient's insurance plan → Payer ID" },
  },
  {
    pattern: /date.?of.?birth|dob/i,
    hint: { plain: "Patient date of birth mismatch.", fixIn: "the patient's demographics → Date of Birth" },
  },
  {
    pattern: /member.?id|subscriber.?id/i,
    hint: { plain: "Member / subscriber ID is invalid.", fixIn: "the patient's insurance → Member ID" },
  },
  {
    pattern: /submitter/i,
    hint: { plain: "Clearinghouse submitter ID is invalid.", fixIn: "Settings → Practice → Clearinghouse Submitter ID" },
  },
];

export function getSubmissionErrorHint(error: string): ErrorHint | null {
  for (const { pattern, hint } of ERROR_PATTERNS) {
    if (pattern.test(error)) return hint;
  }
  return null;
}

export function formatSubmissionError(error: string): { plain: string; fixIn: string | null } {
  const hint = getSubmissionErrorHint(error);
  if (hint) return { plain: hint.plain, fixIn: hint.fixIn };
  return { plain: error, fixIn: null };
}
