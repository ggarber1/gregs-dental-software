import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { apiClient, apiErrorMessage, generateId } from "@/lib/api-client";
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

/** Midnight UTC of the given instant, in ms — so day differences count calendar days. */
const utcDay = (d: Date): number => Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());

/** "Never" | "Today" | "N days ago" | "N weeks ago" | "N months ago" */
export function lastStatementLabel(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "Never";
  const then = new Date(iso);
  const days = Math.round((utcDay(now) - utcDay(then)) / DAY_MS);
  if (days <= 0) return "Today";
  if (days < 14) return days === 1 ? "1 day ago" : `${days} days ago`;
  if (days < 35) return `${Math.floor(days / 7)} weeks ago`;
  const months = Math.floor(days / 30);
  return months === 1 ? "1 month ago" : `${months} months ago`;
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

/**
 * Open a Blob in a new tab (PDF preview). If the browser blocks the popup,
 * fall back to a file download so the user still gets the PDF.
 */
export function openBlob(blob: Blob, fallbackFilename: string): void {
  const url = URL.createObjectURL(blob);
  const w = window.open(url, "_blank");
  if (!w) {
    URL.revokeObjectURL(url);
    saveBlob(blob, fallbackFilename);
    return;
  }
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
    // Keep the table in place while a sort/threshold change refetches.
    placeholderData: keepPreviousData,
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

/** Re-download the PDF for a recorded statement (no new statement row is created). */
export async function downloadStatementPdf(
  patientId: string,
  statement: PatientStatement,
): Promise<void> {
  const blob = await apiClient.getBlob(
    `/api/v1/patients/${patientId}/statements/${statement.id}/pdf`,
  );
  saveBlob(blob, statementFilename(statement.generatedAt));
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
        try {
          const blob = await apiClient.getBlob(
            `/api/v1/patients/${patientId}/statements/${statement.id}/pdf`,
          );
          saveBlob(blob, statementFilename(statement.generatedAt));
        } catch {
          throw new Error(
            "Statement recorded but the PDF could not be downloaded. Use the statement history to retry.",
          );
        }
      }
      return statement;
    },
    onSuccess: (statement) => {
      toast.success(
        statement.deliveryMethod === "email" ? "Statement emailed." : "Statement downloaded.",
      );
    },
    onError: (err) => {
      toast.error(apiErrorMessage(err));
    },
    // The POST may have recorded a row even when the follow-up download failed,
    // so refresh history and the worklist on every outcome.
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: statementKeys.patient(patientId) });
      void qc.invalidateQueries({ queryKey: AGING_PREFIX });
    },
  });
}
