import { z } from "zod";
import { UuidSchema } from "./common.js";

export const PatientSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  firstName: z.string().min(1).max(100),
  lastName: z.string().min(1).max(100),
  dateOfBirth: z.string().date(), // ISO 8601 date string, YYYY-MM-DD
  sex: z.enum(["male", "female", "other", "unknown"]).optional(),
  phone: z.string().max(20).optional(),
  email: z.string().email().max(255).optional(),
  addressLine1: z.string().max(255).optional(),
  addressLine2: z.string().max(255).optional(),
  city: z.string().max(100).optional(),
  state: z.string().length(2).optional(),
  zip: z.string().max(10).optional(),
  // PHI — SSN stored AES-256 encrypted at application layer, never plaintext
  ssnLastFour: z.string().length(4).optional(),
  allergies: z.array(z.string()).default([]),
  medicalAlerts: z.array(z.string()).default([]),
  smsOptOut: z.boolean().default(false),
  // Soft delete
  deletedAt: z.string().datetime().optional(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const CreatePatientSchema = PatientSchema.omit({
  id: true,
  deletedAt: true,
  createdAt: true,
  updatedAt: true,
});

export const UpdatePatientSchema = CreatePatientSchema.partial();

export const PatientSearchQuerySchema = z.object({
  q: z.string().min(1).optional(),
  page: z.number().int().min(1).default(1),
  pageSize: z.number().int().min(1).max(100).default(20),
});

export type Patient = z.infer<typeof PatientSchema>;
export type CreatePatient = z.infer<typeof CreatePatientSchema>;
export type UpdatePatient = z.infer<typeof UpdatePatientSchema>;
export type PatientSearchQuery = z.infer<typeof PatientSearchQuerySchema>;
