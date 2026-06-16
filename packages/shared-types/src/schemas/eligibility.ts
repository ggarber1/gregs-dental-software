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
  planName: z.string().optional(),
  failureReason: z.string().optional(),

  // Coverage
  coverageStatus: z.enum(["active", "inactive", "unknown"]).optional(),
  coverageStartDate: z.string().date().optional(),
  coverageEndDate: z.string().date().optional(),

  // Deductibles (null = not returned by payer) — integer cents
  deductibleIndividual: z.number().int().optional(),
  deductibleIndividualMet: z.number().int().optional(),
  deductibleFamily: z.number().int().optional(),
  deductibleFamilyMet: z.number().int().optional(),

  // Out-of-pocket max — integer cents
  oopMaxIndividual: z.number().int().optional(),
  oopMaxIndividualMet: z.number().int().optional(),

  // Annual maximum — integer cents
  annualMaxIndividual: z.number().int().optional(),
  annualMaxIndividualUsed: z.number().int().optional(),
  annualMaxIndividualRemaining: z.number().int().optional(),

  // Plan classification
  planType: z.enum(["ppo", "premier", "medicaid", "indemnity", "dhmo"]).optional(),
  networkStatus: z.enum(["in_network", "out_of_network"]).optional(),

  // Coinsurance — patient's share (0.20 = patient pays 20%)
  coinsurancePreventive: z.number().optional(),
  coinsuranceBasic: z.number().optional(),
  coinsuranceMajor: z.number().optional(),
  coinsuranceOrtho: z.number().optional(),
  coinsuranceByCode: z.record(z.number()).nullable().optional(),

  // Ortho lifetime maximum — integer cents
  orthoLifetimeMax: z.number().int().nonnegative().nullable().optional(),
  orthoLifetimeMaxUsed: z.number().int().nonnegative().nullable().optional(),

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
