import { z } from "zod";
import { UuidSchema } from "./common.js";

export const PatientToleranceSchema = z.enum(["excellent", "good", "fair", "poor"]);

export const TemplateTypeSchema = z.enum([
  "exam",
  "prophy",
  "extraction",
  "crown_prep",
  "crown_seat",
  "root_canal",
  "filling",
  "srp",
  "other",
]);

export const ClinicalNoteSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  patientId: UuidSchema,
  appointmentId: UuidSchema.nullable(),
  providerId: UuidSchema,
  visitDate: z.string().date(),
  chiefComplaint: z.string().nullable(),
  anesthesia: z.string().nullable(),
  patientTolerance: PatientToleranceSchema.nullable(),
  complications: z.string().nullable(),
  treatmentRendered: z.string().min(1),
  nextVisitPlan: z.string().nullable(),
  notes: z.string().nullable(),
  templateType: TemplateTypeSchema.nullable(),
  isSigned: z.boolean(),
  signedAt: z.string().datetime().nullable(),
  signedByProviderId: UuidSchema.nullable(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const ClinicalNoteSummarySchema = z.object({
  id: UuidSchema,
  patientId: UuidSchema,
  providerId: UuidSchema,
  appointmentId: UuidSchema.nullable(),
  visitDate: z.string().date(),
  treatmentRendered: z.string().min(1),
  templateType: TemplateTypeSchema.nullable(),
  isSigned: z.boolean(),
  signedAt: z.string().datetime().nullable(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const CreateClinicalNoteSchema = z.object({
  appointmentId: UuidSchema.optional(),
  providerId: UuidSchema,
  visitDate: z.string().date(),
  chiefComplaint: z.string().optional(),
  anesthesia: z.string().optional(),
  patientTolerance: PatientToleranceSchema.optional(),
  complications: z.string().optional(),
  treatmentRendered: z.string().min(1),
  nextVisitPlan: z.string().optional(),
  notes: z.string().optional(),
  templateType: TemplateTypeSchema.optional(),
});

export const UpdateClinicalNoteSchema = z.object({
  chiefComplaint: z.string().optional(),
  anesthesia: z.string().optional(),
  patientTolerance: PatientToleranceSchema.optional(),
  complications: z.string().optional(),
  treatmentRendered: z.string().min(1).optional(),
  nextVisitPlan: z.string().optional(),
  notes: z.string().optional(),
  templateType: TemplateTypeSchema.optional(),
});

export const ClinicalNoteListResponseSchema = z.object({
  items: z.array(ClinicalNoteSummarySchema),
  nextCursor: z.string().nullable(),
  hasMore: z.boolean(),
});

export type PatientTolerance = z.infer<typeof PatientToleranceSchema>;
export type TemplateType = z.infer<typeof TemplateTypeSchema>;
export type ClinicalNote = z.infer<typeof ClinicalNoteSchema>;
export type ClinicalNoteSummary = z.infer<typeof ClinicalNoteSummarySchema>;
export type CreateClinicalNote = z.infer<typeof CreateClinicalNoteSchema>;
export type UpdateClinicalNote = z.infer<typeof UpdateClinicalNoteSchema>;
export type ClinicalNoteListResponse = z.infer<typeof ClinicalNoteListResponseSchema>;
