import { z } from "zod";
import { UuidSchema } from "./common.js";

export const LedgerEntryTypeSchema = z.enum([
  "charge",
  "insurance_payment",
  "patient_payment",
  "adjustment",
]);
export type LedgerEntryType = z.infer<typeof LedgerEntryTypeSchema>;

export const LedgerPaymentMethodSchema = z.enum([
  "cash",
  "check",
  "card",
  "external_terminal",
  "other",
]);
export type LedgerPaymentMethod = z.infer<typeof LedgerPaymentMethodSchema>;

export const LedgerEntrySchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  patientId: UuidSchema,
  entryType: LedgerEntryTypeSchema,
  amountCents: z.number().int(),
  runningBalanceCents: z.number().int(),
  appointmentId: UuidSchema.nullable(),
  appointmentProcedureId: UuidSchema.nullable(),
  claimId: UuidSchema.nullable(),
  remittanceId: UuidSchema.nullable(),
  reversesEntryId: UuidSchema.nullable(),
  paymentMethod: LedgerPaymentMethodSchema.nullable(),
  memo: z.string().nullable(),
  postedBy: z.string(),
  postedAt: z.string().datetime(),
});
export type LedgerEntry = z.infer<typeof LedgerEntrySchema>;

export const PatientLedgerSchema = z.object({
  patientId: UuidSchema,
  balanceCents: z.number().int(),
  entries: z.array(LedgerEntrySchema),
});
export type PatientLedger = z.infer<typeof PatientLedgerSchema>;

export const RecordPaymentRequestSchema = z.object({
  amountCents: z.number().int().positive(),
  paymentMethod: LedgerPaymentMethodSchema,
  memo: z.string().nullable().optional(),
});
export type RecordPaymentRequest = z.infer<typeof RecordPaymentRequestSchema>;

export const AddAdjustmentRequestSchema = z.object({
  amountCents: z.number().int(),
  memo: z.string().min(1),
});
export type AddAdjustmentRequest = z.infer<typeof AddAdjustmentRequestSchema>;

export const ReverseEntryRequestSchema = z.object({
  memo: z.string().nullable().optional(),
});
export type ReverseEntryRequest = z.infer<typeof ReverseEntryRequestSchema>;
