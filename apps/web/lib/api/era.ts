import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";

export interface ERARemittance {
  id: string;
  practiceId: string;
  stediTransactionId: string;
  payerName: string | null;
  traceNumber: string | null;
  paymentCents: number | null;
  paymentDate: string | null;
  claimCount: number | null;
  matchedCount: number | null;
  unmatchedCount: number | null;
  createdAt: string;
}

export interface UnmatchedERAPayment {
  id: string;
  practiceId: string;
  remittanceId: string;
  patientControlNumber: string | null;
  payerClaimControlNumber: string | null;
  paidCents: number | null;
  resolved: boolean;
  resolvedAt: string | null;
  createdAt: string;
}

export interface ERAPollSummary {
  polled: number;
  new: number;
  matched: number;
  unmatched: number;
  remittanceIds: string[];
}

export const eraKeys = {
  remittances: ["era", "remittances"] as const,
  unmatched: (resolved: boolean) => ["era", "unmatched", { resolved }] as const,
};

export function useRemittances() {
  return useQuery({
    queryKey: eraKeys.remittances,
    queryFn: () => apiClient.get<ERARemittance[]>("/api/v1/era/remittances"),
  });
}

export function useUnmatched(resolved = false) {
  return useQuery({
    queryKey: eraKeys.unmatched(resolved),
    queryFn: () =>
      apiClient.get<UnmatchedERAPayment[]>(`/api/v1/era/unmatched?resolved=${resolved}`),
  });
}

export function usePollEras() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiClient.post<ERAPollSummary>("/api/v1/era/poll", {}, { idempotencyKey: generateId() }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: eraKeys.remittances });
      void qc.invalidateQueries({ queryKey: ["era", "unmatched"] });
      void qc.invalidateQueries({ queryKey: ["claims"] });
    },
  });
}

export function useResolveUnmatched() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.post<UnmatchedERAPayment>(
        `/api/v1/era/unmatched/${id}/resolve`,
        {},
        { idempotencyKey: generateId() },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["era", "unmatched"] });
    },
  });
}
