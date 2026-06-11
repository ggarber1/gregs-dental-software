import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";
import type { CdtCategory } from "@/lib/api/procedures";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface FeeScheduleRow {
  cdtCodeId: string;
  code: string;
  description: string;
  category: CdtCategory;
  defaultFeeCents: number | null;
  practiceFeeCents: number | null;
  resolvedFeeCents: number | null;
}

// ── Pure helpers (exported for tests) ───────────────────────────────────────────

/** Parse a dollar string to integer cents. Returns null for blank/invalid input. */
export function dollarsToCents(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const n = Number(trimmed);
  if (Number.isNaN(n) || n < 0) return null;
  return Math.round(n * 100);
}

/** Format integer cents as a plain dollar string for an editable field ("45.00"). */
export function centsToDollars(cents: number | null): string {
  return cents == null ? "" : (cents / 100).toFixed(2);
}

// ── API functions ───────────────────────────────────────────────────────────────

export async function getFeeSchedule(): Promise<FeeScheduleRow[]> {
  return apiClient.get<FeeScheduleRow[]>("/api/v1/fee-schedule");
}

export async function setFee(code: string, feeCents: number): Promise<FeeScheduleRow> {
  return apiClient.put<FeeScheduleRow>(
    `/api/v1/fee-schedule/${encodeURIComponent(code)}`,
    { feeCents },
    { idempotencyKey: generateId() },
  );
}

export async function revertFee(code: string): Promise<void> {
  return apiClient.delete<void>(`/api/v1/fee-schedule/${encodeURIComponent(code)}`, {
    idempotencyKey: generateId(),
  });
}

// ── Query keys ──────────────────────────────────────────────────────────────────

export const feeScheduleKeys = {
  list: () => ["feeSchedule"] as const,
};

// ── Hooks ────────────────────────────────────────────────────────────────────────

export function useFeeSchedule(): UseQueryResult<FeeScheduleRow[]> {
  return useQuery({ queryKey: feeScheduleKeys.list(), queryFn: getFeeSchedule });
}

export function useSetFee(): UseMutationResult<
  FeeScheduleRow,
  Error,
  { code: string; feeCents: number }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ code, feeCents }) => setFee(code, feeCents),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: feeScheduleKeys.list() });
    },
  });
}

export function useRevertFee(): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (code: string) => revertFee(code),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: feeScheduleKeys.list() });
    },
  });
}
