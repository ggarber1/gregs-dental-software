import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";
import type { Patient } from "@/lib/api/patients";
import { insuranceKeys } from "@/lib/api/insurance";
import { medicalHistoryKeys } from "@/lib/api/medical-history";

// ── Types ─────────────────────────────────────────────────────────────────────

export type IntakeStatus = "pending" | "completed" | "expired";

export interface IntakeFormSummary {
  id: string;
  patientId: string;
  status: IntakeStatus;
  expiresAt: string;
  createdAt: string;
  createdBy: string;
}

export interface IntakeFormDetail extends IntakeFormSummary {
  responses: Record<string, unknown> | null;
}

export interface SendIntakeFormBody {
  patientId: string;
}

export interface SendIntakeFormResponse {
  intakeFormId: string;
  expiresAt: string;
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const intakeKeys = {
  all: ["intake"] as const,
  forPatient: (patientId: string) => ["intake", "patient", patientId] as const,
  detail: (id: string) => ["intake", "detail", id] as const,
};

// ── API functions ─────────────────────────────────────────────────────────────

export async function sendIntakeForm(body: SendIntakeFormBody): Promise<SendIntakeFormResponse> {
  return apiClient.post<SendIntakeFormResponse>("/api/v1/intake/send", body, {
    idempotencyKey: generateId(),
  });
}

export async function listPatientIntakeForms(patientId: string): Promise<IntakeFormSummary[]> {
  return apiClient.get<IntakeFormSummary[]>(`/api/v1/intake?patient_id=${patientId}`);
}

export async function getIntakeFormDetail(id: string): Promise<IntakeFormDetail> {
  return apiClient.get<IntakeFormDetail>(`/api/v1/intake/${id}`);
}

export async function applyIntakeForm(id: string): Promise<Patient> {
  return apiClient.post<Patient>(`/api/v1/intake/${id}/apply`, {}, {
    idempotencyKey: generateId(),
  });
}

// ── Query hooks ───────────────────────────────────────────────────────────────

export function usePatientIntakeForms(patientId: string): UseQueryResult<IntakeFormSummary[]> {
  return useQuery({
    queryKey: intakeKeys.forPatient(patientId),
    queryFn: () => listPatientIntakeForms(patientId),
    enabled: Boolean(patientId),
  });
}

export function useIntakeFormDetail(id: string | null): UseQueryResult<IntakeFormDetail> {
  return useQuery({
    queryKey: intakeKeys.detail(id ?? ""),
    queryFn: () => getIntakeFormDetail(id!),
    enabled: Boolean(id),
  });
}

export function useSendIntakeForm(): UseMutationResult<
  SendIntakeFormResponse,
  Error,
  SendIntakeFormBody
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: sendIntakeForm,
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: intakeKeys.forPatient(variables.patientId),
      });
    },
  });
}

export function useApplyIntakeForm(
  patientId: string,
): UseMutationResult<Patient, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (intakeFormId: string) => applyIntakeForm(intakeFormId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["patients", "detail", patientId] });
      void queryClient.invalidateQueries({ queryKey: intakeKeys.forPatient(patientId) });
      void queryClient.invalidateQueries({ queryKey: insuranceKeys.all(patientId) });
      void queryClient.invalidateQueries({ queryKey: medicalHistoryKeys.latest(patientId) });
    },
  });
}
