import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";

// ── Types ─────────────────────────────────────────────────────────────────────

export type TreatmentPlanStatus =
  | "proposed"
  | "accepted"
  | "in_progress"
  | "completed"
  | "refused"
  | "superseded";

export type TreatmentPlanItemStatus =
  | "proposed"
  | "accepted"
  | "scheduled"
  | "completed"
  | "refused";

export interface TreatmentPlan {
  id: string;
  practiceId: string;
  patientId: string;
  name: string;
  status: TreatmentPlanStatus;
  presentedAt: string | null;
  acceptedAt: string | null;
  completedAt: string | null;
  notes: string | null;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
}

export interface TreatmentPlanItem {
  id: string;
  practiceId: string;
  treatmentPlanId: string;
  patientId: string;
  toothNumber: string | null;
  procedureCode: string;
  procedureName: string;
  surface: string | null;
  feeCents: number;
  insuranceEstCents: number | null;
  patientEstCents: number | null;
  status: TreatmentPlanItemStatus;
  priority: number;
  appointmentId: string | null;
  completedAppointmentId: string | null;
  notes: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface TreatmentPlanDetail extends TreatmentPlan {
  items: TreatmentPlanItem[];
}

export interface TreatmentPlanListResponse {
  items: TreatmentPlan[];
  nextCursor: string | null;
  hasMore: boolean;
}

export interface OpenPlanQueueItem {
  planId: string;
  planName: string;
  patientId: string;
  patientName: string;
  pendingItemCount: number;
  daysSinceAcceptance: number;
  acceptedAt: string | null;
}

export interface CreateTreatmentPlanItemBody {
  toothNumber?: string;
  procedureCode: string;
  procedureName: string;
  surface?: string;
  feeCents: number;
  insuranceEstCents?: number;
  patientEstCents?: number;
  priority?: number;
  notes?: string;
}

export interface CreateTreatmentPlanBody {
  name?: string;
  notes?: string;
  items?: CreateTreatmentPlanItemBody[];
}

export interface UpdateTreatmentPlanBody {
  name?: string;
  status?: TreatmentPlanStatus;
  presentedAt?: string;
  notes?: string;
}

export interface UpdateTreatmentPlanItemBody {
  status?: TreatmentPlanItemStatus;
  feeCents?: number;
  insuranceEstCents?: number;
  patientEstCents?: number;
  appointmentId?: string;
  completedAppointmentId?: string;
  priority?: number;
  notes?: string;
}

// ── API functions ─────────────────────────────────────────────────────────────

export async function listTreatmentPlans(
  patientId: string,
  params?: { status?: TreatmentPlanStatus; cursor?: string; limit?: number },
): Promise<TreatmentPlanListResponse> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.cursor) qs.set("cursor", params.cursor);
  if (params?.limit) qs.set("limit", String(params.limit));
  const query = qs.toString();
  return apiClient.get<TreatmentPlanListResponse>(
    `/api/v1/patients/${patientId}/treatment-plans${query ? `?${query}` : ""}`,
  );
}

export async function getTreatmentPlan(
  patientId: string,
  planId: string,
): Promise<TreatmentPlanDetail> {
  return apiClient.get<TreatmentPlanDetail>(
    `/api/v1/patients/${patientId}/treatment-plans/${planId}`,
  );
}

export async function createTreatmentPlan(
  patientId: string,
  body: CreateTreatmentPlanBody,
): Promise<TreatmentPlanDetail> {
  return apiClient.post<TreatmentPlanDetail>(
    `/api/v1/patients/${patientId}/treatment-plans`,
    body,
    { idempotencyKey: generateId() },
  );
}

export async function updateTreatmentPlan(
  patientId: string,
  planId: string,
  body: UpdateTreatmentPlanBody,
): Promise<TreatmentPlan> {
  return apiClient.patch<TreatmentPlan>(
    `/api/v1/patients/${patientId}/treatment-plans/${planId}`,
    body,
    { idempotencyKey: generateId() },
  );
}

export async function addTreatmentPlanItem(
  patientId: string,
  planId: string,
  body: CreateTreatmentPlanItemBody,
): Promise<TreatmentPlanItem> {
  return apiClient.post<TreatmentPlanItem>(
    `/api/v1/patients/${patientId}/treatment-plans/${planId}/items`,
    body,
    { idempotencyKey: generateId() },
  );
}

