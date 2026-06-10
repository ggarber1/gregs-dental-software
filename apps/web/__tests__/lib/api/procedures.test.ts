import { describe, it, expect } from "vitest";

import { formatCents, prefillFeeDollars } from "@/lib/api/procedures";

describe("formatCents", () => {
  it("formats whole dollars", () => {
    expect(formatCents(12000)).toBe("$120.00");
  });

  it("formats zero", () => {
    expect(formatCents(0)).toBe("$0.00");
  });

  it("formats sub-dollar cents", () => {
    expect(formatCents(2399)).toBe("$23.99");
  });

  it("formats a single cent", () => {
    expect(formatCents(1)).toBe("$0.01");
  });
});

describe("prefillFeeDollars", () => {
  it("fills the resolved practice fee when the field is empty", () => {
    expect(prefillFeeDollars("", 4500)).toBe("45");
  });

  it("does not clobber a value the user already typed", () => {
    expect(prefillFeeDollars("99.99", 4500)).toBe("99.99");
  });

  it("leaves the field blank when no fee resolves", () => {
    expect(prefillFeeDollars("", null)).toBe("");
  });
});
