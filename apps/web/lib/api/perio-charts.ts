import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";

// ── Types ─────────────────────────────────────────────────────────────────────

export type PerioSite = "db" | "b" | "mb" | "dl" | "l" | "ml";
export type Furcation = "I" | "II" | "III";

export interface PerioReadingCreate {
  toothNumber: string;
  site: PerioSite;
  probingDepthMm: number;
  recessionMm?: number;
  bleeding?: boolean;
  suppuration?: boolean;
  furcation?: Furcation | null;
  mobility?: number | null;
}

export interface PerioReadingOut {
  id: string;
  perioChartId: string;
  toothNumber: string;
  site: PerioSite;
  probingDepthMm: number;
  recessionMm: number;
  cal: number;
  bleeding: boolean;
  suppuration: boolean;
  furcation: Furcation | null;
  mobility: number | null;
  createdAt: string;
}

export interface PerioChartCreate {
  providerId: string;
  chartDate: string;
  appointmentId?: string;
  notes?: string;
  readings?: PerioReadingCreate[];
}

export interface PerioChartSummary {
  id: string;
  practiceId: string;
  patientId: string;
  appointmentId: string | null;
  providerId: string;
  chartDate: string;
  notes: string | null;
  avgProbingDepthMm: number;
  sitesGte4mm: number;
  sitesGte6mm: number;
  bleedingSiteCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface PerioChartDetail extends PerioChartSummary {
  readings: PerioReadingOut[];
}

export interface PerioChartListResponse {
  items: PerioChartSummary[];
  nextCursor: string | null;
  hasMore: boolean;
}

export interface PerioSiteDelta {
  toothNumber: string;
  site: PerioSite;
  depthA: number;
  depthB: number;
  delta: number;
}

export interface PerioChartComparison {
  chartA: PerioChartDetail;
  chartB: PerioChartDetail;
  deltas: PerioSiteDelta[];
}

// ── API functions ─────────────────────────────────────────────────────────────

const base = (patientId: string) => `/api/v1/patients/${patientId}/perio-charts`;

export async function listPerioCharts(
  patientId: string,
  cursor?: string,
): Promise<PerioChartListResponse> {
  const params = new URLSearchParams();
  if (cursor) params.set("cursor", cursor);
  const qs = params.toString();
  return apiClient.get<PerioChartListResponse>(`${base(patientId)}${qs ? `?${qs}` : ""}`);
}

export async function getPerioChart(
  patientId: string,
  chartId: string,
): Promise<PerioChartDetail> {
  return apiClient.get<PerioChartDetail>(`${base(patientId)}/${chartId}`);
}

export async function createPerioChart(
  patientId: string,
  body: PerioChartCreate,
): Promise<PerioChartDetail> {
  return apiClient.post<PerioChartDetail>(base(patientId), body, {
    idempotencyKey: generateId(),
  });
}

export async function upsertPerioReadings(
  patientId: string,
  chartId: string,
  readings: PerioReadingCreate[],
): Promise<PerioChartDetail> {
  return apiClient.post<PerioChartDetail>(
    `${base(patientId)}/${chartId}/readings`,
    { readings },
    { idempotencyKey: generateId() },
  );
}

export async function deletePerioChart(
  patientId: string,
  chartId: string,
): Promise<void> {
  return apiClient.delete<void>(`${base(patientId)}/${chartId}`, {
    idempotencyKey: generateId(),
  });
}

export async function comparePerioCharts(
  patientId: string,
  chartAId: string,
  chartBId: string,
): Promise<PerioChartComparison> {
  const params = new URLSearchParams({ chartA: chartAId, chartB: chartBId });
  return apiClient.get<PerioChartComparison>(`${base(patientId)}/compare?${params}`);
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const perioChartKeys = {
  list: (patientId: string) => ["perioCharts", patientId, "list"] as const,
  detail: (patientId: string, chartId: string) =>
    ["perioCharts", patientId, "detail", chartId] as const,
  compare: (patientId: string, chartAId: string, chartBId: string) =>
    ["perioCharts", patientId, "compare", chartAId, chartBId] as const,
};

// ── Hooks ─────────────────────────────────────────────────────────────────────

export function usePerioCharts(patientId: string): UseQueryResult<PerioChartListResponse> {
  return useQuery({
    queryKey: perioChartKeys.list(patientId),
    queryFn: () => listPerioCharts(patientId),
    enabled: Boolean(patientId),
  });
}

export function usePerioChart(
  patientId: string,
  chartId: string | null,
): UseQueryResult<PerioChartDetail> {
  return useQuery({
    queryKey: perioChartKeys.detail(patientId, chartId ?? ""),
    queryFn: () => getPerioChart(patientId, chartId!),
    enabled: Boolean(patientId) && Boolean(chartId),
  });
}

export function useCreatePerioChart(
  patientId: string,
): UseMutationResult<PerioChartDetail, Error, PerioChartCreate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PerioChartCreate) => createPerioChart(patientId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["perioCharts", patientId] });
    },
  });
}

export function useDeletePerioChart(
  patientId: string,
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (chartId: string) => deletePerioChart(patientId, chartId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["perioCharts", patientId] });
    },
  });
}

export function useComparePerioCharts(
  patientId: string,
  chartAId: string | null,
  chartBId: string | null,
): UseQueryResult<PerioChartComparison> {
  return useQuery({
    queryKey: perioChartKeys.compare(patientId, chartAId ?? "", chartBId ?? ""),
    queryFn: () => comparePerioCharts(patientId, chartAId!, chartBId!),
    enabled: Boolean(patientId) && Boolean(chartAId) && Boolean(chartBId),
  });
}
