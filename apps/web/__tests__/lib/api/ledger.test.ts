import { describe, it, expect } from "vitest";

import { centsToUsd, dollarsToCents, ledgerKeys } from "@/lib/api/ledger";

describe("centsToUsd", () => {
  it("formats cents as a two-decimal dollar string", () => {
    expect(centsToUsd(4500)).toBe("$45.00");
    expect(centsToUsd(0)).toBe("$0.00");
    expect(centsToUsd(2399)).toBe("$23.99");
    expect(centsToUsd(1)).toBe("$0.01");
  });
});

describe("dollarsToCents", () => {
  it("converts a positive dollar string to integer cents", () => {
    expect(dollarsToCents("45", false)).toBe(4500);
    expect(dollarsToCents("45.50", false)).toBe(4550);
    expect(dollarsToCents(" 12.34 ", false)).toBe(1234);
    // 80.10 * 100 = 8009.9999… in float; Math.round must recover 8010.
    expect(dollarsToCents("80.10", false)).toBe(8010);
  });

  it("rejects blank, non-numeric, and zero input", () => {
    expect(dollarsToCents("", false)).toBeNull();
    expect(dollarsToCents("   ", false)).toBeNull();
    expect(dollarsToCents("abc", false)).toBeNull();
    expect(dollarsToCents("0", false)).toBeNull();
  });

  it("rejects negatives when allowNegative is false (payments)", () => {
    expect(dollarsToCents("-5", false)).toBeNull();
  });

  it("keeps negatives when allowNegative is true (credit adjustments)", () => {
    expect(dollarsToCents("-25", true)).toBe(-2500);
    expect(dollarsToCents("25", true)).toBe(2500);
  });
});

describe("ledgerKeys", () => {
  it("namespaces the patient ledger query key", () => {
    expect(ledgerKeys.patient("p1")).toEqual(["ledger", "p1"]);
  });
});
