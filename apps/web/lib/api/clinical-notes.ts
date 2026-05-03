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

export type TemplateType =
  | "exam"
  | "prophy"
  | "extraction"
  | "crown_prep"
  | "crown_seat"
  | "root_canal"
  | "filling"
  | "srp"
  | "other";

export type PatientTolerance = "excellent" | "good" | "fair" | "poor";

export interface ClinicalNote {
  id: string;
  practiceId: string;
  patientId: string;
  appointmentId: string | null;
  providerId: string;
  visitDate: string;
  chiefComplaint: string | null;
  anesthesia: string | null;
  patientTolerance: PatientTolerance | null;
  complications: string | null;
  treatmentRendered: string;
  nextVisitPlan: string | null;
  notes: string | null;
  templateType: TemplateType | null;
  isSigned: boolean;
  signedAt: string | null;
  signedByProviderId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ClinicalNoteSummary {
  id: string;
  patientId: string;
  providerId: string;
  appointmentId: string | null;
  visitDate: string;
  treatmentRendered: string;
  templateType: TemplateType | null;
  isSigned: boolean;
  signedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ClinicalNoteListResponse {
  items: ClinicalNoteSummary[];
  nextCursor: string | null;
  hasMore: boolean;
}

export interface CreateClinicalNoteBody {
  appointmentId?: string;
  providerId: string;
  visitDate: string;
  chiefComplaint?: string;
  anesthesia?: string;
  patientTolerance?: PatientTolerance;
  complications?: string;
  treatmentRendered: string;
  nextVisitPlan?: string;
  notes?: string;
  templateType?: TemplateType;
}

export interface UpdateClinicalNoteBody {
  chiefComplaint?: string;
  anesthesia?: string;
  patientTolerance?: PatientTolerance;
  complications?: string;
  treatmentRendered?: string;
  nextVisitPlan?: string;
  notes?: string;
  templateType?: TemplateType;
}

// ── API functions ─────────────────────────────────────────────────────────────

export async function listClinicalNotes(
  patientId: string,
  limit: number = 20,
  cursor?: string,
  appointmentId?: string,
): Promise<ClinicalNoteListResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (cursor) params.set("cursor", cursor);
  if (appointmentId) params.set("appointment_id", appointmentId);
  const qs = params.toString();
  return apiClient.get<ClinicalNoteListResponse>(
    `/api/v1/patients/${patientId}/clinical-notes${qs ? `?${qs}` : ""}`,
  );
}

export async function getClinicalNote(
  patientId: string,
  noteId: string,
): Promise<ClinicalNote> {
  return apiClient.get<ClinicalNote>(
    `/api/v1/patients/${patientId}/clinical-notes/${noteId}`,
  );
}

export async function createClinicalNote(
  patientId: string,
  body: CreateClinicalNoteBody,
): Promise<ClinicalNote> {
  return apiClient.post<ClinicalNote>(
    `/api/v1/patients/${patientId}/clinical-notes`,
    body,
    { idempotencyKey: generateId() },
  );
}

export async function updateClinicalNote(
  patientId: string,
  noteId: string,
  body: UpdateClinicalNoteBody,
): Promise<ClinicalNote> {
  return apiClient.patch<ClinicalNote>(
    `/api/v1/patients/${patientId}/clinical-notes/${noteId}`,
    body,
    { idempotencyKey: generateId() },
  );
}

export async function signClinicalNote(
  patientId: string,
  noteId: string,
): Promise<ClinicalNote> {
  return apiClient.post<ClinicalNote>(
    `/api/v1/patients/${patientId}/clinical-notes/${noteId}/sign`,
    {},
    { idempotencyKey: generateId() },
  );
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const clinicalNoteKeys = {
  list: (patientId: string) => ["clinicalNotes", patientId, "list"] as const,
  detail: (patientId: string, noteId: string) =>
    ["clinicalNotes", patientId, "detail", noteId] as const,
};

// ── Hooks ─────────────────────────────────────────────────────────────────────

export function useClinicalNotes(patientId: string, limit: number = 20) {
  return useInfiniteQuery({
    queryKey: clinicalNoteKeys.list(patientId),
    queryFn: ({ pageParam }: { pageParam: string | undefined }) =>
      listClinicalNotes(patientId, limit, pageParam),
    getNextPageParam: (lastPage: ClinicalNoteListResponse) =>
      lastPage.hasMore ? (lastPage.nextCursor ?? undefined) : undefined,
    initialPageParam: undefined as string | undefined,
    enabled: Boolean(patientId),
  });
}

export function useClinicalNote(
  patientId: string,
  noteId: string,
): UseQueryResult<ClinicalNote> {
  return useQuery({
    queryKey: clinicalNoteKeys.detail(patientId, noteId),
    queryFn: () => getClinicalNote(patientId, noteId),
    enabled: Boolean(patientId) && Boolean(noteId),
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 404) return false;
      return failureCount < 3;
    },
  });
}

export function useCreateClinicalNote(
  patientId: string,
): UseMutationResult<ClinicalNote, Error, CreateClinicalNoteBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateClinicalNoteBody) => createClinicalNote(patientId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: clinicalNoteKeys.list(patientId) });
    },
  });
}

export function useUpdateClinicalNote(
  patientId: string,
  noteId: string,
): UseMutationResult<ClinicalNote, Error, UpdateClinicalNoteBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateClinicalNoteBody) =>
      updateClinicalNote(patientId, noteId, body),
    onSuccess: (updated) => {
      queryClient.setQueryData(clinicalNoteKeys.detail(patientId, noteId), updated);
      void queryClient.invalidateQueries({ queryKey: clinicalNoteKeys.list(patientId) });
    },
  });
}

export function useSignClinicalNote(
  patientId: string,
  noteId: string,
): UseMutationResult<ClinicalNote, Error, void> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => signClinicalNote(patientId, noteId),
    onSuccess: (updated) => {
      queryClient.setQueryData(clinicalNoteKeys.detail(patientId, noteId), updated);
      void queryClient.invalidateQueries({ queryKey: clinicalNoteKeys.list(patientId) });
    },
  });
}
