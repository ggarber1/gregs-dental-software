import { z } from "zod";
import { UuidSchema } from "./common.js";
import { ARBucketsSchema } from "./reports.js";

export const StatementDeliveryMethodSchema = z.enum(["email", "download"]);
export type StatementDeliveryMethod = z.infer<typeof StatementDeliveryMethodSchema>;

/**
 * One patient with an outstanding balance. Buckets hold gross charge amounts by
 * age of the charge. Payments and adjustments are not attributed to a bucket;
 * they are reported as a single signed creditsCents total (normally negative).
 */
export const PatientAgingRowSchema = z.object({
  patientId: UuidSchema,
  patientName: z.string(),
  email: z.string().nullable(),
  balanceCents: z.number().int(),
  buckets: ARBucketsSchema,
  creditsCents: z.number().int(),
  oldestChargeAt: z.string().datetime().nullable(),
  lastStatementAt: z.string().datetime().nullable(),
  lastStatementMethod: StatementDeliveryMethodSchema.nullable(),
});
export type PatientAgingRow = z.infer<typeof PatientAgingRowSchema>;

/** Append-only delivery record. `buckets` is the aging snapshot at generation time. */
export const PatientStatementSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  patientId: UuidSchema,
  deliveryMethod: StatementDeliveryMethodSchema,
  balanceCents: z.number().int(),
  buckets: ARBucketsSchema,
  generatedAt: z.string().datetime(),
  deliveredAt: z.string().datetime().nullable(),
  generatedBy: z.string(),
});
export type PatientStatement = z.infer<typeof PatientStatementSchema>;

export const GenerateStatementRequestSchema = z.object({
  deliveryMethod: StatementDeliveryMethodSchema,
});
export type GenerateStatementRequest = z.infer<typeof GenerateStatementRequestSchema>;
