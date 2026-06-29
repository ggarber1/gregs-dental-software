import { z } from "zod";
import { UuidSchema } from "./common.js";
import { ClaimStatusSchema } from "./claims.js";

export const ARCategorySchema = z.enum([
  "awaiting",
  "underpaid",
  "problem",
  "appealing",
]);
export type ARCategory = z.infer<typeof ARCategorySchema>;

export const AgeBucketSchema = z.enum(["0-30", "31-60", "61-90", "90+"]);
export type AgeBucket = z.infer<typeof AgeBucketSchema>;

export const InsuranceARRowSchema = z.object({
  claimId: UuidSchema,
  claimNumber: z.string(),
  patientName: z.string(),
  payerId: z.string(),
  carrierName: z.string(),
  category: ARCategorySchema,
  billedCents: z.number().int(),
  estimatedInsuranceCents: z.number().int().nullable(),
  insurancePaidCents: z.number().int().nullable(),
  shortfallCents: z.number().int().nullable(),
  hasEstimate: z.boolean(),
  daysOut: z.number().int(),
  bucket: AgeBucketSchema,
  status: ClaimStatusSchema,
  reason: z.string().nullable(),
});
export type InsuranceARRow = z.infer<typeof InsuranceARRowSchema>;

export const ARBucketsSchema = z.object({
  b0_30: z.number().int(),
  b31_60: z.number().int(),
  b61_90: z.number().int(),
  b90_plus: z.number().int(),
});

export const InsuranceARCarrierSummarySchema = z.object({
  payerId: z.string(),
  carrierName: z.string(),
  claimCount: z.number().int(),
  buckets: ARBucketsSchema,
  totalBilledCents: z.number().int(),
  expectedCents: z.number().int(),
  unestimatedCount: z.number().int(),
  underpaidCount: z.number().int(),
  problemCount: z.number().int(),
});

export const InsuranceARTotalsSchema = z.object({
  claimCount: z.number().int(),
  buckets: ARBucketsSchema,
  totalBilledCents: z.number().int(),
  expectedCents: z.number().int(),
  unestimatedCount: z.number().int(),
  underpaidCount: z.number().int(),
  problemCount: z.number().int(),
});

export const InsuranceARSummarySchema = z.object({
  carriers: z.array(InsuranceARCarrierSummarySchema),
  totals: InsuranceARTotalsSchema,
});
export type InsuranceARSummary = z.infer<typeof InsuranceARSummarySchema>;

export const ClaimActionResultSchema = z.object({
  claimId: UuidSchema,
  status: ClaimStatusSchema,
  insuranceReviewedAt: z.string().datetime().nullable(),
});
export type ClaimActionResult = z.infer<typeof ClaimActionResultSchema>;
