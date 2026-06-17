import { z } from "zod";
import { UuidSchema } from "./common.js";
import { CdtCategorySchema } from "./procedures.js";

// ---- Contracted fee schedule ----

export const ContractedFeeRowSchema = z.object({
  cdtCodeId: UuidSchema,
  code: z.string().min(1),
  description: z.string().min(1),
  category: CdtCategorySchema,
  payerId: z.string().min(1),
  allowedAmountCents: z.number().int().nonnegative().nullable(),
  notCovered: z.boolean(),
  requiresPriorAuth: z.boolean(),
});
export type ContractedFeeRow = z.infer<typeof ContractedFeeRowSchema>;

export const SetContractedFeeSchema = z.object({
  allowedAmountCents: z.number().int().nonnegative().nullable(),
  notCovered: z.boolean().optional(),
  requiresPriorAuth: z.boolean().optional(),
});
export type SetContractedFee = z.infer<typeof SetContractedFeeSchema>;

// ---- Co-pay estimate ----

export const CopayLineItemSchema = z.object({
  procedureId: UuidSchema,
  cdtCode: z.string(),
  category: CdtCategorySchema,
  providerFeeCents: z.number().int(),
  allowedAmountCents: z.number().int(),
  writeOffCents: z.number().int(),
  deductibleAppliedCents: z.number().int(),
  insuranceOwesCents: z.number().int(),
  patientOwesCents: z.number().int(),
  needsManualEntry: z.boolean(),
  notCovered: z.boolean(),
  isFrequencyExceeded: z.boolean(),
  isInWaitingPeriod: z.boolean(),
  annualMaxCapApplied: z.boolean(),
});
export type CopayLineItem = z.infer<typeof CopayLineItemSchema>;

export const CopayEstimateSchema = z.object({
  id: UuidSchema,
  appointmentId: UuidSchema,
  eligibilityCheckId: UuidSchema.nullable(),
  calculatedAt: z.string().datetime(),
  planType: z.enum(["ppo", "premier", "medicaid", "indemnity", "dhmo"]),
  totalProviderFeeCents: z.number().int(),
  totalWriteOffCents: z.number().int(),
  totalInsuranceOwesCents: z.number().int(),
  totalPatientOwesCents: z.number().int(),
  deductibleRemainingAfterCents: z.number().int().nullable(),
  annualMaxRemainingAfterCents: z.number().int().nullable(),
  overridePatientCents: z.number().int().nullable(),
  overrideNote: z.string().nullable(),
  hasSecondaryInsurance: z.boolean(),
  lineItems: z.array(CopayLineItemSchema),
});
export type CopayEstimate = z.infer<typeof CopayEstimateSchema>;

export const OverrideCopaySchema = z.object({
  overridePatientCents: z.number().int().nonnegative().nullable(),
  overrideNote: z.string().optional(),
});
export type OverrideCopay = z.infer<typeof OverrideCopaySchema>;
