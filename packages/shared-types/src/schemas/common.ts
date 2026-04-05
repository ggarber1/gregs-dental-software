import { z } from "zod";

export const UuidSchema = z.string().uuid();

export const IdempotencyKeySchema = z.string().min(1).max(255);

export const PaginationQuerySchema = z.object({
  page: z.number().int().min(1).default(1),
  pageSize: z.number().int().min(1).max(100).default(20),
});

export const PaginationMetaSchema = z.object({
  page: z.number().int(),
  pageSize: z.number().int(),
  total: z.number().int(),
  totalPages: z.number().int(),
});

export function ApiResponseSchema<T extends z.ZodTypeAny>(dataSchema: T) {
  return z.object({
    data: dataSchema,
    meta: PaginationMetaSchema.optional(),
  });
}

export const ApiErrorSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.record(z.unknown()).optional(),
  }),
});

export type UuidType = z.infer<typeof UuidSchema>;
export type PaginationQuery = z.infer<typeof PaginationQuerySchema>;
export type PaginationMeta = z.infer<typeof PaginationMetaSchema>;
export type ApiError = z.infer<typeof ApiErrorSchema>;
