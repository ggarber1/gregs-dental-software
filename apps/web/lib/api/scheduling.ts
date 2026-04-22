import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";

// ── Types ─────────────────────────────────────────────────────────────────────

export type AppointmentStatus =
  | "scheduled"
  | "confirmed"
  | "checked_in"
  | "in_chair"
  | "completed"
  | "cancelled"
  | "no_show";

export interface Appointment {
  id: string;
  practiceId: string;
  patientId: string | null;
  providerId: string | null;
  operatoryId: string | null;
  appointmentTypeId: string | null;
  startTime: string; // ISO datetime
  endTime: string; // ISO datetime
  status: AppointmentStatus;
  notes: string | null;
  cancellationReason: string | null;
  patientName: string | null;
  providerName: string | null;
  operatoryName: string | null;
  appointmentTypeName: string | null;
  appointmentTypeColor: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface CreateAppointmentBody {
  patientId: string;
  providerId: string;
  operatoryId: string;
  appointmentTypeId?: string;
  startTime: string;
  endTime: string;
  notes?: string;
}

export interface UpdateAppointmentBody {
  patientId?: string;
  providerId?: string;
  operatoryId?: string;
  appointmentTypeId?: string;
  startTime?: string;
  endTime?: string;
  status?: AppointmentStatus;
  notes?: string;
  cancellationReason?: string;
}

export interface CancelAppointmentBody {
  cancellationReason?: string;
}

export interface AppointmentType {
  id: string;
  practiceId: string;
  name: string;
  durationMinutes: number;
  color: string;
  defaultCdtCodes: string[];
  isActive: boolean;
  displayOrder: number;
  createdAt: string;
  updatedAt: string;
}

export interface Provider {
  id: string;
  practiceId: string;
  fullName: string;
  npi: string;
  providerType: "dentist" | "hygienist" | "specialist" | "other";
  licenseNumber: string | null;
  specialty: string | null;
  color: string;
  isActive: boolean;
  displayOrder: number;
  createdAt: string;
  updatedAt: string;
}

export interface Operatory {
  id: string;
  practiceId: string;
  name: string;
  color: string;
  isActive: boolean;
  displayOrder: number;
  createdAt: string;
  updatedAt: string;
}

export interface ListAppointmentsParams {
  providerId?: string;
  operatoryId?: string;
  status?: AppointmentStatus;
}

// ── Provider mutation types ─────────────────────────────────────────────────

export interface CreateProviderBody {
  fullName: string;
  npi: string;
  providerType: "dentist" | "hygienist" | "specialist" | "other";
  licenseNumber?: string;
  specialty?: string;
  color?: string;
  isActive?: boolean;
  displayOrder?: number;
}

export interface UpdateProviderBody {
  fullName?: string;
  npi?: string;
  providerType?: "dentist" | "hygienist" | "specialist" | "other";
  licenseNumber?: string;
  specialty?: string;
  color?: string;
  isActive?: boolean;
  displayOrder?: number;
}

// ── Operatory mutation types ────────────────────────────────────────────────

export interface CreateOperatoryBody {
  name: string;
  color?: string;
  isActive?: boolean;
  displayOrder?: number;
}

export interface UpdateOperatoryBody {
  name?: string;
  color?: string;
  isActive?: boolean;
  displayOrder?: number;
}

// ── Appointment Type mutation types ─────────────────────────────────────────

export interface CreateAppointmentTypeBody {
  name: string;
  durationMinutes: number;
  color?: string;
  defaultCdtCodes?: string[];
  isActive?: boolean;
  displayOrder?: number;
}

export interface UpdateAppointmentTypeBody {
  name?: string;
  durationMinutes?: number;
  color?: string;
  defaultCdtCodes?: string[];
  isActive?: boolean;
  displayOrder?: number;
}

// Returns the confirmation glyph for a given appointment status.
// ⚪ = not yet confirmed, ✅ = confirmed or past that stage.
export function confirmationGlyph(status: AppointmentStatus): string {
  switch (status) {
    case "confirmed":
    case "checked_in":
    case "in_chair":
    case "completed":
      return "✅";
    default:
      return "⚪";
  }
}

// ── API functions ─────────────────────────────────────────────────────────────

export async function listAppointments(
  params: ListAppointmentsParams = {},
): Promise<Appointment[]> {
  const qs = new URLSearchParams();
  if (params.providerId) qs.set("provider_id", params.providerId);
  if (params.operatoryId) qs.set("operatory_id", params.operatoryId);
  if (params.status) qs.set("status", params.status);
  const query = qs.toString();
  return apiClient.get<Appointment[]>(`/api/v1/appointments${query ? `?${query}` : ""}`);
}

export async function getAppointment(id: string): Promise<Appointment> {
  return apiClient.get<Appointment>(`/api/v1/appointments/${id}`);
}

export async function createAppointment(body: CreateAppointmentBody): Promise<Appointment> {
  return apiClient.post<Appointment>("/api/v1/appointments", body, {
    idempotencyKey: generateId(),
  });
}

export async function updateAppointment(
  id: string,
  body: UpdateAppointmentBody,
): Promise<Appointment> {
  return apiClient.patch<Appointment>(`/api/v1/appointments/${id}`, body, {
    idempotencyKey: generateId(),
  });
}

export async function cancelAppointment(
  id: string,
  body?: CancelAppointmentBody,
): Promise<Appointment> {
  const patchBody: UpdateAppointmentBody = { status: "cancelled" };
  if (body?.cancellationReason) patchBody.cancellationReason = body.cancellationReason;
  return apiClient.patch<Appointment>(`/api/v1/appointments/${id}`, patchBody, {
    idempotencyKey: generateId(),
  });
}

export async function listAppointmentTypes(): Promise<AppointmentType[]> {
  return apiClient.get<AppointmentType[]>("/api/v1/appointment-types");
}

export async function listProviders(): Promise<Provider[]> {
  return apiClient.get<Provider[]>("/api/v1/providers");
}

export async function listOperatories(): Promise<Operatory[]> {
  return apiClient.get<Operatory[]>("/api/v1/operatories");
}

// ── Provider CRUD ───────────────────────────────────────────────────────────

export async function createProvider(body: CreateProviderBody): Promise<Provider> {
  return apiClient.post<Provider>("/api/v1/providers", body, {
    idempotencyKey: generateId(),
  });
}

export async function updateProvider(id: string, body: UpdateProviderBody): Promise<Provider> {
  return apiClient.patch<Provider>(`/api/v1/providers/${id}`, body, {
    idempotencyKey: generateId(),
  });
}

export async function deleteProvider(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/providers/${id}`, { idempotencyKey: generateId() });
}

// ── Operatory CRUD ──────────────────────────────────────────────────────────

export async function createOperatory(body: CreateOperatoryBody): Promise<Operatory> {
  return apiClient.post<Operatory>("/api/v1/operatories", body, {
    idempotencyKey: generateId(),
  });
}

export async function updateOperatory(id: string, body: UpdateOperatoryBody): Promise<Operatory> {
  return apiClient.patch<Operatory>(`/api/v1/operatories/${id}`, body, {
    idempotencyKey: generateId(),
  });
}

export async function deleteOperatory(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/operatories/${id}`, { idempotencyKey: generateId() });
}

