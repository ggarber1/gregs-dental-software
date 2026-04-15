import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";

// ── Types ─────────────────────────────────────────────────────────────────────

export type InsurancePriority = "primary" | "secondary";
export type RelationshipToInsured = "self" | "spouse" | "child" | "other";

export interface Insurance {
  id: string;
  patientId: string;
  practiceId: string;
  priority: InsurancePriority;
  carrier: string;
  memberId: string | null;
  groupNumber: string | null;
  relationshipToInsured: RelationshipToInsured;
  insuredFirstName: string | null;
  insuredLastName: string | null;
  insuredDateOfBirth: string | null; // ISO date YYYY-MM-DD
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface CreateInsuranceBody {
  priority?: InsurancePriority;
  carrier: string;
  memberId?: string | null;
  groupNumber?: string | null;
  relationshipToInsured?: RelationshipToInsured;
  insuredFirstName?: string | null;
  insuredLastName?: string | null;
  insuredDateOfBirth?: string | null;
}

export interface UpdateInsuranceBody {
  priority?: InsurancePriority;
  carrier?: string;
  memberId?: string | null;
  groupNumber?: string | null;
  relationshipToInsured?: RelationshipToInsured;
  insuredFirstName?: string | null;
  insuredLastName?: string | null;
  insuredDateOfBirth?: string | null;
}

// ── API functions ─────────────────────────────────────────────────────────────

export async function listPatientInsurance(patientId: string): Promise<Insurance[]> {
  return apiClient.get<Insurance[]>(`/api/v1/patients/${patientId}/insurance`);
}

export async function createInsurance(
  patientId: string,
  body: CreateInsuranceBody,
): Promise<Insurance> {
  return apiClient.post<Insurance>(`/api/v1/patients/${patientId}/insurance`, body, {
    idempotencyKey: generateId(),
  });
}

export async function updateInsurance(
  patientId: string,
  insuranceId: string,
  body: UpdateInsuranceBody,
): Promise<Insurance> {
  return apiClient.patch<Insurance>(
    `/api/v1/patients/${patientId}/insurance/${insuranceId}`,
    body,
    { idempotencyKey: generateId() },
  );
}

export async function deleteInsurance(patientId: string, insuranceId: string): Promise<void> {
  await apiClient.delete(`/api/v1/patients/${patientId}/insurance/${insuranceId}`, {
    idempotencyKey: generateId(),
  });
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const insuranceKeys = {
  all: (patientId: string) => ["insurance", patientId] as const,
};

// ── Hooks ─────────────────────────────────────────────────────────────────────

export function usePatientInsurance(patientId: string): UseQueryResult<Insurance[]> {
  return useQuery({
    queryKey: insuranceKeys.all(patientId),
    queryFn: () => listPatientInsurance(patientId),
    enabled: Boolean(patientId),
  });
}

export function useCreateInsurance(
  patientId: string,
): UseMutationResult<Insurance, Error, CreateInsuranceBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateInsuranceBody) => createInsurance(patientId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: insuranceKeys.all(patientId) });
    },
  });
}

export function useUpdateInsurance(
  patientId: string,
  insuranceId: string,
): UseMutationResult<Insurance, Error, UpdateInsuranceBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateInsuranceBody) => updateInsurance(patientId, insuranceId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: insuranceKeys.all(patientId) });
    },
  });
}

export function useDeleteInsurance(
  patientId: string,
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (insuranceId: string) => deleteInsurance(patientId, insuranceId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: insuranceKeys.all(patientId) });
    },
  });
}
