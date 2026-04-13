import { z } from "zod";
import { UuidSchema } from "./common.js";

export const IntakeStatusSchema = z.enum(["pending", "completed", "expired"]);

export const RelationshipToInsuredSchema = z.enum(["self", "spouse", "child", "other"]);

// Public endpoint response — minimal, reveals only practice name + patient first name
export const IntakeFormTokenInfoSchema = z.object({
  practiceName: z.string(),
  patientFirstName: z.string(),
});

// Form payload submitted by the patient (encrypted at rest)
export const SubmitIntakeFormSchema = z.object({
  // Personal info
  firstName: z.string().min(1).max(100),
  lastName: z.string().min(1).max(100),
  dateOfBirth: z.string().date(),
  sex: z.enum(["male", "female", "other", "unknown"]).optional(),
  phone: z.string().max(20),
  email: z.string().email().max(255).optional(),
  addressLine1: z.string().max(255).optional(),
  addressLine2: z.string().max(255).optional(),
  city: z.string().max(100).optional(),
  state: z.string().length(2).optional(),
  zip: z.string().max(10).optional(),
  ssnLastFour: z.string().length(4).regex(/^\d{4}$/).optional(),
  maritalStatus: z
    .enum(["single", "married", "divorced", "widowed", "separated", "domestic_partner", "other"])
    .optional(),
  emergencyContactName: z.string().max(200).optional(),
  emergencyContactPhone: z.string().max(20).optional(),
  occupation: z.string().max(200).optional(),
  employer: z.string().max(200).optional(),
  referralSource: z.string().max(200).optional(),
  // Medical history
  medicalConditions: z.array(z.string()).default([]),
  medications: z.array(z.string()).default([]),
  allergies: z.array(z.string()).default([]),
  dentalSymptoms: z.array(z.string()).default([]),
  // Dental history
  lastDentalVisit: z.string().optional(),
  lastXrayDate: z.string().optional(),
  previousDentist: z.string().optional(),
  chiefComplaint: z.string().optional(),
  // Insurance
  insuranceCarrier: z.string().optional(),
  insuranceMemberId: z.string().optional(),
  insuranceGroupNumber: z.string().optional(),
  insuranceHolderName: z.string().optional(),
  insuranceHolderDob: z.string().optional(),
  relationshipToInsured: RelationshipToInsuredSchema.optional(),
  // HIPAA consent — validated server-side that hipaaConsentAccepted === true
  hipaaConsentAccepted: z.boolean(),
  hipaaConsentTimestamp: z.string().datetime(),
  hipaaConsentSignature: z.string().min(1),
  smsOptIn: z.boolean(),
});

// Staff: send intake form to a patient
export const SendIntakeFormSchema = z.object({
  patientId: UuidSchema,
});

// Staff: response from POST /api/v1/intake/send
export const SendIntakeFormResponseSchema = z.object({
  intakeFormId: UuidSchema,
  expiresAt: z.string().datetime(),
  formUrl: z.string().url(),
});

// Staff: list item (no responses)
export const IntakeFormSummarySchema = z.object({
  id: UuidSchema,
  patientId: UuidSchema,
  status: IntakeStatusSchema,
  expiresAt: z.string().datetime(),
  createdAt: z.string().datetime(),
  createdBy: UuidSchema,
});

// Staff: detail view (includes decrypted responses when completed)
export const IntakeFormDetailSchema = IntakeFormSummarySchema.extend({
  responses: SubmitIntakeFormSchema.nullable(),
});

export type IntakeStatus = z.infer<typeof IntakeStatusSchema>;
export type RelationshipToInsured = z.infer<typeof RelationshipToInsuredSchema>;
export type IntakeFormTokenInfo = z.infer<typeof IntakeFormTokenInfoSchema>;
export type SubmitIntakeForm = z.infer<typeof SubmitIntakeFormSchema>;
export type SendIntakeForm = z.infer<typeof SendIntakeFormSchema>;
export type SendIntakeFormResponse = z.infer<typeof SendIntakeFormResponseSchema>;
export type IntakeFormSummary = z.infer<typeof IntakeFormSummarySchema>;
export type IntakeFormDetail = z.infer<typeof IntakeFormDetailSchema>;
