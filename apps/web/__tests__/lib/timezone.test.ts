import { describe, it, expect } from "vitest";

import {
  formatTimeInTz,
  formatDateHeaderInTz,
  isoToTimeInTz,
  isoToDateInTz,
  localInputToUTC,
  todayInTz,
  dayBoundsInTz,
  toDateStringInTz,
  dateToTimeInTz,
  addMonthsLocal,
} from "@/lib/timezone";

// ── formatTimeInTz ───────────────────────────────────────────────────────────

describe("formatTimeInTz", () => {
  it("formats a UTC ISO string in America/New_York", () => {
    // 13:00 UTC = 9:00 AM EDT
    const result = formatTimeInTz("2026-04-16T13:00:00Z", "America/New_York");
    expect(result).toBe("9:00 AM");
  });

  it("formats the same instant differently in America/Los_Angeles", () => {
    // 13:00 UTC = 6:00 AM PDT
    const result = formatTimeInTz("2026-04-16T13:00:00Z", "America/Los_Angeles");
    expect(result).toBe("6:00 AM");
  });

  it("formats afternoon time correctly", () => {
    // 20:30 UTC = 4:30 PM EDT
    const result = formatTimeInTz("2026-04-16T20:30:00Z", "America/New_York");
    expect(result).toBe("4:30 PM");
  });
});

// ── formatDateHeaderInTz ─────────────────────────────────────────────────────

describe("formatDateHeaderInTz", () => {
  it("formats a date in the practice timezone", () => {
    // 2026-04-16 is a Thursday
    const d = new Date("2026-04-16T12:00:00Z");
    const result = formatDateHeaderInTz(d, "America/New_York");
    expect(result).toContain("Thursday");
    expect(result).toContain("April");
    expect(result).toContain("16");
    expect(result).toContain("2026");
  });

  it("handles date rollover at UTC midnight", () => {
    // 2026-04-17 00:00 UTC = Apr 16 8:00 PM EDT — still the 16th in NY
    const d = new Date("2026-04-17T00:00:00Z");
    const result = formatDateHeaderInTz(d, "America/New_York");
    expect(result).toContain("16");
  });
});

// ── isoToTimeInTz ────────────────────────────────────────────────────────────

describe("isoToTimeInTz", () => {
  it("extracts HH:mm in practice timezone", () => {
    // 14:30 UTC = 10:30 EDT
    const result = isoToTimeInTz("2026-04-16T14:30:00Z", "America/New_York");
    expect(result).toBe("10:30");
  });

  it("extracts HH:mm in a different timezone", () => {
    // 14:30 UTC = 07:30 PDT
    const result = isoToTimeInTz("2026-04-16T14:30:00Z", "America/Los_Angeles");
    expect(result).toBe("07:30");
  });

  it("handles midnight correctly", () => {
    // 04:00 UTC = 00:00 EDT (midnight)
    const result = isoToTimeInTz("2026-04-16T04:00:00Z", "America/New_York");
    expect(result).toBe("00:00");
  });
});

// ── isoToDateInTz ────────────────────────────────────────────────────────────

describe("isoToDateInTz", () => {
  it("extracts YYYY-MM-DD in practice timezone", () => {
    const result = isoToDateInTz("2026-04-16T14:00:00Z", "America/New_York");
    expect(result).toBe("2026-04-16");
  });

  it("handles UTC midnight date rollover correctly", () => {
    // 2026-01-02 03:00 UTC = 2026-01-01 22:00 EST — still Jan 1 in NY
    const result = isoToDateInTz("2026-01-02T03:00:00Z", "America/New_York");
    expect(result).toBe("2026-01-01");
  });

  it("handles year boundary", () => {
    // 2026-01-01 02:00 UTC = 2025-12-31 21:00 EST
    const result = isoToDateInTz("2026-01-01T02:00:00Z", "America/New_York");
    expect(result).toBe("2025-12-31");
  });
});

// ── localInputToUTC ──────────────────────────────────────────────────────────

describe("localInputToUTC", () => {
  it("converts practice-local time to UTC during EDT", () => {
    // 9:00 AM EDT = 13:00 UTC (EDT = UTC-4)
    const result = localInputToUTC("2026-04-16", "09:00", "America/New_York");
    const d = new Date(result);
    expect(d.getUTCHours()).toBe(13);
    expect(d.getUTCMinutes()).toBe(0);
    expect(d.getUTCFullYear()).toBe(2026);
    expect(d.getUTCMonth()).toBe(3); // April (0-indexed)
    expect(d.getUTCDate()).toBe(16);
  });

  it("converts practice-local time to UTC during EST", () => {
    // 9:00 AM EST = 14:00 UTC (EST = UTC-5)
    const result = localInputToUTC("2026-01-15", "09:00", "America/New_York");
    const d = new Date(result);
    expect(d.getUTCHours()).toBe(14);
    expect(d.getUTCMinutes()).toBe(0);
  });

  it("converts Pacific time correctly", () => {
    // 9:00 AM PDT = 16:00 UTC (PDT = UTC-7)
    const result = localInputToUTC("2026-04-16", "09:00", "America/Los_Angeles");
    const d = new Date(result);
    expect(d.getUTCHours()).toBe(16);
    expect(d.getUTCMinutes()).toBe(0);
  });

  it("handles times with minutes", () => {
    // 14:45 EDT = 18:45 UTC
    const result = localInputToUTC("2026-04-16", "14:45", "America/New_York");
    const d = new Date(result);
    expect(d.getUTCHours()).toBe(18);
    expect(d.getUTCMinutes()).toBe(45);
  });

  it("returns a valid ISO string", () => {
    const result = localInputToUTC("2026-04-16", "09:00", "America/New_York");
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d{3}Z$/);
  });
});