export async function updateTreatmentPlanItem(
  patientId: string,
  planId: string,
  itemId: string,
  body: UpdateTreatmentPlanItemBody,
): Promise<TreatmentPlanItem> {
  return apiClient.patch<TreatmentPlanItem>(
    `/api/v1/patients/${patientId}/treatment-plans/${planId}/items/${itemId}`,
    body,
    { idempotencyKey: generateId() },
  );
}

export async function deleteTreatmentPlanItem(
  patientId: string,
  planId: string,
  itemId: string,
): Promise<void> {
  return apiClient.delete<void>(
    `/api/v1/patients/${patientId}/treatment-plans/${planId}/items/${itemId}`,
    { idempotencyKey: generateId() },
  );
}

export async function getOpenTreatmentPlans(): Promise<OpenPlanQueueItem[]> {
  return apiClient.get<OpenPlanQueueItem[]>("/api/v1/treatment-plans/open");
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const treatmentPlanKeys = {
  list: (patientId: string, status?: TreatmentPlanStatus) =>
    ["treatmentPlans", patientId, "list", status ?? "all"] as const,
  detail: (patientId: string, planId: string) =>
    ["treatmentPlans", patientId, "detail", planId] as const,
  openQueue: () => ["treatmentPlans", "open"] as const,
};

// ── Hooks ─────────────────────────────────────────────────────────────────────

export function useTreatmentPlans(
  patientId: string,
  status?: TreatmentPlanStatus,
): UseQueryResult<TreatmentPlanListResponse> {
  return useQuery({
    queryKey: treatmentPlanKeys.list(patientId, status),
    queryFn: () => listTreatmentPlans(patientId, status ? { status } : {}),
    enabled: Boolean(patientId),
  });
}

export function useTreatmentPlanDetail(
  patientId: string,
  planId: string,
): UseQueryResult<TreatmentPlanDetail> {
  return useQuery({
    queryKey: treatmentPlanKeys.detail(patientId, planId),
    queryFn: () => getTreatmentPlan(patientId, planId),
    enabled: Boolean(patientId) && Boolean(planId),
  });
}

export function useCreateTreatmentPlan(
  patientId: string,
): UseMutationResult<TreatmentPlanDetail, Error, CreateTreatmentPlanBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateTreatmentPlanBody) => createTreatmentPlan(patientId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["treatmentPlans", patientId] });
    },
  });
}

export function useUpdateTreatmentPlan(
  patientId: string,
  planId: string,
): UseMutationResult<TreatmentPlan, Error, UpdateTreatmentPlanBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateTreatmentPlanBody) => updateTreatmentPlan(patientId, planId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["treatmentPlans", patientId] });
      void queryClient.invalidateQueries({ queryKey: treatmentPlanKeys.openQueue() });
    },
  });
}

export function useAddTreatmentPlanItem(
  patientId: string,
  planId: string,
): UseMutationResult<TreatmentPlanItem, Error, CreateTreatmentPlanItemBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateTreatmentPlanItemBody) =>
      addTreatmentPlanItem(patientId, planId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: treatmentPlanKeys.detail(patientId, planId),
      });
    },
  });
}

export function useUpdateTreatmentPlanItem(
  patientId: string,
  planId: string,
): UseMutationResult<TreatmentPlanItem, Error, { itemId: string; body: UpdateTreatmentPlanItemBody }> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, body }) => updateTreatmentPlanItem(patientId, planId, itemId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["treatmentPlans", patientId] });
      void queryClient.invalidateQueries({ queryKey: treatmentPlanKeys.openQueue() });
    },
  });
}

export function useDeleteTreatmentPlanItem(
  patientId: string,
  planId: string,
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => deleteTreatmentPlanItem(patientId, planId, itemId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: treatmentPlanKeys.detail(patientId, planId),
      });
    },
  });
}

export function useOpenTreatmentPlanQueue(): UseQueryResult<OpenPlanQueueItem[]> {
  return useQuery({
    queryKey: treatmentPlanKeys.openQueue(),
    queryFn: getOpenTreatmentPlans,
  });
}
