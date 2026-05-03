import {
  useQuery,
  useMutation,
  useQueryClient,
  useInfiniteQuery,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";

import { apiClient, generateId, ApiError } from "@/lib/api-client";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface AllergyEntry {
  name: string;
  severity?: string | undefined;
  reaction?: string | undefined;
}

export interface MedicationEntry {
  name: string;
  dose?: string | undefined;
  frequency?: string | undefined;
}

export interface ConditionEntry {
  name: string;
  icd10Hint?: string | undefined;
  notes?: string | undefined;
}

export interface MedicalFlags {
  flagBloodThinners: boolean;
  flagBisphosphonates: boolean;
  flagHeartCondition: boolean;
  flagDiabetes: boolean;
  flagPacemaker: boolean;
  flagLatexAllergy: boolean;
}

export interface MedicalHistoryVersion {
  id: string;
  practiceId: string;
  patientId: string;
  versionNumber: number;
  recordedBy: string;
  recordedAt: string;
  allergies: AllergyEntry[];
  medications: MedicationEntry[];
  conditions: ConditionEntry[];
  flags: MedicalFlags;
  additionalNotes?: string;
  createdAt: string;
  updatedAt: string;
}

export interface MedicalHistoryVersionSummary {
  id: string;
  versionNumber: number;
  recordedBy: string;
  recordedAt: string;
  allergyCount: number;
  medicationCount: number;
  conditionCount: number;
  flags: MedicalFlags;
}

export interface MedicalHistoryHistoryResponse {
  items: MedicalHistoryVersionSummary[];
  total: number;
  page: number;
  pageSize: number;
}

export interface CreateMedicalHistoryBody {
  allergies?: AllergyEntry[];
  medications?: MedicationEntry[];
  conditions?: ConditionEntry[];
  flags?: Partial<MedicalFlags>;
  additionalNotes?: string;
}

// ── API functions ─────────────────────────────────────────────────────────────

export async function getMedicalHistory(patientId: string): Promise<MedicalHistoryVersion> {
  return apiClient.get<MedicalHistoryVersion>(
    `/api/v1/patients/${patientId}/medical-history`,
  );
}

export async function getMedicalHistoryHistory(
  patientId: string,
  page: number = 1,
  pageSize: number = 20,
): Promise<MedicalHistoryHistoryResponse> {
  return apiClient.get<MedicalHistoryHistoryResponse>(
    `/api/v1/patients/${patientId}/medical-history/history?page=${page}&page_size=${pageSize}`,
  );
}

export async function getMedicalHistoryVersion(
  patientId: string,
  versionId: string,
): Promise<MedicalHistoryVersion> {
  return apiClient.get<MedicalHistoryVersion>(
    `/api/v1/patients/${patientId}/medical-history/${versionId}`,
  );
}

export async function createMedicalHistoryVersion(
  patientId: string,
  body: CreateMedicalHistoryBody,
): Promise<MedicalHistoryVersion> {
  return apiClient.post<MedicalHistoryVersion>(
    `/api/v1/patients/${patientId}/medical-history`,
    body,
    { idempotencyKey: generateId() },
  );
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const medicalHistoryKeys = {
  latest: (patientId: string) => ["medicalHistory", patientId, "latest"] as const,
  history: (patientId: string) => ["medicalHistory", patientId, "history"] as const,
  version: (patientId: string, versionId: string) =>
    ["medicalHistory", patientId, "version", versionId] as const,
};

// ── Hooks ─────────────────────────────────────────────────────────────────────

export function useMedicalHistory(
  patientId: string,
): UseQueryResult<MedicalHistoryVersion> {
  return useQuery({
    queryKey: medicalHistoryKeys.latest(patientId),
    queryFn: () => getMedicalHistory(patientId),
    enabled: Boolean(patientId),
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 404) return false;
      return failureCount < 3;
    },
  });
}

export function useMedicalHistoryHistory(patientId: string, pageSize: number = 20) {
  return useInfiniteQuery({
    queryKey: medicalHistoryKeys.history(patientId),
    queryFn: ({ pageParam = 1 }) =>
      getMedicalHistoryHistory(patientId, pageParam as number, pageSize),
    getNextPageParam: (lastPage) => {
      const totalPages = Math.ceil(lastPage.total / lastPage.pageSize);
      return lastPage.page < totalPages ? lastPage.page + 1 : undefined;
    },
    initialPageParam: 1,
    enabled: Boolean(patientId),
  });
}

export function useCreateMedicalHistoryVersion(
  patientId: string,
): UseMutationResult<MedicalHistoryVersion, Error, CreateMedicalHistoryBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateMedicalHistoryBody) =>
      createMedicalHistoryVersion(patientId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: medicalHistoryKeys.latest(patientId),
      });
      void queryClient.invalidateQueries({
        queryKey: medicalHistoryKeys.history(patientId),
      });
      // Also invalidate the patient query so MedicalAlertsBar sees the updated flat arrays
      void queryClient.invalidateQueries({ queryKey: ["patient", patientId] });
    },
  });
}
