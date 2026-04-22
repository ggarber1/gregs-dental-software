import { describe, it, expect } from "vitest";
import { confirmationGlyph, shouldShowNotes } from "@/lib/api/scheduling";

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

describe("shouldShowNotes", () => {
  it("returns true when notes present and duration >= 30 min", () => {
    expect(shouldShowNotes("Follow up on crown", 30)).toBe(true);
    expect(shouldShowNotes("Follow up on crown", 60)).toBe(true);
  });

  it("returns false when duration < 30 min even if notes are present", () => {
    expect(shouldShowNotes("Follow up on crown", 29)).toBe(false);
    expect(shouldShowNotes("Follow up on crown", 15)).toBe(false);
  });

  it("returns false when notes are null or empty regardless of duration", () => {
    expect(shouldShowNotes(null, 60)).toBe(false);
    expect(shouldShowNotes("", 60)).toBe(false);
    expect(shouldShowNotes(undefined, 60)).toBe(false);
  });
});
