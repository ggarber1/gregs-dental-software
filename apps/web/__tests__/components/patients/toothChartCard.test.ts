import { describe, it, expect } from "vitest";

import {
  shouldShowHoverCard,
  formatHoverConditionLine,
} from "@/components/patients/ToothChartCard";
import type { ToothCondition } from "@/lib/api/tooth-chart";

const mkCondition = (overrides: Partial<ToothCondition> = {}): ToothCondition => ({
  id: "c-1",
  practiceId: "p-1",
  patientId: "pt-1",
  toothNumber: "14",
  notationSystem: "universal",
  conditionType: "decay",
  surface: null,
  material: null,
  notes: null,
  status: "existing",
  recordedAt: "2026-01-01T00:00:00Z",
  recordedBy: "u-1",
  appointmentId: null,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  ...overrides,
});

describe("shouldShowHoverCard", () => {
  // Happy path: a tooth is hovered and nothing is selected → show its card.
  it("shows the card when the tooth is hovered and no tooth is selected", () => {
    expect(shouldShowHoverCard("14", null, "14")).toBe(true);
  });

  it("shows the card when the tooth is hovered and a different tooth is selected", () => {
    expect(shouldShowHoverCard("14", "3", "14")).toBe(true);
  });

  // Failure case: no hover.
  it("hides the card when no tooth is hovered", () => {
    expect(shouldShowHoverCard(null, null, "14")).toBe(false);
  });

  it("hides the card on teeth other than the hovered one", () => {
    expect(shouldShowHoverCard("14", null, "3")).toBe(false);
  });

  // Suppression: hovered tooth is also the selected tooth → detail panel takes over.
  it("suppresses the card when the hovered tooth is also the selected tooth", () => {
    expect(shouldShowHoverCard("14", "14", "14")).toBe(false);
  });
});

describe("formatHoverConditionLine", () => {
  // Happy path: condition with a surface.
  it("renders the condition label with the surface in parentheses", () => {
    const line = formatHoverConditionLine(
      mkCondition({ conditionType: "decay", surface: "MO" }),
    );
    expect(line).toBe("Decay (MO)");
  });

  it("uses the human-readable label for snake_case condition types", () => {
    const line = formatHoverConditionLine(
      mkCondition({ conditionType: "existing_restoration", surface: "B" }),
    );
    expect(line).toBe("Restoration (B)");
  });

  // Failure / edge case: condition with no surface recorded.
  it("omits the surface segment when surface is null", () => {
    const line = formatHoverConditionLine(
      mkCondition({ conditionType: "crown", surface: null }),
    );
    expect(line).toBe("Crown");
  });

  it("omits the surface segment when surface is an empty string", () => {
    const line = formatHoverConditionLine(
      mkCondition({ conditionType: "crown", surface: "" }),
    );
    expect(line).toBe("Crown");
  });
});