// ── todayInTz ────────────────────────────────────────────────────────────────

describe("todayInTz", () => {
  it("returns a YYYY-MM-DD string", () => {
    const result = todayInTz("America/New_York");
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

// ── dayBoundsInTz ────────────────────────────────────────────────────────────

describe("dayBoundsInTz", () => {
  it("returns UTC bounds for a day in EDT", () => {
    const date = new Date("2026-04-16T12:00:00Z");
    const { start, end } = dayBoundsInTz(date, "America/New_York");

    // Apr 16 midnight EDT = 04:00 UTC
    expect(start.getUTCHours()).toBe(4);
    expect(start.getUTCDate()).toBe(16);
    expect(start.getUTCMonth()).toBe(3);

    // Apr 17 midnight EDT = 04:00 UTC next day
    expect(end.getUTCHours()).toBe(4);
    expect(end.getUTCDate()).toBe(17);
  });

  it("returns UTC bounds for a day in EST", () => {
    const date = new Date("2026-01-15T12:00:00Z");
    const { start, end } = dayBoundsInTz(date, "America/New_York");

    // Jan 15 midnight EST = 05:00 UTC
    expect(start.getUTCHours()).toBe(5);
    expect(start.getUTCDate()).toBe(15);

    // Jan 16 midnight EST = 05:00 UTC
    expect(end.getUTCHours()).toBe(5);
    expect(end.getUTCDate()).toBe(16);
  });

  it("end is exactly 24 hours after start for a non-DST-transition day", () => {
    const date = new Date("2026-04-16T12:00:00Z");
    const { start, end } = dayBoundsInTz(date, "America/New_York");
    const diffMs = end.getTime() - start.getTime();
    expect(diffMs).toBe(24 * 60 * 60 * 1000);
  });
});

// ── toDateStringInTz ─────────────────────────────────────────────────────────

describe("toDateStringInTz", () => {
  it("returns YYYY-MM-DD in practice timezone", () => {
    const d = new Date("2026-04-16T12:00:00Z");
    expect(toDateStringInTz(d, "America/New_York")).toBe("2026-04-16");
  });
});

// ── dateToTimeInTz ───────────────────────────────────────────────────────────

describe("dateToTimeInTz", () => {
  it("extracts HH:mm from a Date in practice timezone", () => {
    const d = new Date("2026-04-16T13:30:00Z"); // 9:30 AM EDT
    expect(dateToTimeInTz(d, "America/New_York")).toBe("09:30");
  });
});

// ── addMonthsLocal ───────────────────────────────────────────────────────────

describe("addMonthsLocal", () => {
  it("advances by 3 months mid-month", () => {
    expect(addMonthsLocal("2026-03-15", 3)).toBe("2026-06-15");
  });

  it("advances by 6 months across a year boundary", () => {
    expect(addMonthsLocal("2026-10-20", 6)).toBe("2027-04-20");
  });

  it("subtracts 3 months across a year boundary", () => {
    expect(addMonthsLocal("2026-02-10", -3)).toBe("2025-11-10");
  });

  it("clamps Jan 31 + 1mo to Feb 28 in a non-leap year", () => {
    expect(addMonthsLocal("2026-01-31", 1)).toBe("2026-02-28");
  });

  it("clamps Jan 31 + 1mo to Feb 29 in a leap year", () => {
    expect(addMonthsLocal("2028-01-31", 1)).toBe("2028-02-29");
  });

  it("clamps Mar 31 - 1mo to Feb 28 (non-leap)", () => {
    expect(addMonthsLocal("2026-03-31", -1)).toBe("2026-02-28");
  });

  it("clamps May 31 + 1mo to Jun 30", () => {
    expect(addMonthsLocal("2026-05-31", 1)).toBe("2026-06-30");
  });

  it("returns the same date for 0 months", () => {
    expect(addMonthsLocal("2026-04-20", 0)).toBe("2026-04-20");
  });

  it("does not mutate the input string", () => {
    const input = "2026-04-20";
    addMonthsLocal(input, 3);
    expect(input).toBe("2026-04-20");
  });

  it("handles large positive offsets (24 months)", () => {
    expect(addMonthsLocal("2026-04-20", 24)).toBe("2028-04-20");
  });

  it("throws on malformed date string", () => {
    expect(() => addMonthsLocal("2026/04/20", 1)).toThrow();
    expect(() => addMonthsLocal("not-a-date", 1)).toThrow();
    expect(() => addMonthsLocal("", 1)).toThrow();
  });

  it("throws on non-integer month offset", () => {
    expect(() => addMonthsLocal("2026-04-20", 1.5)).toThrow();
  });
});
