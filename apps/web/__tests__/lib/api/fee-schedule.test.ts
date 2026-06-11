import { describe, it, expect } from "vitest";

import { dollarsToCents, centsToDollars } from "@/lib/api/fee-schedule";

describe("dollarsToCents", () => {
  it("converts a dollar string to integer cents", () => {
    expect(dollarsToCents("45")).toBe(4500);
    expect(dollarsToCents("45.50")).toBe(4550);
    expect(dollarsToCents(" 12.34 ")).toBe(1234);
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
  });

  it("returns an empty string for null", () => {
    expect(centsToDollars(null)).toBe("");
  });
});
