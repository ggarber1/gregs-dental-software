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

export interface ContractedFeeRow {
  cdtCodeId: string;
  code: string;
  description: string;
  category: CdtCategory;
  payerId: string;
  allowedAmountCents: number | null;
  notCovered: boolean;
  requiresPriorAuth: boolean;
}

export interface SetContractedFeeBody {
  allowedAmountCents: number | null;
  notCovered?: boolean;
  requiresPriorAuth?: boolean;
}

// ── Pure helpers (exported for tests) ─────────────────────────────────────────

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

// ── API functions ──────────────────────────────────────────────────────────────

export async function getContractedFees(payerId: string): Promise<ContractedFeeRow[]> {
  return apiClient.get<ContractedFeeRow[]>(
    `/api/v1/contracted-fees?payer_id=${encodeURIComponent(payerId)}`,
  );
}

export async function setContractedFee(
  cdtCodeId: string,
  payerId: string,
  body: SetContractedFeeBody,
): Promise<ContractedFeeRow> {
  return apiClient.put<ContractedFeeRow>(
    `/api/v1/contracted-fees/${encodeURIComponent(cdtCodeId)}?payer_id=${encodeURIComponent(payerId)}`,
    body,
    { idempotencyKey: generateId() },
  );
}

export async function revertContractedFee(cdtCodeId: string, payerId: string): Promise<void> {
  return apiClient.delete<void>(
    `/api/v1/contracted-fees/${encodeURIComponent(cdtCodeId)}?payer_id=${encodeURIComponent(payerId)}`,
    { idempotencyKey: generateId() },
  );
}

// ── Query keys ─────────────────────────────────────────────────────────────────

export const contractedFeeKeys = {
  list: (payerId: string) => ["contractedFees", payerId] as const,
};

// ── Hooks ──────────────────────────────────────────────────────────────────────

export function useContractedFees(payerId: string): UseQueryResult<ContractedFeeRow[]> {
  return useQuery({
    queryKey: contractedFeeKeys.list(payerId),
    queryFn: () => getContractedFees(payerId),
    enabled: !!payerId,
  });
}

export function useSetContractedFee(
  payerId: string,
): UseMutationResult<ContractedFeeRow, Error, { cdtCodeId: string; body: SetContractedFeeBody }> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ cdtCodeId, body }) => setContractedFee(cdtCodeId, payerId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: contractedFeeKeys.list(payerId) });
    },
  });
}

export function useRevertContractedFee(
  payerId: string,
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (cdtCodeId: string) => revertContractedFee(cdtCodeId, payerId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: contractedFeeKeys.list(payerId) });
    },
  });
}
