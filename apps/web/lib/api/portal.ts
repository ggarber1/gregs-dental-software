import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";
import { getPortalAccessToken } from "@/lib/auth/cookies";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type PortalAccountStatus = "none" | "invited" | "active" | "revoked";

export interface PortalAccountStatusResponse {
  patientId: string;
  status: PortalAccountStatus;
  email: string | null;
  invitedAt: string | null;
  enrolledAt: string | null;
  inviteExpiresAt: string | null;
}

export interface SendPortalInviteBody {
  patientId: string;
}

export interface SendPortalInviteResponse {
  portalAccountId: string;
  status: "invited" | "active";
  expiresAt: string | null;
  inviteUrl: string | null;
}

export function buildPortalInviteUrl(token: string): string {
  const base = process.env.NEXT_PUBLIC_PATIENT_PORTAL_URL ?? "http://localhost:3000/portal";
  return `${base.replace(/\/$/, "")}/accept/${token}`;
}

export interface PortalInviteTokenInfo {
  practiceName: string;
  patientFirstName: string;
  email: string;
}

export interface PortalProfile {
  patientId: string;
  practiceId: string;
  practiceName: string;
  firstName: string;
  lastName: string;
  email: string | null;
}

export const portalKeys = {
  all: ["portal"] as const,
  status: (patientId: string) => ["portal", "status", patientId] as const,
  profile: ["portal", "profile"] as const,
  invite: (token: string) => ["portal", "invite", token] as const,
};

async function portalRequest<T>(
  method: "GET" | "POST",
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  const token = getPortalAccessToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    ...(body !== undefined && { body: JSON.stringify(body) }),
  });

  if (!response.ok) {
    const errorBody: unknown = await response
      .json()
      .catch(() => ({ error: { code: "UNKNOWN", message: response.statusText } }));
    throw new Error(
      typeof errorBody === "object" &&
        errorBody !== null &&
        "error" in errorBody &&
        typeof (errorBody as { error?: { message?: string } }).error?.message === "string"
        ? (errorBody as { error: { message: string } }).error.message
        : response.statusText,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export async function getPortalStatus(patientId: string): Promise<PortalAccountStatusResponse> {
  return apiClient.get<PortalAccountStatusResponse>(`/api/v1/portal/status?patient_id=${patientId}`);
}

export async function sendPortalInvite(body: SendPortalInviteBody): Promise<SendPortalInviteResponse> {
  return apiClient.post<SendPortalInviteResponse>("/api/v1/portal/invite", body, {
    idempotencyKey: generateId(),
  });
}

export async function getPortalInvite(token: string): Promise<PortalInviteTokenInfo> {
  const response = await fetch(`${API_BASE_URL}/api/portal/invite/${token}`);
  if (!response.ok) {
    throw new Error("This portal invite is invalid or has expired.");
  }
  return response.json() as Promise<PortalInviteTokenInfo>;
}

export async function completePortalInvite(token: string): Promise<void> {
  await portalRequest<void>("POST", `/api/portal/invite/${token}/complete`);
}

export async function getPortalProfile(): Promise<PortalProfile> {
  return portalRequest<PortalProfile>("GET", "/api/v1/portal/me");
}

export function usePortalStatus(patientId: string): UseQueryResult<PortalAccountStatusResponse> {
  return useQuery({
    queryKey: portalKeys.status(patientId),
    queryFn: () => getPortalStatus(patientId),
    enabled: Boolean(patientId),
  });
}

export function useSendPortalInvite(): UseMutationResult<
  SendPortalInviteResponse,
  Error,
  SendPortalInviteBody
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: sendPortalInvite,
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: portalKeys.status(variables.patientId),
      });
    },
  });
}

export function usePortalInvite(token: string | null): UseQueryResult<PortalInviteTokenInfo> {
  return useQuery({
    queryKey: portalKeys.invite(token ?? ""),
    queryFn: () => getPortalInvite(token!),
    enabled: Boolean(token),
    retry: false,
  });
}

export function usePortalProfile(enabled = true): UseQueryResult<PortalProfile> {
  return useQuery({
    queryKey: portalKeys.profile,
    queryFn: getPortalProfile,
    enabled,
  });
}
