import { z } from "zod";
import { UuidSchema } from "./common.js";

export const PerioSiteSchema = z.enum(["db", "b", "mb", "dl", "l", "ml"]);

export const FurcationSchema = z.enum(["I", "II", "III"]);

export const PerioReadingCreateSchema = z.object({
  toothNumber: z.string().min(1),
  site: PerioSiteSchema,
  probingDepthMm: z.number().int().min(0).max(20),
  recessionMm: z.number().int().min(0).max(15).optional().default(0),
  bleeding: z.boolean().optional().default(false),
  suppuration: z.boolean().optional().default(false),
  furcation: FurcationSchema.nullable().optional(),
  mobility: z.number().int().min(0).max(3).nullable().optional(),
});

export const PerioReadingOutSchema = z.object({
  id: UuidSchema,
  perioChartId: UuidSchema,
  toothNumber: z.string(),
  site: PerioSiteSchema,
  probingDepthMm: z.number().int(),
  recessionMm: z.number().int(),
  cal: z.number().int(),
  bleeding: z.boolean(),
  suppuration: z.boolean(),
  furcation: FurcationSchema.nullable(),
  mobility: z.number().int().nullable(),
  createdAt: z.string().datetime(),
});

export const PerioChartCreateSchema = z.object({
  providerId: UuidSchema,
  chartDate: z.string().date(),
  appointmentId: UuidSchema.optional(),
  notes: z.string().optional(),
  readings: z.array(PerioReadingCreateSchema).optional().default([]),
});

export const AddPerioReadingsSchema = z.object({
  readings: z.array(PerioReadingCreateSchema),
});

export const PerioChartSummarySchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  patientId: UuidSchema,
  appointmentId: UuidSchema.nullable(),
  providerId: UuidSchema,
  chartDate: z.string().date(),
  notes: z.string().nullable(),
  avgProbingDepthMm: z.number(),
  sitesGte4mm: z.number().int(),
  sitesGte6mm: z.number().int(),
  bleedingSiteCount: z.number().int(),
  createdAt: z.string().datetime(),
  updatedAt: z.string().datetime(),
});

export const PerioChartDetailSchema = PerioChartSummarySchema.extend({
  readings: z.array(PerioReadingOutSchema),
});

export const PerioChartListResponseSchema = z.object({
  items: z.array(PerioChartSummarySchema),
  nextCursor: z.string().nullable(),
  hasMore: z.boolean(),
});

export const PerioSiteDeltaSchema = z.object({
  toothNumber: z.string(),
  site: PerioSiteSchema,
  depthA: z.number().int(),
  depthB: z.number().int(),
  delta: z.number().int(),
});

export const PerioChartComparisonSchema = z.object({
  chartA: PerioChartDetailSchema,
  chartB: PerioChartDetailSchema,
  deltas: z.array(PerioSiteDeltaSchema),
});

export type AddPerioReadings = z.infer<typeof AddPerioReadingsSchema>;
export type PerioSite = z.infer<typeof PerioSiteSchema>;
export type Furcation = z.infer<typeof FurcationSchema>;
export type PerioReadingCreate = z.infer<typeof PerioReadingCreateSchema>;
export type PerioReadingOut = z.infer<typeof PerioReadingOutSchema>;
export type PerioChartCreate = z.infer<typeof PerioChartCreateSchema>;
export type PerioChartSummary = z.infer<typeof PerioChartSummarySchema>;
export type PerioChartDetail = z.infer<typeof PerioChartDetailSchema>;
export type PerioChartListResponse = z.infer<typeof PerioChartListResponseSchema>;
export type PerioSiteDelta = z.infer<typeof PerioSiteDeltaSchema>;
export type PerioChartComparison = z.infer<typeof PerioChartComparisonSchema>;
