import { z } from "zod";
import { UuidSchema } from "./common.js";

export const EligibilityCheckStatusSchema = z.enum([
  "pending",
  "verified",
  "failed",
  "not_supported",
]);

export const EligibilityCheckTriggerSchema = z.enum([
  "manual",
  "pre_appointment_batch",
]);

export const EligibilityCheckSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  patientId: UuidSchema,
  patientInsuranceId: UuidSchema,
  appointmentId: UuidSchema.optional(),

  idempotencyKey: z.string(),
  status: EligibilityCheckStatusSchema,
  trigger: EligibilityCheckTriggerSchema,
  clearinghouse: z.string(),
  payerIdUsed: z.string(),
  payerName: z.string().optional(),
  failureReason: z.string().optional(),

  // Coverage
  coverageStatus: z.enum(["active", "inactive", "unknown"]).optional(),
  coverageStartDate: z.string().date().optional(),
  coverageEndDate: z.string().date().optional(),

  // Deductibles (null = not returned by payer)
  deductibleIndividual: z.number().optional(),
  deductibleIndividualMet: z.number().optional(),
  deductibleFamily: z.number().optional(),
  deductibleFamilyMet: z.number().optional(),

  // Out-of-pocket max
  oopMaxIndividual: z.number().optional(),
  oopMaxIndividualMet: z.number().optional(),

  // Annual maximum
  annualMaxIndividual: z.number().optional(),
  annualMaxIndividualUsed: z.number().optional(),
  annualMaxIndividualRemaining: z.number().optional(),

  // Coinsurance — patient's share (0.20 = patient pays 20%)
  coinsurancePreventive: z.number().optional(),
  coinsuranceBasic: z.number().optional(),
  coinsuranceMajor: z.number().optional(),
  coinsuranceOrtho: z.number().optional(),

  // Waiting periods in months
  waitingPeriodBasicMonths: z.number().int().optional(),
  waitingPeriodMajorMonths: z.number().int().optional(),
  waitingPeriodOrthoMonths: z.number().int().optional(),

  // Frequency limits — flexible JSON object
  frequencyLimits: z.record(z.unknown()).optional(),

  requestedAt: z.string().datetime(),
  verifiedAt: z.string().datetime().optional(),
  failedAt: z.string().datetime().optional(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const CreateEligibilityCheckSchema = z.object({
  patientInsuranceId: UuidSchema,
  appointmentId: UuidSchema.optional(),
});

export type EligibilityCheckStatus = z.infer<typeof EligibilityCheckStatusSchema>;
export type EligibilityCheckTrigger = z.infer<typeof EligibilityCheckTriggerSchema>;
export type EligibilityCheck = z.infer<typeof EligibilityCheckSchema>;
export type CreateEligibilityCheck = z.infer<typeof CreateEligibilityCheckSchema>;
