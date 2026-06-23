import { z } from "zod";
import { UuidSchema } from "./common.js";

export const ERARemittanceSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  stediTransactionId: z.string(),
  payerName: z.string().nullable(),
  traceNumber: z.string().nullable(),
  paymentCents: z.number().int().nullable(),
  paymentDate: z.string().nullable(),
  claimCount: z.number().int().nullable(),
  matchedCount: z.number().int().nullable(),
  unmatchedCount: z.number().int().nullable(),
  createdAt: z.string().datetime(),
});
export type ERARemittance = z.infer<typeof ERARemittanceSchema>;

export const UnmatchedERAPaymentSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  remittanceId: UuidSchema,
  patientControlNumber: z.string().nullable(),
  payerClaimControlNumber: z.string().nullable(),
  paidCents: z.number().int().nullable(),
  resolved: z.boolean(),
  resolvedAt: z.string().datetime().nullable(),
  createdAt: z.string().datetime(),
});
export type UnmatchedERAPayment = z.infer<typeof UnmatchedERAPaymentSchema>;

export const ERAPollSummarySchema = z.object({
  polled: z.number().int(),
  new: z.number().int(),
  matched: z.number().int(),
  unmatched: z.number().int(),
  remittanceIds: z.array(z.string()),
});
export type ERAPollSummary = z.infer<typeof ERAPollSummarySchema>;
