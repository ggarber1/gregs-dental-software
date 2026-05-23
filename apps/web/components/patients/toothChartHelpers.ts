import type {
  TreatmentPlanItem,
  TreatmentPlanItemUrgency,
} from "@/lib/api/treatment-plans";

/** Returns true when the tooth has at least one open treatment-planned item. */
export function hasTreatmentPlannedItem(
  treatmentItemsByTooth: Map<string, TreatmentPlanItem[]> | undefined,
  toothNumber: string,
): boolean {
  const items = treatmentItemsByTooth?.get(toothNumber);
  return Boolean(items && items.length > 0);
}

// Worst-status-wins: urgent beats soon beats elective. Used to color the
// tooth chart's treatment-planned badge so urgent items pop at a glance.
export function highestUrgency(
  items: TreatmentPlanItem[],
): TreatmentPlanItemUrgency | null {
  if (items.length === 0) return null;
  if (items.some((i) => i.urgency === "urgent")) return "urgent";
  if (items.some((i) => i.urgency === "soon")) return "soon";
  return "elective";
}

const URGENCY_BADGE_COLORS: Record<TreatmentPlanItemUrgency, string> = {
  urgent: "bg-red-600",
  soon: "bg-orange-500",
  elective: "bg-gray-400",
};

export function urgencyBadgeColor(urgency: TreatmentPlanItemUrgency): string {
  return URGENCY_BADGE_COLORS[urgency];
}
