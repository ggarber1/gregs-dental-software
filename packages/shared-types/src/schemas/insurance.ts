import { z } from "zod";
import { UuidSchema } from "./common.js";
import { RelationshipToInsuredSchema } from "./intake.js";

export const InsurancePrioritySchema = z.enum(["primary", "secondary"]);

export const InsuranceSchema = z.object({
  id: UuidSchema,
  patientId: UuidSchema,
  practiceId: UuidSchema,
  insurancePlanId: UuidSchema.optional(),
  priority: InsurancePrioritySchema.default("primary"),
  carrier: z.string().min(1).max(255),
  memberId: z.string().max(100).optional(),
  groupNumber: z.string().max(100).optional(),
  relationshipToInsured: RelationshipToInsuredSchema.default("self"),
  insuredFirstName: z.string().max(100).optional(),
  insuredLastName: z.string().max(100).optional(),
  insuredDateOfBirth: z.string().date().optional(),
  isActive: z.boolean().default(true),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const CreateInsuranceSchema = z.object({
  insurancePlanId: UuidSchema.optional(),
  priority: InsurancePrioritySchema.default("primary"),
  carrier: z.string().min(1).max(255),
  memberId: z.string().max(100).optional(),
  groupNumber: z.string().max(100).optional(),
  relationshipToInsured: RelationshipToInsuredSchema.default("self"),
  insuredFirstName: z.string().max(100).optional(),
  insuredLastName: z.string().max(100).optional(),
  insuredDateOfBirth: z.string().date().optional(),
});

export const UpdateInsuranceSchema = CreateInsuranceSchema.partial();

export const InsurancePlanSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  carrierName: z.string().min(1).max(255),
  payerId: z.string().min(1).max(50),
  groupNumber: z.string().max(100).optional(),
  isInNetwork: z.boolean().default(true),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const CreateInsurancePlanSchema = z.object({
  carrierName: z.string().min(1).max(255),
  payerId: z.string().min(1).max(50),
  groupNumber: z.string().max(100).optional(),
  isInNetwork: z.boolean().optional().default(true),
});

export const UpdateInsurancePlanSchema = CreateInsurancePlanSchema.partial();

export type InsurancePriority = z.infer<typeof InsurancePrioritySchema>;
export type InsurancePlan = z.infer<typeof InsurancePlanSchema>;
export type CreateInsurancePlan = z.infer<typeof CreateInsurancePlanSchema>;
export type UpdateInsurancePlan = z.infer<typeof UpdateInsurancePlanSchema>;
export type Insurance = z.infer<typeof InsuranceSchema>;
export type CreateInsurance = z.infer<typeof CreateInsuranceSchema>;
export type UpdateInsurance = z.infer<typeof UpdateInsuranceSchema>;
