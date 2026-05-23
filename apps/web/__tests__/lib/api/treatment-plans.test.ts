import { describe, it, expect } from "vitest";

import {
  groupOpenItemsByTooth,
  type TreatmentPlanDetail,
  type TreatmentPlanItem,
} from "@/lib/api/treatment-plans";

const PRACTICE_ID = "practice-uuid-1";
const PATIENT_ID = "patient-uuid-1";

function makeItem(overrides: Partial<TreatmentPlanItem>): TreatmentPlanItem {
  return {
    id: "item-uuid",
    practiceId: PRACTICE_ID,
    treatmentPlanId: "plan-uuid-1",
    patientId: PATIENT_ID,
    toothNumber: null,
    procedureCode: "D2750",
    procedureName: "Crown - porcelain fused to metal",
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
    ...overrides,
  };
}

function makePlan(overrides: Partial<TreatmentPlanDetail>): TreatmentPlanDetail {
  return {
    id: "plan-uuid-1",
    practiceId: PRACTICE_ID,
    patientId: PATIENT_ID,
    name: "Plan A",
    status: "accepted",
    presentedAt: null,
    acceptedAt: null,
    completedAt: null,
    notes: null,
    createdBy: "provider-uuid-1",
    createdAt: "2026-05-04T12:00:00Z",
    updatedAt: "2026-05-04T12:00:00Z",
    items: [],
    ...overrides,
  };
}

describe("groupOpenItemsByTooth", () => {
  it("returns a Map keyed by tooth number with items grouped per tooth", () => {
    const plans: TreatmentPlanDetail[] = [
      makePlan({
        id: "plan-1",
        status: "accepted",
        items: [
          makeItem({ id: "item-1", treatmentPlanId: "plan-1", toothNumber: "14" }),
          makeItem({ id: "item-2", treatmentPlanId: "plan-1", toothNumber: "30" }),
        ],
      }),
      makePlan({
        id: "plan-2",
        status: "in_progress",
        items: [
          // Second item on tooth 14 — should append, not overwrite.
          makeItem({
            id: "item-3",
            treatmentPlanId: "plan-2",
            toothNumber: "14",
            procedureName: "Root canal",
          }),
          // Item without a tooth number — should be skipped.
          makeItem({ id: "item-4", treatmentPlanId: "plan-2", toothNumber: null }),
        ],
      }),
    ];

    const result = groupOpenItemsByTooth(plans);

    expect([...result.keys()].sort()).toEqual(["14", "30"]);
    expect(result.get("14")?.map((i) => i.id)).toEqual(["item-1", "item-3"]);
    expect(result.get("30")?.map((i) => i.id)).toEqual(["item-2"]);
  });

  it("skips items belonging to plans in terminal statuses", () => {
    const plans: TreatmentPlanDetail[] = [
      makePlan({
        id: "plan-done",
        status: "completed",
        items: [makeItem({ id: "item-done", toothNumber: "14" })],
      }),
      makePlan({
        id: "plan-refused",
        status: "refused",
        items: [makeItem({ id: "item-refused", toothNumber: "30" })],
      }),
    ];

    const result = groupOpenItemsByTooth(plans);
    expect(result.size).toBe(0);
  });

  it("returns an empty Map when there are no plans", () => {
    const result = groupOpenItemsByTooth([]);
    expect(result.size).toBe(0);
  });
});
