import { describe, expect, it } from "vitest";

import {
  centsToUsd,
  pctToPatientShare,
} from "@/components/patients/EligibilityCard";

// ── centsToUsd ────────────────────────────────────────────────────────────────

describe("centsToUsd", () => {
  it("converts cents to a dollar string with two decimal places", () => {
    expect(centsToUsd(5000)).toBe("$50.00");
  });

  it("converts large values with thousands separator", () => {
    expect(centsToUsd(120000)).toBe("$1,200.00");
  });

  it("returns em-dash for null", () => {
    expect(centsToUsd(null)).toBe("—");
  });

  it("converts zero cents to $0.00 (not special-cased)", () => {
    expect(centsToUsd(0)).toBe("$0.00");
  });
});

// ── pctToPatientShare ─────────────────────────────────────────────────────────

describe("pctToPatientShare", () => {
  it("converts 0.2 fraction to '20%'", () => {
    expect(pctToPatientShare(0.2)).toBe("20%");
  });

  it("converts 0.5 fraction to '50%'", () => {
    expect(pctToPatientShare(0.5)).toBe("50%");
  });

  it("converts 0.0 fraction to '0%'", () => {
    expect(pctToPatientShare(0.0)).toBe("0%");
  });

  it("rounds fractional results", () => {
    expect(pctToPatientShare(0.333)).toBe("33%");
  });

  it("returns em-dash for null", () => {
    expect(pctToPatientShare(null)).toBe("—");
  });
});
