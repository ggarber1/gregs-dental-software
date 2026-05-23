import { describe, it, expect } from "vitest";

import {
  shouldShowHoverCard,
  formatHoverConditionLine,
  centerSurfaceCode,
  isAnteriorTooth,
  surfaceCellsForTooth,
  surfaceFillColors,
} from "@/components/patients/ToothChartCard";
import {
  hasTreatmentPlannedItem,
  highestUrgency,
  urgencyBadgeColor,
} from "@/components/patients/toothChartHelpers";
import type { ToothCondition } from "@/lib/api/tooth-chart";
import type {
  TreatmentPlanItem,
  TreatmentPlanItemUrgency,
} from "@/lib/api/treatment-plans";

const mkCondition = (overrides: Partial<ToothCondition> = {}): ToothCondition => ({
  id: "c-1",
  practiceId: "p-1",
  patientId: "pt-1",
  toothNumber: "14",
  notationSystem: "universal",
  conditionType: "decay",
  surface: null,
  surfaces: [],
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

describe("shouldShowHoverCard", () => {
  it("shows the card when the tooth is hovered and no tooth is selected", () => {
    expect(shouldShowHoverCard("14", null, "14")).toBe(true);
  });

  it("shows the card when the tooth is hovered and a different tooth is selected", () => {
    expect(shouldShowHoverCard("14", "3", "14")).toBe(true);
  });

  it("hides the card when no tooth is hovered", () => {
    expect(shouldShowHoverCard(null, null, "14")).toBe(false);
  });

  it("hides the card on teeth other than the hovered one", () => {
    expect(shouldShowHoverCard("14", null, "3")).toBe(false);
  });

  it("suppresses the card when the hovered tooth is also the selected tooth", () => {
    expect(shouldShowHoverCard("14", "14", "14")).toBe(false);
  });
});

describe("formatHoverConditionLine", () => {
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

describe("isAnteriorTooth", () => {
  it("treats teeth 6-11 (upper incisors + canines) as anterior", () => {
    for (const t of [6, 7, 8, 9, 10, 11]) {
      expect(isAnteriorTooth(String(t))).toBe(true);
    }
  });

  it("treats teeth 22-27 (lower incisors + canines) as anterior", () => {
    for (const t of [22, 23, 24, 25, 26, 27]) {
      expect(isAnteriorTooth(String(t))).toBe(true);
    }
  });

  it("treats premolars and molars as posterior", () => {
    for (const t of [1, 2, 3, 4, 5, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 28, 29, 30, 31, 32]) {
      expect(isAnteriorTooth(String(t))).toBe(false);
    }
  });

  it("treats non-numeric (deciduous) tooth IDs as non-anterior", () => {
    expect(isAnteriorTooth("A")).toBe(false);
  });
});

describe("centerSurfaceCode", () => {
  it("returns 'I' for anterior teeth (incisal edge)", () => {
    expect(centerSurfaceCode("8")).toBe("I");
    expect(centerSurfaceCode("24")).toBe("I");
  });

  it("returns 'O' for posterior teeth (occlusal surface)", () => {
    expect(centerSurfaceCode("3")).toBe("O");
    expect(centerSurfaceCode("14")).toBe("O");
    expect(centerSurfaceCode("30")).toBe("O");
  });
});

describe("surfaceCellsForTooth", () => {
  it("labels the center cell 'O' on a molar (tooth 14)", () => {
    const cells = surfaceCellsForTooth("14");
    expect(cells.map((c) => c.label)).toEqual(["B", "M", "O", "D", "L"]);
  });

  it("labels the center cell 'I' on an anterior (tooth 8)", () => {
    const cells = surfaceCellsForTooth("8");
    expect(cells.map((c) => c.label)).toEqual(["B", "M", "I", "D", "L"]);
  });
});

describe("surfaceFillColors", () => {
  it("fills only the buccal cell when a condition has surfaces=['B']", () => {
    const result = surfaceFillColors(
      [mkCondition({ conditionType: "decay", surfaces: ["B"] })],
      "14",
    );
    expect(result.B).not.toBeNull();
    expect(result.M).toBeNull();
    expect(result.O).toBeNull();
    expect(result.D).toBeNull();
    expect(result.L).toBeNull();
  });

  it("fills all cells when a whole-tooth condition has no surfaces", () => {
    const result = surfaceFillColors(
      [mkCondition({ conditionType: "crown", surfaces: [] })],
      "14",
    );
    expect(result.B).not.toBeNull();
    expect(result.M).not.toBeNull();
    expect(result.O).not.toBeNull();
    expect(result.D).not.toBeNull();
    expect(result.L).not.toBeNull();
  });

  it("fills the I (incisal) slot for anterior teeth, not O", () => {
    const result = surfaceFillColors(
      [mkCondition({ conditionType: "decay", surfaces: ["I"] })],
      "8",
    );
    expect(result.I).not.toBeNull();
    expect(result.O).toBeNull();
  });

  it("returns no fills for an empty conditions list", () => {
    const result = surfaceFillColors([], "14");
    expect(result.B).toBeNull();
    expect(result.M).toBeNull();
    expect(result.O).toBeNull();
    expect(result.D).toBeNull();
    expect(result.L).toBeNull();
  });

  it("higher-priority condition wins per surface", () => {
    const watchColor = surfaceFillColors(
      [mkCondition({ id: "w", conditionType: "watch", surfaces: ["M"] })],
      "14",
    ).M;
    const decayColor = surfaceFillColors(
      [mkCondition({ id: "d", conditionType: "decay", surfaces: ["M"] })],
      "14",
    ).M;

    const combined = surfaceFillColors(
      [
        mkCondition({ id: "w", conditionType: "watch", surfaces: ["M"] }),
        mkCondition({ id: "d", conditionType: "decay", surfaces: ["M"] }),
      ],
      "14",
    ).M;

    expect(combined).toBe(decayColor);
    expect(combined).not.toBe(watchColor);
  });
});

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
