import { z } from "zod";
import { UuidSchema } from "./common.js";

export const ConditionTypeSchema = z.enum([
  "existing_restoration",
  "missing",
  "implant",
  "crown",
  "bridge_pontic",
  "bridge_abutment",
  "root_canal",
  "decay",
  "fracture",
  "watch",
  "other",
]);

export const NotationSystemSchema = z.enum(["universal", "fdi"]);

export const ToothConditionStatusSchema = z.enum([
  "existing",
  "treatment_planned",
  "completed_today",
]);

// Normalized tooth-surface codes.
//   B = buccal/facial, M = mesial, O = occlusal, D = distal, L = lingual,
//   I = incisal (anterior teeth — used in place of O).
export const ToothSurfaceSchema = z.enum(["B", "M", "O", "D", "L", "I"]);

export const ToothConditionSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  patientId: UuidSchema,
  toothNumber: z.string().min(1),
  notationSystem: NotationSystemSchema,
  conditionType: ConditionTypeSchema,
  surface: z.string().nullable(),
  surfaces: z.array(ToothSurfaceSchema),
  material: z.string().nullable(),
  notes: z.string().nullable(),
  status: ToothConditionStatusSchema,
  recordedAt: z.string().date(),
  recordedBy: UuidSchema,
  appointmentId: UuidSchema.nullable(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const CreateToothConditionSchema = z.object({
  toothNumber: z.string().min(1),
  notationSystem: NotationSystemSchema.optional(),
  conditionType: ConditionTypeSchema,
  surface: z.string().optional(),
  surfaces: z.array(ToothSurfaceSchema).optional(),
  material: z.string().optional(),
  notes: z.string().optional(),
  status: ToothConditionStatusSchema.optional(),
  recordedAt: z.string().date(),
  recordedBy: UuidSchema,
  appointmentId: UuidSchema.optional(),
});

export const UpdateToothConditionSchema = z.object({
  status: ToothConditionStatusSchema.optional(),
  surface: z.string().optional(),
  surfaces: z.array(ToothSurfaceSchema).optional(),
  material: z.string().optional(),
  notes: z.string().optional(),
});

export const ToothChartResponseSchema = z.object({
  conditions: z.array(ToothConditionSchema),
});

export type ConditionType = z.infer<typeof ConditionTypeSchema>;
export type NotationSystem = z.infer<typeof NotationSystemSchema>;
export type ToothConditionStatus = z.infer<typeof ToothConditionStatusSchema>;
export type ToothSurface = z.infer<typeof ToothSurfaceSchema>;
export type ToothCondition = z.infer<typeof ToothConditionSchema>;
export type CreateToothCondition = z.infer<typeof CreateToothConditionSchema>;
export type UpdateToothCondition = z.infer<typeof UpdateToothConditionSchema>;
export type ToothChartResponse = z.infer<typeof ToothChartResponseSchema>;
