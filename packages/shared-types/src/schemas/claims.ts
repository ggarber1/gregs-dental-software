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
  submittedAt: z.string().datetime().nullable(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});
export type Claim = z.infer<typeof ClaimSchema>;
