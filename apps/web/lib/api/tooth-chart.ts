import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";

// ── Types ─────────────────────────────────────────────────────────────────────

export type ConditionType =
  | "existing_restoration"
  | "missing"
  | "implant"
  | "crown"
  | "bridge_pontic"
  | "bridge_abutment"
  | "root_canal"
  | "decay"
  | "fracture"
  | "watch"
  | "other";

export type NotationSystem = "universal" | "fdi";
export type ToothConditionStatus = "existing" | "treatment_planned" | "completed_today";

// Normalized tooth-surface codes shared with the API.
//   B = buccal/facial, M = mesial, O = occlusal, D = distal, L = lingual,
//   I = incisal (anterior teeth — used in place of O).
export type ToothSurface = "B" | "M" | "O" | "D" | "L" | "I";

// Vertical position. Crown (default) is everything coronal of the gumline;
// cervical is the gingival third / Class V; root is below the gumline.
export type VerticalZone = "crown" | "cervical" | "root";

export interface ToothCondition {
  id: string;
  practiceId: string;
  patientId: string;
  toothNumber: string;
  notationSystem: NotationSystem;
  conditionType: ConditionType;
  surface: string | null;
  surfaces: ToothSurface[];
  material: string | null;
  notes: string | null;
  status: ToothConditionStatus;
  verticalZone: VerticalZone;
  recordedAt: string;
  recordedBy: string;
  appointmentId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ToothChartResponse {
  conditions: ToothCondition[];
}

export interface CreateToothConditionBody {
  toothNumber: string;
  notationSystem?: NotationSystem;
  conditionType: ConditionType;
  surface?: string;
  surfaces?: ToothSurface[];
  material?: string;
  notes?: string;
  status?: ToothConditionStatus;
  verticalZone?: VerticalZone;
  recordedAt: string;
  recordedBy: string;
  appointmentId?: string;
}

export interface UpdateToothConditionBody {
  status?: ToothConditionStatus;
  surface?: string;
  surfaces?: ToothSurface[];
  material?: string;
  notes?: string;
  verticalZone?: VerticalZone;
}

// ── API functions ─────────────────────────────────────────────────────────────

export async function getToothChart(
  patientId: string,
  asOfDate?: string,
): Promise<ToothChartResponse> {
  const params = new URLSearchParams();
  if (asOfDate) params.set("as_of_date", asOfDate);
  const qs = params.toString();
  return apiClient.get<ToothChartResponse>(
    `/api/v1/patients/${patientId}/tooth-chart${qs ? `?${qs}` : ""}`,
  );
}

export async function addToothCondition(
  patientId: string,
  body: CreateToothConditionBody,
): Promise<ToothCondition> {
  return apiClient.post<ToothCondition>(
    `/api/v1/patients/${patientId}/tooth-chart/conditions`,
    body,
    { idempotencyKey: generateId() },
  );
}

export async function updateToothCondition(
  patientId: string,
  conditionId: string,
  body: UpdateToothConditionBody,
): Promise<ToothCondition> {
  return apiClient.patch<ToothCondition>(
    `/api/v1/patients/${patientId}/tooth-chart/conditions/${conditionId}`,
    body,
    { idempotencyKey: generateId() },
  );
}

export async function deleteToothCondition(
  patientId: string,
  conditionId: string,
): Promise<void> {
  return apiClient.delete<void>(
    `/api/v1/patients/${patientId}/tooth-chart/conditions/${conditionId}`,
    { idempotencyKey: generateId() },
  );
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const toothChartKeys = {
  chart: (patientId: string, asOfDate?: string) =>
    ["toothChart", patientId, "chart", asOfDate ?? "current"] as const,
};

// ── Hooks ─────────────────────────────────────────────────────────────────────

export function useToothChart(
  patientId: string,
  asOfDate?: string,
): UseQueryResult<ToothChartResponse> {
  return useQuery({
    queryKey: toothChartKeys.chart(patientId, asOfDate),
    queryFn: () => getToothChart(patientId, asOfDate),
    enabled: Boolean(patientId),
  });
}

export function useAddToothCondition(
  patientId: string,
): UseMutationResult<ToothCondition, Error, CreateToothConditionBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateToothConditionBody) => addToothCondition(patientId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["toothChart", patientId],
      });
    },
  });
}

export function useUpdateToothCondition(
  patientId: string,
): UseMutationResult<ToothCondition, Error, { conditionId: string; body: UpdateToothConditionBody }> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ conditionId, body }) =>
      updateToothCondition(patientId, conditionId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["toothChart", patientId],
      });
    },
  });
}

export function useDeleteToothCondition(
  patientId: string,
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (conditionId: string) => deleteToothCondition(patientId, conditionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["toothChart", patientId],
      });
    },
  });
}
