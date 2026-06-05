import { describe, it, expect } from "vitest";

import { formatCents } from "@/lib/api/procedures";

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
