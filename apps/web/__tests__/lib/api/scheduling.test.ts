import { describe, it, expect } from "vitest";
import { confirmationGlyph, shouldShowNotes } from "@/lib/api/scheduling";
import { reminderStatusText } from "@/components/scheduling/DaySheet";
import type { Appointment } from "@/lib/api/scheduling";

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

  it("returns 🚫 when patient is opted out and appointment is unconfirmed", () => {
    expect(
      confirmationGlyph("scheduled", { smsStatus: null, emailStatus: null, patientSmsOptedOut: true }),
    ).toBe("🚫");
  });

  it("returns ✅ even when opted out if appointment is confirmed", () => {
    expect(
      confirmationGlyph("confirmed", { smsStatus: null, emailStatus: null, patientSmsOptedOut: true }),
    ).toBe("✅");
  });

  it("returns ⚪ when reminderSummary is null", () => {
    expect(confirmationGlyph("scheduled", null)).toBe("⚪");
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

// ── reminderStatusText ────────────────────────────────────────────────────────

function makeAppt(overrides: Partial<Appointment["reminderSummary"]> = {}): Appointment {
  return {
    id: "1",
    practiceId: "p1",
    patientId: null,
    providerId: null,
    operatoryId: null,
    appointmentTypeId: null,
    startTime: "2026-06-15T09:00:00Z",
    endTime: "2026-06-15T09:30:00Z",
    status: "scheduled",
    notes: null,
    cancellationReason: null,
    patientName: null,
    providerName: null,
    operatoryName: null,
    appointmentTypeName: null,
    appointmentTypeColor: null,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    reminderSummary: {
      smsStatus: null,
      emailStatus: null,
      patientSmsOptedOut: false,
      ...overrides,
    },
  };
}

describe("reminderStatusText", () => {
  it("returns null when reminderSummary is null", () => {
    const appt = { ...makeAppt(), reminderSummary: null };
    expect(reminderStatusText(appt)).toBeNull();
  });

  it("returns null when all statuses are pending (nothing has fired yet)", () => {
    expect(reminderStatusText(makeAppt({ smsStatus: "pending", emailStatus: "pending" }))).toBeNull();
  });

  it("returns null when all statuses are cancelled", () => {
    expect(
      reminderStatusText(makeAppt({ smsStatus: "cancelled", emailStatus: "cancelled" })),
    ).toBeNull();
  });

  it("returns SMS ✓ when sms is sent and email is pending", () => {
    const text = reminderStatusText(makeAppt({ smsStatus: "sent", emailStatus: "pending" }));
    expect(text).toBe("SMS ✓");
  });

  it("returns both channels when both are sent", () => {
    const text = reminderStatusText(makeAppt({ smsStatus: "sent", emailStatus: "sent" }));
    expect(text).toBe("SMS ✓ · Email ✓");
  });

  it("returns SMS ✗ when sms failed", () => {
    const text = reminderStatusText(makeAppt({ smsStatus: "failed", emailStatus: null }));
    expect(text).toBe("SMS ✗");
  });

  it("returns Email ✓ when only email was sent", () => {
    const text = reminderStatusText(makeAppt({ smsStatus: null, emailStatus: "sent" }));
    expect(text).toBe("Email ✓");
  });
});
