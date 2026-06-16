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
