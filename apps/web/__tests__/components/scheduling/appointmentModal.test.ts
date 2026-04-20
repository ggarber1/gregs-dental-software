import { describe, it, expect } from "vitest";

import {
  addMinutesToTime,
  resolveDefaultEndTime,
} from "@/components/scheduling/AppointmentModal";

describe("resolveDefaultEndTime", () => {
  it("uses explicit defaultEndTime when provided (drag-to-range case)", () => {
    expect(resolveDefaultEndTime("10:30", "09:00")).toBe("10:30");
  });

  it("prefers defaultEndTime even over a conflicting startTime default", () => {
    expect(resolveDefaultEndTime("10:00", "14:00")).toBe("10:00");
  });

  it("falls back to start + 30min when defaultEndTime is undefined (single-click case)", () => {
    expect(resolveDefaultEndTime(undefined, "09:00")).toBe("09:30");
    expect(resolveDefaultEndTime(undefined, "14:15")).toBe("14:45");
  });

  it("falls back to 09:30 when neither default is provided (toolbar New Appointment)", () => {
    expect(resolveDefaultEndTime(undefined, undefined)).toBe("09:30");
  });

  it("handles hour rollover in the start+30 fallback", () => {
    expect(resolveDefaultEndTime(undefined, "09:45")).toBe("10:15");
  });
});

describe("addMinutesToTime", () => {
  it("adds minutes without rollover", () => {
    expect(addMinutesToTime("09:00", 30)).toBe("09:30");
    expect(addMinutesToTime("14:15", 45)).toBe("15:00");
  });

  it("wraps past midnight", () => {
    expect(addMinutesToTime("23:45", 30)).toBe("00:15");
  });

  it("zero-pads single-digit hours and minutes", () => {
    expect(addMinutesToTime("08:05", 0)).toBe("08:05");
  });
});
