import { z } from "zod";
import { UuidSchema } from "./common.js";

export const TimezoneSchema = z.string().min(1); // IANA timezone string, e.g. "America/New_York"

export const PracticeSchema = z.object({
  id: UuidSchema,
  name: z.string().min(1).max(255),
  timezone: TimezoneSchema,
  phone: z.string().max(20).optional(),
  addressLine1: z.string().max(255).optional(),
  addressLine2: z.string().max(255).optional(),
  city: z.string().max(100).optional(),
  state: z.string().length(2).optional(),
  zip: z.string().max(10).optional(),
  // Feature flags — opt-in per-practice modules
  features: z
    .object({
      eligibility_verification: z.boolean().default(false),
      copay_estimation: z.boolean().default(false),
      claims_submission: z.boolean().default(false),
    })
    .default({}),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const CreatePracticeSchema = PracticeSchema.omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});

export const ProviderSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  firstName: z.string().min(1).max(100),
  lastName: z.string().min(1).max(100),
  npi: z.string().length(10), // NPI is always exactly 10 digits
  role: z.enum(["dentist", "hygienist", "assistant"]),
  isActive: z.boolean().default(true),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const CreateProviderSchema = ProviderSchema.omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});

export const OperatorySchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  name: z.string().min(1).max(100), // e.g. "Operatory 1", "Hygiene Room"
  isActive: z.boolean().default(true),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const CreateOperatorySchema = OperatorySchema.omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});

export type Practice = z.infer<typeof PracticeSchema>;
export type CreatePractice = z.infer<typeof CreatePracticeSchema>;
export type Provider = z.infer<typeof ProviderSchema>;
export type CreateProvider = z.infer<typeof CreateProviderSchema>;
export type Operatory = z.infer<typeof OperatorySchema>;
export type CreateOperatory = z.infer<typeof CreateOperatorySchema>;
