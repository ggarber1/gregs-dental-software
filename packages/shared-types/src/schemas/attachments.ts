import { z } from "zod";
import { UuidSchema } from "./common.js";

export const AttachmentTypeSchema = z.enum([
  "xray",
  "photo",
  "perio_narrative",
  "lab_rx",
  "other",
]);
export type AttachmentType = z.infer<typeof AttachmentTypeSchema>;

export const AppointmentAttachmentSchema = z.object({
  id: UuidSchema,
  practiceId: UuidSchema,
  appointmentId: UuidSchema,
  s3Key: z.string(),
  fileName: z.string(),
  fileSizeBytes: z.number().int(),
  contentType: z.string(),
  attachmentType: AttachmentTypeSchema,
  uploadedBy: z.string(),
  createdAt: z.string().datetime(),
});
export type AppointmentAttachment = z.infer<typeof AppointmentAttachmentSchema>;
