import type { TreatmentPlanItem } from "@/lib/api/treatment-plans";

/** Returns true when the tooth has at least one open treatment-planned item. */
export function hasTreatmentPlannedItem(
  treatmentItemsByTooth: Map<string, TreatmentPlanItem[]> | undefined,
  toothNumber: string,
): boolean {
  const items = treatmentItemsByTooth?.get(toothNumber);
  return Boolean(items && items.length > 0);
}
