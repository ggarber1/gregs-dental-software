import { describe, it, expect } from "vitest";
import { confirmationGlyph } from "@/lib/api/scheduling";

describe("confirmationGlyph", () => {
  it("returns ⚪ for scheduled (patient not yet confirmed)", () => {
    expect(confirmationGlyph("scheduled")).toBe("⚪");
  });

  it("returns ✅ for confirmed", () => {
    expect(confirmationGlyph("confirmed")).toBe("✅");
  });

  it("returns ✅ for checked_in (patient is present — implicitly confirmed)", () => {
    expect(confirmationGlyph("checked_in")).toBe("✅");
  });

  it("returns ✅ for in_chair", () => {
    expect(confirmationGlyph("in_chair")).toBe("✅");
  });

  it("returns ✅ for completed", () => {
    expect(confirmationGlyph("completed")).toBe("✅");
  });

  it("returns ⚪ for no_show (never confirmed)", () => {
    expect(confirmationGlyph("no_show")).toBe("⚪");
  });

  it("returns ⚪ for cancelled", () => {
    expect(confirmationGlyph("cancelled")).toBe("⚪");
  });
});
