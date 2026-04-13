import { z } from "zod";
import { UuidSchema } from "./common.js";

export const MaritalStatusSchema = z.enum([
  "single",
  "married",
  "divorced",
  "widowed",
  "separated",
  "domestic_partner",
  "other",
]);

export const PatientSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  firstName: z.string().min(1).max(100),
  lastName: z.string().min(1).max(100),
  dateOfBirth: z.string().date(), // ISO 8601 date string, YYYY-MM-DD
  sex: z.enum(["male", "female", "other", "unknown"]).optional(),
  maritalStatus: MaritalStatusSchema.optional(),
  lastXrayDate: z.string().date().optional(),
  phone: z.string().max(20).optional(),
  email: z.string().email().max(255).optional(),
  addressLine1: z.string().max(255).optional(),
  addressLine2: z.string().max(255).optional(),
  city: z.string().max(100).optional(),
  state: z.string().length(2).optional(),
  zip: z.string().max(10).optional(),
  // PHI — SSN stored AES-256 encrypted at application layer, never plaintext.
  // Accepts 4-digit (last four) or full 9-digit SSN.
  ssn: z.string().regex(/^\d{4}$|^\d{9}$/).optional(),
  emergencyContactName: z.string().max(200).optional(),
  emergencyContactPhone: z.string().max(20).optional(),
  occupation: z.string().max(200).optional(),
  employer: z.string().max(200).optional(),
  referralSource: z.string().max(200).optional(),
  allergies: z.array(z.string()).default([]),
  medicalAlerts: z.array(z.string()).default([]),
  medications: z.array(z.string()).default([]),
  doctorNotes: z.string().max(5000).optional(),
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
}).extend({
  // practiceId is inferred from the authenticated X-Practice-ID header;
  // providing it in the body is optional and used only for mismatch validation.
  practiceId: UuidSchema.optional(),
});

export const UpdatePatientSchema = CreatePatientSchema.partial();

export const PatientSearchQuerySchema = z.object({
  q: z.string().min(1).optional(),
  page: z.number().int().min(1).default(1),
  pageSize: z.number().int().min(1).max(100).default(20),
});

export type MaritalStatus = z.infer<typeof MaritalStatusSchema>;
export type Patient = z.infer<typeof PatientSchema>;
export type CreatePatient = z.infer<typeof CreatePatientSchema>;
export type UpdatePatient = z.infer<typeof UpdatePatientSchema>;
export type PatientSearchQuery = z.infer<typeof PatientSearchQuerySchema>;
