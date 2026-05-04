import { z } from "zod";
import { UuidSchema } from "./common.js";

export const TreatmentPlanStatusSchema = z.enum([
  "proposed",
  "accepted",
  "in_progress",
  "completed",
  "refused",
  "superseded",
]);

export const TreatmentPlanItemStatusSchema = z.enum([
  "proposed",
  "accepted",
  "scheduled",
  "completed",
  "refused",
]);

export const TreatmentPlanItemSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  treatmentPlanId: UuidSchema,
  patientId: UuidSchema,
  toothNumber: z.string().nullable(),
  procedureCode: z.string().min(1),
  procedureName: z.string().min(1),
  surface: z.string().nullable(),
  feeCents: z.number().int().nonnegative(),
  insuranceEstCents: z.number().int().nonnegative().nullable(),
  patientEstCents: z.number().int().nonnegative().nullable(),
  status: TreatmentPlanItemStatusSchema,
  priority: z.number().int().positive(),
  appointmentId: UuidSchema.nullable(),
  completedAppointmentId: UuidSchema.nullable(),
  notes: z.string().nullable(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const TreatmentPlanSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  patientId: UuidSchema,
  name: z.string().min(1),
  status: TreatmentPlanStatusSchema,
  presentedAt: z.string().date().nullable(),
  acceptedAt: z.string().date().nullable(),
  completedAt: z.string().date().nullable(),
  notes: z.string().nullable(),
  createdBy: UuidSchema,
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const TreatmentPlanDetailSchema = TreatmentPlanSchema.extend({
  items: z.array(TreatmentPlanItemSchema),
});

export const CreateTreatmentPlanItemSchema = z.object({
  toothNumber: z.string().optional(),
  procedureCode: z.string().min(1),
  procedureName: z.string().min(1),
  surface: z.string().optional(),
  feeCents: z.number().int().nonnegative(),
  insuranceEstCents: z.number().int().nonnegative().optional(),
  patientEstCents: z.number().int().nonnegative().optional(),
  priority: z.number().int().positive().optional(),
  notes: z.string().optional(),
});

export const CreateTreatmentPlanSchema = z.object({
  name: z.string().min(1).optional(),
  notes: z.string().optional(),
  items: z.array(CreateTreatmentPlanItemSchema).optional(),
});

export const UpdateTreatmentPlanSchema = z.object({
  name: z.string().min(1).optional(),
  status: TreatmentPlanStatusSchema.optional(),
  presentedAt: z.string().date().optional(),
  notes: z.string().optional(),
});

export const UpdateTreatmentPlanItemSchema = z.object({
  status: TreatmentPlanItemStatusSchema.optional(),
  feeCents: z.number().int().nonnegative().optional(),
  insuranceEstCents: z.number().int().nonnegative().optional(),
  patientEstCents: z.number().int().nonnegative().optional(),
  appointmentId: UuidSchema.optional(),
  completedAppointmentId: UuidSchema.optional(),
  priority: z.number().int().positive().optional(),
  notes: z.string().optional(),
});

export const TreatmentPlanListResponseSchema = z.object({
  items: z.array(TreatmentPlanSchema),
  nextCursor: z.string().nullable(),
  hasMore: z.boolean(),
});

export const OpenPlanQueueItemSchema = z.object({
  planId: UuidSchema,
  planName: z.string(),
  patientId: UuidSchema,
  patientName: z.string(),
  pendingItemCount: z.number().int().nonnegative(),
  daysSinceAcceptance: z.number().int().nonnegative(),
  acceptedAt: z.string().date().nullable(),
});

export type TreatmentPlanStatus = z.infer<typeof TreatmentPlanStatusSchema>;
export type TreatmentPlanItemStatus = z.infer<typeof TreatmentPlanItemStatusSchema>;
export type TreatmentPlanItem = z.infer<typeof TreatmentPlanItemSchema>;
export type TreatmentPlan = z.infer<typeof TreatmentPlanSchema>;
export type TreatmentPlanDetail = z.infer<typeof TreatmentPlanDetailSchema>;
export type CreateTreatmentPlanItem = z.infer<typeof CreateTreatmentPlanItemSchema>;
export type CreateTreatmentPlan = z.infer<typeof CreateTreatmentPlanSchema>;
export type UpdateTreatmentPlan = z.infer<typeof UpdateTreatmentPlanSchema>;
export type UpdateTreatmentPlanItem = z.infer<typeof UpdateTreatmentPlanItemSchema>;
export type TreatmentPlanListResponse = z.infer<typeof TreatmentPlanListResponseSchema>;
export type OpenPlanQueueItem = z.infer<typeof OpenPlanQueueItemSchema>;
