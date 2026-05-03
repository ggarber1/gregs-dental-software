import { z } from "zod";
import { UuidSchema } from "./common.js";

export const AllergyEntrySchema = z.object({
  name: z.string().min(1).max(255),
  severity: z.string().max(50).optional(),
  reaction: z.string().max(500).optional(),
});

export const MedicationEntrySchema = z.object({
  name: z.string().min(1).max(255),
  dose: z.string().max(100).optional(),
  frequency: z.string().max(100).optional(),
});

export const ConditionEntrySchema = z.object({
  name: z.string().min(1).max(255),
  icd10Hint: z.string().max(20).optional(),
  notes: z.string().max(1000).optional(),
});

export const MedicalFlagsSchema = z.object({
  flagBloodThinners: z.boolean().default(false),
  flagBisphosphonates: z.boolean().default(false),
  flagHeartCondition: z.boolean().default(false),
  flagDiabetes: z.boolean().default(false),
  flagPacemaker: z.boolean().default(false),
  flagLatexAllergy: z.boolean().default(false),
});

export const MedicalHistoryVersionSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  patientId: UuidSchema,
  versionNumber: z.number().int().min(1),
  recordedBy: UuidSchema,
  recordedAt: z.string().datetime(),
  allergies: z.array(AllergyEntrySchema),
  medications: z.array(MedicationEntrySchema),
  conditions: z.array(ConditionEntrySchema),
  flags: MedicalFlagsSchema,
  additionalNotes: z.string().max(5000).optional(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const MedicalHistoryVersionSummarySchema = z.object({
  id: UuidSchema,
  versionNumber: z.number().int().min(1),
  recordedBy: UuidSchema,
  recordedAt: z.string().datetime(),
  allergyCount: z.number().int().min(0),
  medicationCount: z.number().int().min(0),
  conditionCount: z.number().int().min(0),
  flags: MedicalFlagsSchema,
});

export const CreateMedicalHistorySchema = z.object({
  allergies: z.array(AllergyEntrySchema).default([]),
  medications: z.array(MedicationEntrySchema).default([]),
  conditions: z.array(ConditionEntrySchema).default([]),
  flags: MedicalFlagsSchema.partial().optional(),
  additionalNotes: z.string().max(5000).optional(),
});

export const MedicalHistoryHistoryResponseSchema = z.object({
  items: z.array(MedicalHistoryVersionSummarySchema),
  total: z.number().int(),
  page: z.number().int(),
  pageSize: z.number().int(),
});

export type AllergyEntry = z.infer<typeof AllergyEntrySchema>;
export type MedicationEntry = z.infer<typeof MedicationEntrySchema>;
export type ConditionEntry = z.infer<typeof ConditionEntrySchema>;
export type MedicalFlags = z.infer<typeof MedicalFlagsSchema>;
export type MedicalHistoryVersion = z.infer<typeof MedicalHistoryVersionSchema>;
export type MedicalHistoryVersionSummary = z.infer<typeof MedicalHistoryVersionSummarySchema>;
export type CreateMedicalHistory = z.infer<typeof CreateMedicalHistorySchema>;
export type MedicalHistoryHistoryResponse = z.infer<typeof MedicalHistoryHistoryResponseSchema>;
