import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, generateId } from "@/lib/api-client";

// ── Types ──────────────────────────────────────────────────────────────────────

export type LedgerEntryType =
  | "charge"
  | "insurance_payment"
  | "patient_payment"
  | "adjustment";

export type LedgerPaymentMethod =
  | "cash"
  | "check"
  | "card"
  | "external_terminal"
  | "other";

export interface LedgerEntry {
  id: string;
  practiceId: string;
  patientId: string;
  entryType: LedgerEntryType;
  amountCents: number;
  runningBalanceCents: number;
  appointmentId: string | null;
  appointmentProcedureId: string | null;
  claimId: string | null;
  remittanceId: string | null;
  reversesEntryId: string | null;
  paymentMethod: LedgerPaymentMethod | null;
  memo: string | null;
  postedBy: string | null;
  postedAt: string;
}

export interface PatientLedger {
  patientId: string;
  balanceCents: number;
  entries: LedgerEntry[];
}

export interface RecordPaymentBody {
  amountCents: number;
  paymentMethod: LedgerPaymentMethod;
  memo?: string;
}

export interface AddAdjustmentBody {
  amountCents: number;
  memo: string;
}

// ── Pure helpers (exported for tests) ─────────────────────────────────────────

/** Format integer cents as a display dollar string ("$45.00"). */
export function centsToUsd(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

/**
 * Parse a dollar string to integer cents. Returns null for blank/invalid/zero.
 * When `allowNegative` is false, also rejects negatives (payments must be > 0);
 * when true, negatives are kept (credit adjustments).
 */
export function dollarsToCents(value: string, allowNegative: boolean): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const n = Number(trimmed);
  if (Number.isNaN(n)) return null;
  if (n === 0) return null;
  if (!allowNegative && n < 0) return null;
  return Math.round(n * 100);
}

// ── Query keys ─────────────────────────────────────────────────────────────────

export const ledgerKeys = {
  all: ["ledger"] as const,
  patient: (patientId: string) => ["ledger", patientId] as const,
};

// ── Hooks ──────────────────────────────────────────────────────────────────────

export function usePatientLedger(patientId: string) {
  return useQuery({
    queryKey: ledgerKeys.patient(patientId),
    queryFn: () => apiClient.get<PatientLedger>(`/api/v1/patients/${patientId}/ledger`),
  });
}

export function useRecordPayment(patientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RecordPaymentBody) =>
      apiClient.post<LedgerEntry>(`/api/v1/patients/${patientId}/payments`, body, {
        idempotencyKey: generateId(),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ledgerKeys.patient(patientId) });
    },
  });
}

export function useAddAdjustment(patientId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AddAdjustmentBody) =>
      apiClient.post<LedgerEntry>(`/api/v1/patients/${patientId}/adjustments`, body, {
        idempotencyKey: generateId(),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ledgerKeys.patient(patientId) });
    },
  });
}
