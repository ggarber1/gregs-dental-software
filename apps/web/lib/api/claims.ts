import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";

// ── Types ──────────────────────────────────────────────────────────────────────

export type ClaimStatus =
  | "draft"
  | "submitted"
  | "clearinghouse_rejected"
  | "submission_failed"
  | "acknowledged"
  | "pending"
  | "paid"
  | "partially_paid"
  | "denied"
  | "appealing";

export interface Claim {
  id: string;
  practiceId: string;
  appointmentId: string;
  patientId: string;
  insuranceId: string;
  providerId: string;
  idempotencyKey: string;
  submissionAttempt: number;
  patientControlNumber: string;
  payerId: string;
  status: ClaimStatus;
  totalChargeCents: number;
  clearinghouseClaimId: string | null;
  clearinghouseStatus: string | null;
  submissionErrors: string[] | null;
  insurancePaidCents: number | null;
  patientResponsibilityCents: number | null;
  payerClaimControlNumber: string | null;
  adjustments: Array<{ group: string; code: string; cents: number }> | null;
  denialCodes: string[] | null;
  paidAt: string | null;
  remittanceId: string | null;
  submittedAt: string | null;
  createdAt: string;
  updatedAt: string;
  submissionHistory: Array<{
    attempt: number;
    status: string;
    denialCodes: string[] | null;
    payerCcn: string | null;
    submittedAt: string | null;
  }> | null;
  claimFrequencyCode: string;
  insuranceReviewedAt: string | null;
}

// ── Query keys ─────────────────────────────────────────────────────────────────

export const claimsKeys = {
  all: ["claims"] as const,
  list: (status?: string) => ["claims", { status: status ?? null }] as const,
  appointment: (appointmentId: string) => ["claims", "appointment", appointmentId] as const,
  patient: (patientId: string) => ["claims", "patient", patientId] as const,
};

// ── Hooks ──────────────────────────────────────────────────────────────────────

export function useAppointmentClaims(appointmentId: string) {
  return useQuery({
    queryKey: claimsKeys.appointment(appointmentId),
    queryFn: () => apiClient.get<Claim[]>(`/api/v1/appointments/${appointmentId}/claim`),
  });
}

export function useClaimsList(status?: string) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return useQuery({
    queryKey: claimsKeys.list(status),
    queryFn: () => apiClient.get<Claim[]>(`/api/v1/claims${query}`),
  });
}

export function usePatientClaims(patientId: string) {
  return useQuery({
    queryKey: claimsKeys.patient(patientId),
    queryFn: () =>
      apiClient.get<Claim[]>(`/api/v1/claims?patient_id=${encodeURIComponent(patientId)}`),
  });
}

export interface WriteOffResponse {
  claim: Claim;
  ledgerEntry: string | null;
}

export function useResubmitClaim(claimId: string, appointmentId: string, patientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.post<Claim>(`/api/v1/claims/${claimId}/resubmit`, {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: claimsKeys.appointment(appointmentId) });
      void qc.invalidateQueries({ queryKey: claimsKeys.patient(patientId) });
      void qc.invalidateQueries({ queryKey: claimsKeys.all });
    },
  });
}

export function useWriteOffClaim(claimId: string, appointmentId: string, patientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (memo?: string) =>
      apiClient.post<WriteOffResponse>(`/api/v1/claims/${claimId}/write-off`, { memo }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: claimsKeys.appointment(appointmentId) });
      void qc.invalidateQueries({ queryKey: claimsKeys.patient(patientId) });
      void qc.invalidateQueries({ queryKey: claimsKeys.all });
    },
  });
}

export function useSubmitClaim(appointmentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiClient.post<Claim>(`/api/v1/appointments/${appointmentId}/claim`, {}, {
        idempotencyKey: generateId(),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: claimsKeys.appointment(appointmentId) });
      void qc.invalidateQueries({ queryKey: claimsKeys.all });
    },
  });
}
