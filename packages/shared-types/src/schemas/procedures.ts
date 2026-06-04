import { z } from "zod";
import { UuidSchema } from "./common.js";

export const CdtCategorySchema = z.enum([
  "diagnostic",
  "preventive",
  "basic",
  "major",
  "ortho",
  "other",
]);

export const EstimateSourceSchema = z.enum([
  "manual",
  "eligibility",
  "prior_eob",
]);

export const CdtCodeSchema = z.object({
  id: UuidSchema,
  code: z.string().min(1),
  description: z.string().min(1),
  category: CdtCategorySchema,
  defaultFeeCents: z.number().int().nonnegative().nullable(),
  isActive: z.boolean(),
});

export const AppointmentProcedureSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  appointmentId: UuidSchema,
  patientId: UuidSchema,
  cdtCodeId: UuidSchema.nullable(),
  procedureCode: z.string().nullable(),
  procedureName: z.string().min(1),
  toothNumber: z.string().nullable(),
  surface: z.string().nullable(),
  feeCents: z.number().int().nonnegative(),
  insuranceEstCents: z.number().int().nonnegative().nullable(),
  patientEstCents: z.number().int().nonnegative().nullable(),
  estimateSource: EstimateSourceSchema.nullable(),
  notes: z.string().nullable(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const CreateAppointmentProcedureSchema = z.object({
  cdtCodeId: UuidSchema.optional(),
  procedureCode: z.string().optional(),
  procedureName: z.string().min(1),
  toothNumber: z.string().optional(),
  surface: z.string().optional(),
  feeCents: z.number().int().nonnegative(),
  insuranceEstCents: z.number().int().nonnegative().optional(),
  patientEstCents: z.number().int().nonnegative().optional(),
  estimateSource: EstimateSourceSchema.optional(),
  notes: z.string().optional(),
});

export const UpdateAppointmentProcedureSchema =
  CreateAppointmentProcedureSchema.partial();

export const ProcedureTotalsSchema = z.object({
  feeCentsTotal: z.number().int().nonnegative(),
  insuranceEstCentsTotal: z.number().int().nonnegative(),
  patientEstCentsTotal: z.number().int().nonnegative(),
});

export const AppointmentProcedureListResponseSchema = z.object({
  items: z.array(AppointmentProcedureSchema),
  totals: ProcedureTotalsSchema,
});
