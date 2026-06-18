import { describe, it, expect } from "vitest";

import { dollarsToCents, centsToDollars, centsToUsd } from "@/lib/api/copay";

describe("dollarsToCents", () => {
  it("converts a dollar string to integer cents", () => {
    expect(dollarsToCents("45")).toBe(4500);
    expect(dollarsToCents("45.50")).toBe(4550);
    expect(dollarsToCents(" 12.34 ")).toBe(1234);
    // 80.10 * 100 = 8009.9999… in float; Math.round must recover 8010.
    expect(dollarsToCents("80.10")).toBe(8010);
  });

  it("returns null for blank or invalid input", () => {
    expect(dollarsToCents("")).toBeNull();
    expect(dollarsToCents("   ")).toBeNull();
    expect(dollarsToCents("abc")).toBeNull();
    expect(dollarsToCents("-5")).toBeNull();
  });
});

describe("centsToDollars", () => {
  it("formats integer cents as a two-decimal dollar string", () => {
    expect(centsToDollars(4500)).toBe("45.00");
    expect(centsToDollars(1234)).toBe("12.34");
    expect(centsToDollars(0)).toBe("0.00");
  });

  it("returns an empty string for null", () => {
    expect(centsToDollars(null)).toBe("");
  });
});

describe("centsToUsd", () => {
  it("formats cents as a dollar display string", () => {
    expect(centsToUsd(4500)).toBe("$45.00");
    expect(centsToUsd(0)).toBe("$0.00");
  });

  it("returns an em dash for null or undefined", () => {
    expect(centsToUsd(null)).toBe("—");
    expect(centsToUsd(undefined)).toBe("—");
  });
});
