import { describe, it, expect } from "vitest";

import {
  hasTreatmentPlannedItem,
  highestUrgency,
  urgencyBadgeColor,
} from "@/components/patients/toothChartHelpers";
import type {
  TreatmentPlanItem,
  TreatmentPlanItemUrgency,
} from "@/lib/api/treatment-plans";

function makeItem(
  toothNumber: string,
  urgency: TreatmentPlanItemUrgency = "soon",
): TreatmentPlanItem {
  return {
    id: `item-${toothNumber}-${urgency}`,
    practiceId: "practice-1",
    treatmentPlanId: "plan-1",
    patientId: "patient-1",
    toothNumber,
    procedureCode: "D2750",
    procedureName: "Crown",
    surface: null,
    feeCents: 100000,
    insuranceEstCents: null,
    patientEstCents: null,
    status: "proposed",
    urgency,
    priority: 1,
    appointmentId: null,
    completedAppointmentId: null,
    notes: null,
    createdAt: "2026-05-04T12:00:00Z",
    updatedAt: "2026-05-04T12:00:00Z",
  };
}

describe("hasTreatmentPlannedItem", () => {
  it("returns true when the tooth has at least one item", () => {
    const map = new Map<string, TreatmentPlanItem[]>([["14", [makeItem("14")]]]);
    expect(hasTreatmentPlannedItem(map, "14")).toBe(true);
  });

  it("returns false for teeth not present in the map", () => {
    const map = new Map<string, TreatmentPlanItem[]>([["14", [makeItem("14")]]]);
    expect(hasTreatmentPlannedItem(map, "30")).toBe(false);
  });

  it("returns false when the map is undefined", () => {
    expect(hasTreatmentPlannedItem(undefined, "14")).toBe(false);
  });

  it("returns false when the tooth's entry is an empty array", () => {
    const map = new Map<string, TreatmentPlanItem[]>([["14", []]]);
    expect(hasTreatmentPlannedItem(map, "14")).toBe(false);
  });
});

describe("highestUrgency", () => {
  it("returns null for an empty list", () => {
    expect(highestUrgency([])).toBeNull();
  });

  it("returns 'urgent' when any item is urgent (worst-status wins)", () => {
    const items = [
      makeItem("14", "elective"),
      makeItem("14", "urgent"),
      makeItem("14", "soon"),
    ];
    expect(highestUrgency(items)).toBe("urgent");
  });

  it("returns 'soon' when no urgent but at least one soon", () => {
    expect(highestUrgency([makeItem("14", "elective"), makeItem("14", "soon")])).toBe("soon");
  });

  it("returns 'elective' when every item is elective", () => {
    expect(highestUrgency([makeItem("14", "elective"), makeItem("14", "elective")])).toBe(
      "elective",
    );
  });
});

describe("urgencyBadgeColor", () => {
  it("maps urgent to red", () => {
    expect(urgencyBadgeColor("urgent")).toBe("bg-red-600");
  });

  it("maps soon to orange (matches the original badge color)", () => {
    expect(urgencyBadgeColor("soon")).toBe("bg-orange-500");
  });

  it("maps elective to gray", () => {
    expect(urgencyBadgeColor("elective")).toBe("bg-gray-400");
  });
});
