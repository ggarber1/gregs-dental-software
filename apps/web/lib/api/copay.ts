import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";

import { apiClient, generateId, ApiError } from "@/lib/api-client";
import type { CdtCategory } from "@/lib/api/procedures";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface CopayLineItem {
  procedureId: string;
  cdtCode: string;
  category: CdtCategory;
  providerFeeCents: number;
  allowedAmountCents: number;
  writeOffCents: number;
  deductibleAppliedCents: number;
  insuranceOwesCents: number;
  patientOwesCents: number;
  needsManualEntry: boolean;
  notCovered: boolean;
  isFrequencyExceeded: boolean;
  isInWaitingPeriod: boolean;
  annualMaxCapApplied: boolean;
}

export type PlanType = "ppo" | "premier" | "medicaid" | "indemnity" | "dhmo";

export interface CopayEstimate {
  id: string;
  appointmentId: string;
  eligibilityCheckId: string | null;
  calculatedAt: string;
  planType: PlanType;
  totalProviderFeeCents: number;
  totalWriteOffCents: number;
  totalInsuranceOwesCents: number;
  totalPatientOwesCents: number;
  deductibleRemainingAfterCents: number | null;
  annualMaxRemainingAfterCents: number | null;
  overridePatientCents: number | null;
  overrideNote: string | null;
  hasSecondaryInsurance: boolean;
  lineItems: CopayLineItem[];
}

export interface OverrideCopayBody {
  overridePatientCents: number | null;
  overrideNote?: string;
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

/** Format integer cents as a display dollar string ("$45.00" or "—"). */
export function centsToUsd(cents: number | null | undefined): string {
  if (cents == null) return "—";
  return `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// ── API functions ──────────────────────────────────────────────────────────────

export async function getCopayEstimate(appointmentId: string): Promise<CopayEstimate | null> {
  try {
    return await apiClient.get<CopayEstimate>(
      `/api/v1/appointments/${encodeURIComponent(appointmentId)}/copay-estimate`,
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export async function calculateCopayEstimate(appointmentId: string): Promise<CopayEstimate> {
  return apiClient.post<CopayEstimate>(
    `/api/v1/appointments/${encodeURIComponent(appointmentId)}/copay-estimate`,
    {},
    { idempotencyKey: generateId() },
  );
}

export async function overrideCopayEstimate(
  appointmentId: string,
  body: OverrideCopayBody,
): Promise<CopayEstimate> {
  return apiClient.patch<CopayEstimate>(
    `/api/v1/appointments/${encodeURIComponent(appointmentId)}/copay-estimate`,
    body,
    { idempotencyKey: generateId() },
  );
}

// ── Query keys ─────────────────────────────────────────────────────────────────

export const copayKeys = {
  detail: (appointmentId: string) => ["copayEstimate", appointmentId] as const,
};

// ── Hooks ──────────────────────────────────────────────────────────────────────

export function useCopayEstimate(
  appointmentId: string,
): UseQueryResult<CopayEstimate | null> {
  return useQuery({
    queryKey: copayKeys.detail(appointmentId),
    queryFn: () => getCopayEstimate(appointmentId),
    enabled: Boolean(appointmentId),
  });
}

export function useCalculateCopay(
  appointmentId: string,
): UseMutationResult<CopayEstimate, ApiError, void> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => calculateCopayEstimate(appointmentId),
    onSuccess: (data) => {
      queryClient.setQueryData(copayKeys.detail(appointmentId), data);
    },
  });
}

export function useOverrideCopay(
  appointmentId: string,
): UseMutationResult<CopayEstimate, ApiError, OverrideCopayBody> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: OverrideCopayBody) => overrideCopayEstimate(appointmentId, body),
    onSuccess: (data) => {
      queryClient.setQueryData(copayKeys.detail(appointmentId), data);
    },
  });
}
