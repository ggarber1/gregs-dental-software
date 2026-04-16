import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface PracticeInfo {
  id: string;
  name: string;
  timezone: string;
  phone: string | null;
  addressLine1: string | null;
  addressLine2: string | null;
  city: string | null;
  state: string | null;
  zip: string | null;
  features: Record<string, boolean>;
  createdAt: string;
  updatedAt: string;
}

// ── API functions ─────────────────────────────────────────────────────────────

export async function getPractice(): Promise<PracticeInfo> {
  return apiClient.get<PracticeInfo>("/api/v1/practice");
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const practiceKeys = {
  current: ["practice"] as const,
};

// ── Query hooks ───────────────────────────────────────────────────────────────

export function usePractice(): UseQueryResult<PracticeInfo> {
  return useQuery({
    queryKey: practiceKeys.current,
    queryFn: getPractice,
    staleTime: 5 * 60 * 1000, // 5 minutes — practice config rarely changes
  });
}

/**
 * Convenience hook that returns the practice IANA timezone string.
 *
 * Falls back to "America/New_York" (the DB default) while the API response
 * is loading, so components never receive undefined.
 */
export function usePracticeTimezone(): string {
  const { data } = usePractice();
  return data?.timezone ?? "America/New_York";
}
