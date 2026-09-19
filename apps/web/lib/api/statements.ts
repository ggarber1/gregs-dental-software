import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { apiClient, ApiError, generateId } from "@/lib/api-client";
import type { ARBuckets } from "@/lib/api/reports";

// ── Types (hand-written, mirroring packages/shared-types/src/schemas/statements.ts) ──

export type StatementDeliveryMethod = "email" | "download";
export type AgingSortBy = "balance" | "oldest_charge" | "last_statement";

export interface PatientAgingRow {
  patientId: string;
  patientName: string;
  email: string | null;
  balanceCents: number;
  buckets: ARBuckets;
  creditsCents: number;
  oldestChargeAt: string | null;
  lastStatementAt: string | null;
  lastStatementMethod: StatementDeliveryMethod | null;
}

export interface PatientStatement {
  id: string;
  practiceId: string;
  patientId: string;
  deliveryMethod: StatementDeliveryMethod;
  balanceCents: number;
  buckets: ARBuckets;
  generatedAt: string;
  deliveredAt: string | null;
  generatedBy: string;
}

export const DEFAULT_MIN_BALANCE_CENTS = 500;

// ── Pure helpers ──────────────────────────────────────────────────────────────

export function statementFilename(generatedAtIso: string): string {
  return `statement-${generatedAtIso.slice(0, 10)}.pdf`;
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** "Never" | "Today" | "N days ago" | "N weeks ago" | "N months ago" */
export function lastStatementLabel(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "Never";
  const then = new Date(iso);
  const days = Math.floor((now.getTime() - then.getTime()) / DAY_MS);
  if (days <= 0 || now.toISOString().slice(0, 10) === then.toISOString().slice(0, 10)) {
    return "Today";
  }
  if (days < 14) return days === 1 ? "1 day ago" : `${days} days ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 9) return `${weeks} weeks ago`;
  const months = Math.floor(days / 30);
  return months === 1 ? "1 month ago" : `${months} months ago`;
}

function apiErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const body = err.body as { error?: { message?: string } } | null;
    return body?.error?.message ?? `Unexpected error (${err.status})`;
  }
  return "Something went wrong. Please try again.";
}

/** Hand a Blob to the browser as a file download. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Open a Blob in a new tab (PDF preview). */
export function openBlob(blob: Blob): void {
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

// ── Query keys ────────────────────────────────────────────────────────────────

export const statementKeys = {
  all: ["statements"] as const,
  patient: (patientId: string) => ["statements", patientId] as const,
  aging: (sortBy: AgingSortBy, minBalanceCents: number) =>
    ["reports", "patient-aging", { sortBy, minBalanceCents }] as const,
};

const AGING_PREFIX = ["reports", "patient-aging"] as const;

// ── Hooks ─────────────────────────────────────────────────────────────────────

export function usePatientAgingWorklist(params: {
  sortBy: AgingSortBy;
  minBalanceCents: number;
}) {
  const search = new URLSearchParams({
    sort_by: params.sortBy,
    min_balance_cents: String(params.minBalanceCents),
  });
  return useQuery({
    queryKey: statementKeys.aging(params.sortBy, params.minBalanceCents),
    queryFn: () =>
      apiClient.get<PatientAgingRow[]>(`/api/v1/reports/patient-aging?${search.toString()}`),
  });
}

export function usePatientStatements(patientId: string) {
  return useQuery({
    queryKey: statementKeys.patient(patientId),
    queryFn: () => apiClient.get<PatientStatement[]>(`/api/v1/patients/${patientId}/statements`),
    enabled: Boolean(patientId),
  });
}

export function fetchStatementPreview(patientId: string): Promise<Blob> {
  return apiClient.getBlob(`/api/v1/patients/${patientId}/statements/preview`);
}

/**
 * POST a statement. For `download`, follows up with a GET for the bytes and
 * triggers the browser save (the API never returns a PDF from a mutation).
 */
export function useSendStatement(patientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (deliveryMethod: StatementDeliveryMethod) => {
      const statement = await apiClient.post<PatientStatement>(
        `/api/v1/patients/${patientId}/statements`,
        { deliveryMethod },
        { idempotencyKey: generateId() },
      );
      if (deliveryMethod === "download") {
        const blob = await apiClient.getBlob(
          `/api/v1/patients/${patientId}/statements/${statement.id}/pdf`,
        );
        saveBlob(blob, statementFilename(statement.generatedAt));
      }
      return statement;
    },
    onSuccess: (statement) => {
      toast.success(
        statement.deliveryMethod === "email" ? "Statement emailed." : "Statement downloaded.",
      );
      void qc.invalidateQueries({ queryKey: statementKeys.patient(patientId) });
      void qc.invalidateQueries({ queryKey: AGING_PREFIX });
    },
    onError: (err) => {
      toast.error(apiErrorMessage(err));
    },
  });
}
