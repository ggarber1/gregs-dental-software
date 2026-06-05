import { z } from "zod";
import { UuidSchema } from "./common.js";

export const PortalAccountStatusSchema = z.enum(["none", "invited", "active", "revoked"]);

export const PortalInviteTokenInfoSchema = z.object({
  practiceName: z.string(),
  patientFirstName: z.string(),
  email: z.string().email(),
});

export const SendPortalInviteSchema = z.object({
  patientId: UuidSchema,
});

export const SendPortalInviteResponseSchema = z.object({
  portalAccountId: UuidSchema,
  status: z.enum(["invited", "active"]),
  expiresAt: z.string().datetime().nullable(),
  inviteUrl: z.string().url().nullable(),
});

export const PortalAccountStatusResponseSchema = z.object({
  patientId: UuidSchema,
  status: PortalAccountStatusSchema,
  email: z.string().email().nullable(),
  invitedAt: z.string().datetime().nullable(),
  enrolledAt: z.string().datetime().nullable(),
  inviteExpiresAt: z.string().datetime().nullable(),
});

export const PortalProfileSchema = z.object({
  patientId: UuidSchema,
  practiceId: UuidSchema,
  practiceName: z.string(),
  firstName: z.string(),
  lastName: z.string(),
  email: z.string().email().nullable(),
});

export type PortalAccountStatus = z.infer<typeof PortalAccountStatusSchema>;
export type PortalInviteTokenInfo = z.infer<typeof PortalInviteTokenInfoSchema>;
export type SendPortalInvite = z.infer<typeof SendPortalInviteSchema>;
export type SendPortalInviteResponse = z.infer<typeof SendPortalInviteResponseSchema>;
export type PortalAccountStatusResponse = z.infer<typeof PortalAccountStatusResponseSchema>;
export type PortalProfile = z.infer<typeof PortalProfileSchema>;
