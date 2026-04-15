import { z } from "zod";
import { UuidSchema } from "./common.js";

// ── Appointment Types ────────────────────────────────────────────────────────

export const AppointmentTypeSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  name: z.string().min(1).max(255),
  durationMinutes: z.number().int().min(5).max(480),
  color: z.string().regex(/^#[0-9A-Fa-f]{6}$/).default("#5B8DEF"),
  defaultCdtCodes: z.array(z.string().max(10)).default([]),
  isActive: z.boolean().default(true),
  displayOrder: z.number().int().default(0),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const CreateAppointmentTypeSchema = AppointmentTypeSchema.omit({
  id: true,
  createdAt: true,
  updatedAt: true,
}).extend({
  practiceId: UuidSchema.optional(),
});

export const UpdateAppointmentTypeSchema = CreateAppointmentTypeSchema.partial();

// ── Appointments ─────────────────────────────────────────────────────────────

export const AppointmentStatusSchema = z.enum([
  "scheduled",
  "confirmed",
  "checked_in",
  "in_chair",
  "completed",
  "cancelled",
  "no_show",
]);

export const AppointmentSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  patientId: UuidSchema.optional(),
  providerId: UuidSchema.optional(),
  operatoryId: UuidSchema.optional(),
  appointmentTypeId: UuidSchema.optional(),
  startTime: z.string().datetime(),
  endTime: z.string().datetime(),
  status: AppointmentStatusSchema,
  notes: z.string().max(5000).optional(),
  cancellationReason: z.string().max(1000).optional(),
  // Eager-loaded display fields (populated on GET responses)
  patientName: z.string().optional(),
  providerName: z.string().optional(),
  operatoryName: z.string().optional(),
  appointmentTypeName: z.string().optional(),
  appointmentTypeColor: z.string().optional(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const CreateAppointmentSchema = z.object({
  patientId: UuidSchema,
  providerId: UuidSchema,
  operatoryId: UuidSchema,
  appointmentTypeId: UuidSchema.optional(),
  startTime: z.string().datetime(),
  endTime: z.string().datetime(),
  notes: z.string().max(5000).optional(),
});

export const UpdateAppointmentSchema = z.object({
  patientId: UuidSchema.optional(),
  providerId: UuidSchema.optional(),
  operatoryId: UuidSchema.optional(),
  appointmentTypeId: UuidSchema.optional(),
  startTime: z.string().datetime().optional(),
  endTime: z.string().datetime().optional(),
  status: AppointmentStatusSchema.optional(),
  notes: z.string().max(5000).optional(),
  cancellationReason: z.string().max(1000).optional(),
});

export const CancelAppointmentSchema = z.object({
  cancellationReason: z.string().max(1000).optional(),
});

// ── Providers (response schema — model already exists) ───────────────────────

export const CreateProviderSchema = z.object({
  fullName: z.string().min(1).max(255),
  npi: z.string().length(10).regex(/^\d{10}$/),
  providerType: z.enum(["dentist", "hygienist", "specialist", "other"]),
  licenseNumber: z.string().max(50).optional(),
  specialty: z.string().max(255).optional(),
  color: z.string().regex(/^#[0-9A-Fa-f]{6}$/).default("#4F86C6"),
  isActive: z.boolean().default(true),
  displayOrder: z.number().int().default(0),
});

export const UpdateProviderSchema = CreateProviderSchema.partial();

export const ProviderResponseSchema = CreateProviderSchema.extend({
  id: UuidSchema,
  practiceId: UuidSchema,
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

// ── Operatories (response schema — model already exists) ─────────────────────

export const CreateOperatorySchema = z.object({
  name: z.string().min(1).max(100),
  color: z.string().regex(/^#[0-9A-Fa-f]{6}$/).default("#7BC67E"),
  isActive: z.boolean().default(true),
  displayOrder: z.number().int().default(0),
});

export const UpdateOperatorySchema = CreateOperatorySchema.partial();

export const OperatoryResponseSchema = CreateOperatorySchema.extend({
  id: UuidSchema,
  practiceId: UuidSchema,
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

// ── Type exports ─────────────────────────────────────────────────────────────

export type AppointmentType = z.infer<typeof AppointmentTypeSchema>;
export type CreateAppointmentType = z.infer<typeof CreateAppointmentTypeSchema>;
export type UpdateAppointmentType = z.infer<typeof UpdateAppointmentTypeSchema>;
export type AppointmentStatus = z.infer<typeof AppointmentStatusSchema>;
export type Appointment = z.infer<typeof AppointmentSchema>;
export type CreateAppointment = z.infer<typeof CreateAppointmentSchema>;
export type UpdateAppointment = z.infer<typeof UpdateAppointmentSchema>;
export type CancelAppointment = z.infer<typeof CancelAppointmentSchema>;
export type ProviderResponse = z.infer<typeof ProviderResponseSchema>;
export type CreateProvider = z.infer<typeof CreateProviderSchema>;
export type UpdateProvider = z.infer<typeof UpdateProviderSchema>;
export type OperatoryResponse = z.infer<typeof OperatoryResponseSchema>;
export type CreateOperatory = z.infer<typeof CreateOperatorySchema>;
export type UpdateOperatory = z.infer<typeof UpdateOperatorySchema>;
