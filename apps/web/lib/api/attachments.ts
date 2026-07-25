import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, apiClient, generateId } from "@/lib/api-client";
import { getAccessToken, getPracticeId } from "@/lib/auth/cookies";

// ── Types ──────────────────────────────────────────────────────────────────────

export type AttachmentType = "xray" | "photo" | "perio_narrative" | "lab_rx" | "other";

export const ATTACHMENT_TYPE_LABELS: Record<AttachmentType, string> = {
  xray: "X-ray",
  photo: "Photo",
  perio_narrative: "Perio chart",
  lab_rx: "Lab Rx",
  other: "Other",
};

export interface AppointmentAttachment {
  id: string;
  practiceId: string;
  appointmentId: string;
  s3Key: string;
  fileName: string;
  fileSizeBytes: number;
  contentType: string;
  attachmentType: AttachmentType;
  uploadedBy: string;
  createdAt: string;
}

// ── Query keys ─────────────────────────────────────────────────────────────────

export const attachmentsKeys = {
  forAppointment: (appointmentId: string) =>
    ["attachments", "appointment", appointmentId] as const,
};

// ── Hooks ──────────────────────────────────────────────────────────────────────

export function useAppointmentAttachments(appointmentId: string) {
  return useQuery({
    queryKey: attachmentsKeys.forAppointment(appointmentId),
    queryFn: () =>
      apiClient.get<AppointmentAttachment[]>(
        `/api/v1/appointments/${appointmentId}/attachments`,
      ),
  });
}

export function useUploadAttachment(appointmentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      file,
      attachmentType,
    }: {
      file: File;
      attachmentType: AttachmentType;
    }) => {
      // Must use fetch directly — apiClient hardcodes Content-Type: application/json
      // which breaks multipart/form-data. Browser sets the correct boundary automatically
      // when Content-Type is omitted from the headers object.
      const formData = new FormData();
      formData.append("file", file);
      formData.append("attachment_type", attachmentType);

      const headers: Record<string, string> = {};

      const token = getAccessToken();
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const practiceId = getPracticeId();
      if (practiceId) {
        headers["X-Practice-ID"] = practiceId;
      }

      headers["Idempotency-Key"] = generateId();

      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const response = await fetch(
        `${apiBase}/api/v1/appointments/${appointmentId}/attachments`,
        { method: "POST", headers, body: formData },
      );
      if (!response.ok) {
        if (response.status === 401 && typeof window !== "undefined") {
          window.location.href = "/login";
          return undefined as unknown as AppointmentAttachment;
        }
        // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
        const errorBody: unknown = await response
          .json()
          .catch(() => ({ error: { code: "UNKNOWN", message: response.statusText } }));
        throw new ApiError(response.status, errorBody);
      }
      return response.json() as Promise<AppointmentAttachment>;
    },
    onSuccess: () => {
      void qc.invalidateQueries({
        queryKey: attachmentsKeys.forAppointment(appointmentId),
      });
    },
  });
}

export function useDeleteAttachment(appointmentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (attachmentId: string) =>
      apiClient.delete<void>(
        `/api/v1/appointments/${appointmentId}/attachments/${attachmentId}`,
        { idempotencyKey: generateId() },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({
        queryKey: attachmentsKeys.forAppointment(appointmentId),
      });
    },
  });
}
