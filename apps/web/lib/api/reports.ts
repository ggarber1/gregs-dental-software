import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { apiClient, ApiError, generateId } from "@/lib/api-client";

export type ARCategory = "awaiting" | "underpaid" | "problem";
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

export type ReconciliationLabel =
  | "overpaid"
  | "within_tolerance"
  | "matched"
  | "no_estimate";

export interface ReconciliationRow {
  claimId: string;
  appointmentId: string;
  patientId: string;
  claimNumber: string;
  patientName: string;
  payerId: string;
  carrierName: string;
  reconLabel: ReconciliationLabel;
  billedCents: number;
  estimatedInsuranceCents: number | null;
  insurancePaidCents: number;
  varianceCents: number | null;
  hasEstimate: boolean;
  patientBalanceCents: number;
  daysSinceEra: number;
  reconciliationConfirmedAt: string | null;
}

export interface ARSummary {
  insuranceArTotalCents: number;
  patientArTotalCents: number;
  claimsNeedingAttention: number;
  reconciliationPendingCount: number;
  eraReconciliationMode: "auto" | "confirm";
}

export const reportsKeys = {
  all: ["reports"] as const,
  worklist: (category?: string) =>
    ["reports", "insurance-ar", "worklist", { category: category ?? null }] as const,
  summary: ["reports", "insurance-ar", "summary"] as const,
  reconciliation: (confirmed?: boolean) =>
    ["reports", "reconciliation", { confirmed: confirmed ?? null }] as const,
  arSummary: ["reports", "ar-summary"] as const,
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

function apiErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const body = err.body as { error?: { message?: string } } | null;
    return body?.error?.message ?? `Unexpected error (${err.status})`;
  }
  return "Something went wrong. Please try again.";
}

export function useAcceptUnderpayment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (claimId: string) =>
      apiClient.post(
        `/api/v1/reports/insurance-ar/claims/${claimId}/accept`,
        {},
        { idempotencyKey: generateId() },
      ),
    onSuccess: () => {
      toast.success("Underpayment written off.");
      void qc.invalidateQueries({ queryKey: reportsKeys.all });
      void qc.invalidateQueries({ queryKey: ["claims"] });
    },
    onError: (err) => {
      toast.error(apiErrorMessage(err));
    },
  });
}

export function useReconciliationWorklist(confirmed?: boolean) {
  const query =
    confirmed !== undefined ? `?confirmed=${confirmed}` : "";
  return useQuery({
    queryKey: reportsKeys.reconciliation(confirmed),
    queryFn: () =>
      apiClient.get<ReconciliationRow[]>(
        `/api/v1/reports/reconciliation/claims${query}`,
      ),
  });
}

export function useConfirmReconciliation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (claimId: string) =>
      apiClient.post(
        `/api/v1/reports/reconciliation/claims/${claimId}/confirm`,
        {},
        { idempotencyKey: generateId() },
      ),
    onSuccess: () => {
      toast.success("Reconciliation confirmed.");
      void qc.invalidateQueries({ queryKey: reportsKeys.all });
    },
    onError: (err) => {
      toast.error(apiErrorMessage(err));
    },
  });
}

export function useARSummary() {
  return useQuery({
    queryKey: reportsKeys.arSummary,
    queryFn: () => apiClient.get<ARSummary>("/api/v1/reports/ar-summary"),
  });
}

export function centsToUsd(cents: number | null): string {
  if (cents === null) return "—";
  return `$${(cents / 100).toFixed(2)}`;
}
