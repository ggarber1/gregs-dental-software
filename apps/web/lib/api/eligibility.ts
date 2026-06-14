import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";

// ── Types ─────────────────────────────────────────────────────────────────────

export type EligibilityStatus = "pending" | "verified" | "failed" | "not_supported";
export type CoverageStatus = "active" | "inactive" | "unknown";

export interface EligibilityCheck {
  id: string;
  practiceId: string;
  patientId: string;
  patientInsuranceId: string;
  appointmentId: string | null;
  idempotencyKey: string;
  status: EligibilityStatus;
  trigger: string;
  clearinghouse: string;
  payerIdUsed: string;
  payerName: string | null;
  planName: string | null;
  failureReason: string | null;
  coverageStatus: CoverageStatus | null;
  coverageStartDate: string | null;
  coverageEndDate: string | null;
  deductibleIndividual: number | null; // cents
  deductibleIndividualMet: number | null;
  oopMaxIndividual: number | null;
  annualMaxIndividual: number | null;
  annualMaxIndividualRemaining: number | null;
  coinsurancePreventive: number | null; // patient share fraction
  coinsuranceBasic: number | null;
  coinsuranceMajor: number | null;
  coinsuranceOrtho: number | null;
  verifiedAt: string | null;
  requestedAt: string;
  createdAt: string;
  updatedAt: string;
}

export interface CreateEligibilityCheckBody {
  patientInsuranceId: string;
  appointmentId?: string | null;
}

// ── API functions ─────────────────────────────────────────────────────────────

export async function listEligibilityChecks(patientId: string): Promise<EligibilityCheck[]> {
  return apiClient.get<EligibilityCheck[]>(`/api/v1/eligibility?patient_id=${patientId}`);
}

export async function createEligibilityCheck(
  body: CreateEligibilityCheckBody,
): Promise<EligibilityCheck> {
  return apiClient.post<EligibilityCheck>(`/api/v1/eligibility/check`, body, {
    idempotencyKey: generateId(),
  });
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const eligibilityKeys = {
  all: (patientId: string) => ["eligibility", patientId] as const,
};

// ── Hooks ─────────────────────────────────────────────────────────────────────

export function usePatientEligibility(
  patientId: string,
  enabled = true,
): UseQueryResult<EligibilityCheck[]> {
  return useQuery({
    queryKey: eligibilityKeys.all(patientId),
    queryFn: () => listEligibilityChecks(patientId),
    enabled: Boolean(patientId) && enabled,
  });
}

export function useCreateEligibilityCheck(
  patientId: string,
): UseMutationResult<EligibilityCheck, Error, CreateEligibilityCheckBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateEligibilityCheckBody) => createEligibilityCheck(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: eligibilityKeys.all(patientId) });
    },
  });
}
