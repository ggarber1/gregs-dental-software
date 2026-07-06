import { z } from "zod";
import { UuidSchema } from "./common.js";

export const ClaimStatusSchema = z.enum([
  "draft",
  "submitted",
  "clearinghouse_rejected",
  "submission_failed",
  "acknowledged",
  "pending",
  "paid",
  "partially_paid",
  "denied",
  "appealing",
]);
export type ClaimStatus = z.infer<typeof ClaimStatusSchema>;

export const ClaimSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  appointmentId: UuidSchema,
  patientId: UuidSchema,
  insuranceId: UuidSchema,
  providerId: UuidSchema,
  idempotencyKey: z.string(),
  submissionAttempt: z.number().int(),
  patientControlNumber: z.string(),
  payerId: z.string(),
  status: ClaimStatusSchema,
  totalChargeCents: z.number().int(),
  clearinghouseClaimId: z.string().nullable(),
  clearinghouseStatus: z.string().nullable(),
  submissionErrors: z.array(z.string()).nullable(),
  insurancePaidCents: z.number().int().nullable(),
  patientResponsibilityCents: z.number().int().nullable(),
  payerClaimControlNumber: z.string().nullable(),
  adjustments: z
    .array(z.object({ group: z.string(), code: z.string(), cents: z.number().int() }))
    .nullable(),
  denialCodes: z.array(z.string()).nullable(),
  paidAt: z.string().datetime().nullable(),
  remittanceId: UuidSchema.nullable(),
  submittedAt: z.string().datetime().nullable(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
  submissionHistory: z
    .array(
      z.object({
        attempt: z.number().int(),
        status: z.string(),
        denialCodes: z.array(z.string()).nullable(),
        payerCcn: z.string().nullable(),
        submittedAt: z.string().nullable(),
      })
    )
    .nullable(),
  claimFrequencyCode: z.string(),
  insuranceReviewedAt: z.string().datetime().nullable(),
});
export type Claim = z.infer<typeof ClaimSchema>;
