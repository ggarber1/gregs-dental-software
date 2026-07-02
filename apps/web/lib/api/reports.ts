import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, generateId } from "@/lib/api-client";

export type ARCategory = "awaiting" | "underpaid" | "problem" | "appealing";
export type AgeBucket = "0-30" | "31-60" | "61-90" | "90+";

export interface InsuranceARRow {
  claimId: string;
  appointmentId: string;
  patientId: string;
  claimNumber: string;
  patientName: string;
  payerId: string;
  carrierName: string;
  category: ARCategory;
  billedCents: number;
  estimatedInsuranceCents: number | null;
  insurancePaidCents: number | null;
  shortfallCents: number | null;
  hasEstimate: boolean;
  daysOut: number;
  bucket: AgeBucket;
  status: string;
  reason: string | null;
}

export interface ARBuckets {
  b0_30: number;
  b31_60: number;
  b61_90: number;
  b90_plus: number;
}

export interface InsuranceARCarrierSummary {
  payerId: string;
  carrierName: string;
  claimCount: number;
  buckets: ARBuckets;
  totalBilledCents: number;
  expectedCents: number;
  unestimatedCount: number;
  underpaidCount: number;
  problemCount: number;
}

export interface InsuranceARSummary {
  carriers: InsuranceARCarrierSummary[];
  totals: Omit<InsuranceARCarrierSummary, "payerId" | "carrierName">;
}

export const reportsKeys = {
  all: ["reports"] as const,
  worklist: (category?: string) =>
    ["reports", "insurance-ar", "worklist", { category: category ?? null }] as const,
  summary: ["reports", "insurance-ar", "summary"] as const,
};

export function useInsuranceARWorklist(category?: ARCategory) {
  const query = category ? `?category=${encodeURIComponent(category)}` : "";
  return useQuery({
    queryKey: reportsKeys.worklist(category),
    queryFn: () =>
      apiClient.get<InsuranceARRow[]>(`/api/v1/reports/insurance-ar/claims${query}`),
  });
}

export function useInsuranceARSummary() {
  return useQuery({
    queryKey: reportsKeys.summary,
    queryFn: () =>
      apiClient.get<InsuranceARSummary>("/api/v1/reports/insurance-ar/summary"),
  });
}

function useClaimAction(action: "accept" | "appeal") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (claimId: string) =>
      apiClient.post(
        `/api/v1/reports/insurance-ar/claims/${claimId}/${action}`,
        {},
        { idempotencyKey: generateId() },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: reportsKeys.all });
      void qc.invalidateQueries({ queryKey: ["claims"] });
    },
  });
}

export function useAcceptUnderpayment() {
  return useClaimAction("accept");
}

export function useFlagForAppeal() {
  return useClaimAction("appeal");
}

export function centsToUsd(cents: number | null): string {
  if (cents === null) return "—";
  return `$${(cents / 100).toFixed(2)}`;
}
