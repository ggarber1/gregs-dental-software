import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface InsurancePlan {
  id: string;
  practiceId: string;
  carrierName: string;
  payerId: string;
  groupNumber: string | null;
  isInNetwork: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface CreateInsurancePlanBody {
  carrierName: string;
  payerId: string;
  groupNumber?: string | null;
  isInNetwork?: boolean;
}

export interface UpdateInsurancePlanBody {
  carrierName?: string;
  payerId?: string;
  groupNumber?: string | null;
  isInNetwork?: boolean;
}

// ── API functions ─────────────────────────────────────────────────────────────

export async function listInsurancePlans(): Promise<InsurancePlan[]> {
  return apiClient.get<InsurancePlan[]>("/api/v1/insurance-plans");
}

export async function createInsurancePlan(body: CreateInsurancePlanBody): Promise<InsurancePlan> {
  return apiClient.post<InsurancePlan>("/api/v1/insurance-plans", body, {
    idempotencyKey: generateId(),
  });
}

export async function updateInsurancePlan(
  planId: string,
  body: UpdateInsurancePlanBody,
): Promise<InsurancePlan> {
  return apiClient.patch<InsurancePlan>(`/api/v1/insurance-plans/${planId}`, body, {
    idempotencyKey: generateId(),
  });
}

export async function deleteInsurancePlan(planId: string): Promise<void> {
  await apiClient.delete(`/api/v1/insurance-plans/${planId}`, {
    idempotencyKey: generateId(),
  });
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const insurancePlanKeys = {
  all: () => ["insurance-plans"] as const,
};

// ── Hooks ─────────────────────────────────────────────────────────────────────

export function useInsurancePlans(): UseQueryResult<InsurancePlan[]> {
  return useQuery({
    queryKey: insurancePlanKeys.all(),
    queryFn: listInsurancePlans,
  });
}

export function useCreateInsurancePlan(): UseMutationResult<
  InsurancePlan,
  Error,
  CreateInsurancePlanBody
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createInsurancePlan,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: insurancePlanKeys.all() });
    },
  });
}

export function useUpdateInsurancePlan(
  planId: string,
): UseMutationResult<InsurancePlan, Error, UpdateInsurancePlanBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateInsurancePlanBody) => updateInsurancePlan(planId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: insurancePlanKeys.all() });
    },
  });
}

export function useDeleteInsurancePlan(): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteInsurancePlan,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: insurancePlanKeys.all() });
    },
  });
}
