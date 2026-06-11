import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";

// ── Types ─────────────────────────────────────────────────────────────────────

export type CdtCategory =
  | "diagnostic"
  | "preventive"
  | "basic"
  | "major"
  | "ortho"
  | "other";

export type EstimateSource = "manual" | "eligibility" | "prior_eob";

export interface CdtCode {
  id: string;
  code: string;
  description: string;
  category: CdtCategory;
  defaultFeeCents: number | null;
  resolvedFeeCents: number | null;
  isActive: boolean;
}

export interface AppointmentProcedure {
  id: string;
  practiceId: string;
  appointmentId: string;
  patientId: string;
  cdtCodeId: string | null;
  procedureCode: string | null;
  procedureName: string;
  toothNumber: string | null;
  surface: string | null;
  feeCents: number;
  insuranceEstCents: number | null;
  patientEstCents: number | null;
  estimateSource: EstimateSource | null;
  notes: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ProcedureTotals {
  feeCentsTotal: number;
  insuranceEstCentsTotal: number;
  patientEstCentsTotal: number;
}

export interface AppointmentProcedureListResponse {
  items: AppointmentProcedure[];
  totals: ProcedureTotals;
}

export interface CreateAppointmentProcedureBody {
  cdtCodeId?: string;
  procedureCode?: string;
  procedureName: string;
  toothNumber?: string;
  surface?: string;
  feeCents: number;
  insuranceEstCents?: number;
  patientEstCents?: number;
  estimateSource?: EstimateSource;
  notes?: string;
}

export type UpdateAppointmentProcedureBody = Partial<CreateAppointmentProcedureBody>;

// ── API functions ─────────────────────────────────────────────────────────────

export async function searchCdtCodes(q: string): Promise<CdtCode[]> {
  return apiClient.get<CdtCode[]>(
    `/api/v1/cdt-codes${q ? `?q=${encodeURIComponent(q)}` : ""}`,
  );
}

export async function listAppointmentProcedures(
  appointmentId: string,
): Promise<AppointmentProcedureListResponse> {
  return apiClient.get<AppointmentProcedureListResponse>(
    `/api/v1/appointments/${appointmentId}/procedures`,
  );
}

export async function listPatientProcedures(
  patientId: string,
): Promise<AppointmentProcedureListResponse> {
  return apiClient.get<AppointmentProcedureListResponse>(
    `/api/v1/patients/${patientId}/procedures`,
  );
}

export async function createAppointmentProcedure(
  appointmentId: string,
  body: CreateAppointmentProcedureBody,
): Promise<AppointmentProcedure> {
  return apiClient.post<AppointmentProcedure>(
    `/api/v1/appointments/${appointmentId}/procedures`,
    body,
    { idempotencyKey: generateId() },
  );
}

export async function updateAppointmentProcedure(
  appointmentId: string,
  procedureId: string,
  body: UpdateAppointmentProcedureBody,
): Promise<AppointmentProcedure> {
  return apiClient.patch<AppointmentProcedure>(
    `/api/v1/appointments/${appointmentId}/procedures/${procedureId}`,
    body,
    { idempotencyKey: generateId() },
  );
}

export async function deleteAppointmentProcedure(
  appointmentId: string,
  procedureId: string,
): Promise<void> {
  return apiClient.delete<void>(
    `/api/v1/appointments/${appointmentId}/procedures/${procedureId}`,
    { idempotencyKey: generateId() },
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Pure helper — format an integer cents amount as a USD string. Exported for tests. */
export function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

/** Pure helper — decide the fee field's dollar value when a CDT code is picked.
 * Never clobbers a value the user already typed; blank when no fee resolves.
 * Exported for tests. */
export function prefillFeeDollars(currentFee: string, resolvedFeeCents: number | null): string {
  if (currentFee || resolvedFeeCents == null) return currentFee;
  return (resolvedFeeCents / 100).toString();
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const procedureKeys = {
  list: (appointmentId: string) => ["appointmentProcedures", appointmentId] as const,
};

// ── Hooks ─────────────────────────────────────────────────────────────────────

export function useAppointmentProcedures(
  appointmentId: string,
): UseQueryResult<AppointmentProcedureListResponse> {
  return useQuery({
    queryKey: procedureKeys.list(appointmentId),
    queryFn: () => listAppointmentProcedures(appointmentId),
    enabled: Boolean(appointmentId),
  });
}

export function usePatientProcedures(
  patientId: string,
): UseQueryResult<AppointmentProcedureListResponse> {
  return useQuery({
    queryKey: ["patientProcedures", patientId],
    queryFn: () => listPatientProcedures(patientId),
    enabled: Boolean(patientId),
  });
}

export function useCreateAppointmentProcedure(
  appointmentId: string,
): UseMutationResult<AppointmentProcedure, Error, CreateAppointmentProcedureBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateAppointmentProcedureBody) =>
      createAppointmentProcedure(appointmentId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: procedureKeys.list(appointmentId) });
    },
  });
}

export function useUpdateAppointmentProcedure(
  appointmentId: string,
): UseMutationResult<
  AppointmentProcedure,
  Error,
  { procedureId: string; body: UpdateAppointmentProcedureBody }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ procedureId, body }) =>
      updateAppointmentProcedure(appointmentId, procedureId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: procedureKeys.list(appointmentId) });
    },
  });
}

export function useDeleteAppointmentProcedure(
  appointmentId: string,
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (procedureId: string) =>
      deleteAppointmentProcedure(appointmentId, procedureId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: procedureKeys.list(appointmentId) });
    },
  });
}

export function useCdtCodeSearch(q: string): UseQueryResult<CdtCode[]> {
  return useQuery({
    queryKey: ["cdtCodes", q],
    queryFn: () => searchCdtCodes(q),
    enabled: q.length >= 1,
  });
}
