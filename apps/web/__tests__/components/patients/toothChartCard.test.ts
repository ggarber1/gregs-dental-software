import { describe, it, expect } from "vitest";

import { hasTreatmentPlannedItem } from "@/components/patients/toothChartHelpers";
import type { TreatmentPlanItem } from "@/lib/api/treatment-plans";

function makeItem(toothNumber: string): TreatmentPlanItem {
  return {
    id: `item-${toothNumber}`,
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