// ── Appointment Type CRUD ───────────────────────────────────────────────────

export async function createAppointmentType(
  body: CreateAppointmentTypeBody,
): Promise<AppointmentType> {
  return apiClient.post<AppointmentType>("/api/v1/appointment-types", body, {
    idempotencyKey: generateId(),
  });
}

export async function updateAppointmentType(
  id: string,
  body: UpdateAppointmentTypeBody,
): Promise<AppointmentType> {
  return apiClient.patch<AppointmentType>(`/api/v1/appointment-types/${id}`, body, {
    idempotencyKey: generateId(),
  });
}

export async function deleteAppointmentType(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/appointment-types/${id}`, { idempotencyKey: generateId() });
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const appointmentKeys = {
  all: ["appointments"] as const,
  list: (params: ListAppointmentsParams) => ["appointments", "list", params] as const,
  detail: (id: string) => ["appointments", "detail", id] as const,
};

export const appointmentTypeKeys = {
  all: ["appointment-types"] as const,
  list: () => ["appointment-types", "list"] as const,
};

export const providerKeys = {
  all: ["providers"] as const,
  list: () => ["providers", "list"] as const,
};

export const operatoryKeys = {
  all: ["operatories"] as const,
  list: () => ["operatories", "list"] as const,
};

// ── Query hooks ───────────────────────────────────────────────────────────────

export function useAppointments(
  params: ListAppointmentsParams = {},
): UseQueryResult<Appointment[]> {
  return useQuery({
    queryKey: appointmentKeys.list(params),
    queryFn: () => listAppointments(params),
  });
}

export function useAppointment(id: string): UseQueryResult<Appointment> {
  return useQuery({
    queryKey: appointmentKeys.detail(id),
    queryFn: () => getAppointment(id),
    enabled: Boolean(id),
  });
}

export function useCreateAppointment(): UseMutationResult<
  Appointment,
  Error,
  CreateAppointmentBody
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createAppointment,
    onSuccess: (created) => {
      queryClient.setQueryData(appointmentKeys.detail(created.id), created);
      void queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
    },
  });
}

export function useUpdateAppointment(): UseMutationResult<
  Appointment,
  Error,
  { id: string; body: UpdateAppointmentBody }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => updateAppointment(id, body),
    onSuccess: (updated) => {
      queryClient.setQueryData(appointmentKeys.detail(updated.id), updated);
      void queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
    },
  });
}

export function useCancelAppointment(): UseMutationResult<
  Appointment,
  Error,
  { id: string; body?: CancelAppointmentBody }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => cancelAppointment(id, body),
    onSuccess: (updated) => {
      queryClient.setQueryData(appointmentKeys.detail(updated.id), updated);
      void queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
    },
  });
}

export function useAppointmentTypes(): UseQueryResult<AppointmentType[]> {
  return useQuery({
    queryKey: appointmentTypeKeys.list(),
    queryFn: listAppointmentTypes,
  });
}

export function useProviders(): UseQueryResult<Provider[]> {
  return useQuery({
    queryKey: providerKeys.list(),
    queryFn: listProviders,
  });
}

export function useOperatories(): UseQueryResult<Operatory[]> {
  return useQuery({
    queryKey: operatoryKeys.list(),
    queryFn: listOperatories,
  });
}

// ── Provider mutations ──────────────────────────────────────────────────────

export function useCreateProvider(): UseMutationResult<Provider, Error, CreateProviderBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createProvider,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: providerKeys.all });
    },
  });
}

export function useUpdateProvider(): UseMutationResult<
  Provider,
  Error,
  { id: string; body: UpdateProviderBody }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => updateProvider(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: providerKeys.all });
    },
  });
}

export function useDeleteProvider(): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteProvider,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: providerKeys.all });
    },
  });
}

// ── Operatory mutations ─────────────────────────────────────────────────────

export function useCreateOperatory(): UseMutationResult<Operatory, Error, CreateOperatoryBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createOperatory,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: operatoryKeys.all });
    },
  });
}

export function useUpdateOperatory(): UseMutationResult<
  Operatory,
  Error,
  { id: string; body: UpdateOperatoryBody }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => updateOperatory(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: operatoryKeys.all });
    },
  });
}

export function useDeleteOperatory(): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteOperatory,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: operatoryKeys.all });
    },
  });
}

// ── Appointment Type mutations ──────────────────────────────────────────────

export function useCreateAppointmentType(): UseMutationResult<
  AppointmentType,
  Error,
  CreateAppointmentTypeBody
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createAppointmentType,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: appointmentTypeKeys.all });
    },
  });
}

export function useUpdateAppointmentType(): UseMutationResult<
  AppointmentType,
  Error,
  { id: string; body: UpdateAppointmentTypeBody }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => updateAppointmentType(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: appointmentTypeKeys.all });
    },
  });
}

export function useDeleteAppointmentType(): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteAppointmentType,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: appointmentTypeKeys.all });
    },
  });
}
