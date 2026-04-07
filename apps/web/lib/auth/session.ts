import { cookies } from "next/headers";

import { ACCESS_TOKEN_COOKIE } from "./cookies";
import { validateAccessToken, type CognitoJwtPayload } from "./jwks";

export interface CognitoSession {
  sub: string;
  email: string;
  practiceId: string | null;
  groups: string[];
  accessToken: string;
  expiresAt: number; // Unix timestamp (seconds)
}

function payloadToSession(token: string, payload: CognitoJwtPayload): CognitoSession {
  return {
    sub: payload.sub ?? "",
    email: payload.email ?? "",
    practiceId: payload["custom:practice_id"] ?? null,
    groups: payload["cognito:groups"] ?? [],
    accessToken: token,
    expiresAt: payload.exp ?? 0,
  };
}

// Server-side only — reads from the request cookie store.
// Returns null if no token is present or the token is invalid/expired.
export async function getSession(): Promise<CognitoSession | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get(ACCESS_TOKEN_COOKIE)?.value;
  if (!token) return null;

  const payload = await validateAccessToken(token);
  if (!payload) return null;

  return payloadToSession(token, payload);
}
