import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";

import { apiClient, ApiError, generateId } from "@/lib/api-client";

// ── Types ─────────────────────────────────────────────────────────────────────

export type Sex = "male" | "female" | "other" | "unknown";

export interface Patient {
  id: string;
  practiceId: string;
  firstName: string;
  lastName: string;
  dateOfBirth: string; // ISO date string YYYY-MM-DD
  sex: Sex | null;
  phone: string | null;
  email: string | null;
  addressLine1: string | null;
  addressLine2: string | null;
  city: string | null;
  state: string | null;
  zip: string | null;
  ssnLastFour: string | null;
  allergies: string[];
  medicalAlerts: string[];
  smsOptOut: boolean;
  deletedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface PaginationMeta {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

export interface PatientListResponse {
  data: Patient[];
  meta: PaginationMeta;
}

export interface CreatePatientBody {
  firstName: string;
  lastName: string;
  dateOfBirth: string;
  sex?: Sex | null;
  phone?: string | null;
  email?: string | null;
  addressLine1?: string | null;
  addressLine2?: string | null;
  city?: string | null;
  state?: string | null;
  zip?: string | null;
  ssnLastFour?: string | null;
  allergies?: string[];
  medicalAlerts?: string[];
  smsOptOut?: boolean;
}

export interface UpdatePatientBody {
  firstName?: string;
  lastName?: string;
  dateOfBirth?: string;
  sex?: Sex | null;
  phone?: string | null;
  email?: string | null;
  addressLine1?: string | null;
  addressLine2?: string | null;
  city?: string | null;
  state?: string | null;
  zip?: string | null;
  ssnLastFour?: string | null;
  allergies?: string[];
  medicalAlerts?: string[];
  smsOptOut?: boolean;
}

export interface ListPatientsParams {
  q?: string;
  page?: number;
  pageSize?: number;
}

// ── API functions ─────────────────────────────────────────────────────────────

export async function listPatients(params: ListPatientsParams = {}): Promise<PatientListResponse> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.page) qs.set("page", String(params.page));
  if (params.pageSize) qs.set("page_size", String(params.pageSize));
  const query = qs.toString();
  return apiClient.get<PatientListResponse>(`/api/v1/patients${query ? `?${query}` : ""}`);
}

export async function getPatient(id: string): Promise<Patient> {
  return apiClient.get<Patient>(`/api/v1/patients/${id}`);
}

export async function createPatient(body: CreatePatientBody): Promise<Patient> {
  return apiClient.post<Patient>("/api/v1/patients", body, {
    idempotencyKey: generateId(),
  });
}

export async function updatePatient(id: string, body: UpdatePatientBody): Promise<Patient> {
  return apiClient.patch<Patient>(`/api/v1/patients/${id}`, body, {
    idempotencyKey: generateId(),
  });
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const patientKeys = {
  all: ["patients"] as const,
  list: (params: ListPatientsParams) => ["patients", "list", params] as const,
  detail: (id: string) => ["patients", "detail", id] as const,
};

// ── Query hooks ───────────────────────────────────────────────────────────────

export function usePatients(params: ListPatientsParams = {}): UseQueryResult<PatientListResponse> {
  return useQuery({
    queryKey: patientKeys.list(params),
    queryFn: () => listPatients(params),
  });
}

export function usePatient(id: string): UseQueryResult<Patient> {
  return useQuery({
    queryKey: patientKeys.detail(id),
    queryFn: () => getPatient(id),
    enabled: Boolean(id),
  });
}

export function useCreatePatient(): UseMutationResult<Patient, Error, CreatePatientBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createPatient,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: patientKeys.all });
    },
  });
}

export function useUpdatePatient(
  id: string,
): UseMutationResult<Patient, Error, UpdatePatientBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdatePatientBody) => updatePatient(id, body),
    onSuccess: (updated) => {
      queryClient.setQueryData(patientKeys.detail(id), updated);
      void queryClient.invalidateQueries({ queryKey: patientKeys.all });
    },
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────

export function isNotFoundError(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404;
}
