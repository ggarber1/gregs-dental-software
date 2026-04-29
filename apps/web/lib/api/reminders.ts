import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";

// ── Types ─────────────────────────────────────────────────────────────────────

export type ReminderStatus = "pending" | "enqueued" | "sent" | "failed" | "cancelled";
export type ReminderChannel = "sms" | "email";

export interface ReminderRecord {
  id: string;
  reminderType: ReminderChannel;
  hoursBefore: number;
  sendAt: string; // ISO datetime
  status: ReminderStatus;
  sentAt: string | null;
  failedAt: string | null;
  failureReason: string | null;
  responseReceived: string | null;
  respondedAt: string | null;
}

export interface ReminderSettings {
  reminderHours: number[];
}

// ── API functions ─────────────────────────────────────────────────────────────

export async function listAppointmentReminders(appointmentId: string): Promise<ReminderRecord[]> {
  return apiClient.get<ReminderRecord[]>(`/api/v1/appointments/${appointmentId}/reminders`);
}

export async function getReminderSettings(): Promise<ReminderSettings> {
  return apiClient.get<ReminderSettings>("/api/v1/settings/reminders");
}

export async function updateReminderSettings(body: ReminderSettings): Promise<ReminderSettings> {
  return apiClient.put<ReminderSettings>("/api/v1/settings/reminders", body, {
    idempotencyKey: generateId(),
  });
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const reminderKeys = {
  forAppointment: (id: string) => ["appointment-reminders", id] as const,
  settings: ["reminder-settings"] as const,
};

// ── Query hooks ───────────────────────────────────────────────────────────────

export function useAppointmentReminders(
  appointmentId: string | null | undefined,
): UseQueryResult<ReminderRecord[]> {
  return useQuery({
    queryKey: reminderKeys.forAppointment(appointmentId ?? ""),
    queryFn: () => listAppointmentReminders(appointmentId!),
    enabled: !!appointmentId,
    staleTime: 30 * 1000, // 30 seconds — reminders update as jobs run
  });
}

export function useReminderSettings(): UseQueryResult<ReminderSettings> {
  return useQuery({
    queryKey: reminderKeys.settings,
    queryFn: getReminderSettings,
    staleTime: 5 * 60 * 1000,
  });
}

export function useUpdateReminderSettings(): UseMutationResult<
  ReminderSettings,
  Error,
  ReminderSettings
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updateReminderSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(reminderKeys.settings, data);
    },
  });
}
