import type { NextRequest } from "next/server";

export const ACCESS_TOKEN_COOKIE = "dental-access-token";
export const REFRESH_TOKEN_COOKIE = "dental-refresh-token";

const COOKIE_BASE = [
  "Path=/",
  "SameSite=Strict",
  // Secure flag is omitted in development (no HTTPS on localhost).
  process.env.NODE_ENV === "production" ? "Secure" : "",
]
  .filter(Boolean)
  .join("; ");

// Used by the /api/auth/session route handler to set cookies on the Response.
export function buildSetCookieHeaders(accessToken: string, refreshToken: string): string[] {
  const accessMaxAge = 60 * 60; // 1 hour — matches Cognito access token validity
  const refreshMaxAge = 60 * 60 * 24 * 30; // 30 days — matches Cognito refresh token validity

  return [
    // Access token: NOT httpOnly so JavaScript can read it and forward to FastAPI.
    `${ACCESS_TOKEN_COOKIE}=${accessToken}; Max-Age=${accessMaxAge}; ${COOKIE_BASE}`,
    // Refresh token: httpOnly — never readable by JavaScript.
    `${REFRESH_TOKEN_COOKIE}=${refreshToken}; Max-Age=${refreshMaxAge}; HttpOnly; ${COOKIE_BASE}`,
  ];
}

export function buildClearCookieHeaders(): string[] {
  return [
    `${ACCESS_TOKEN_COOKIE}=; Max-Age=0; ${COOKIE_BASE}`,
    `${REFRESH_TOKEN_COOKIE}=; Max-Age=0; HttpOnly; ${COOKIE_BASE}`,
  ];
}

// Server-side: read from a NextRequest (middleware or route handler).
export function getAccessTokenFromRequest(req: NextRequest): string | undefined {
  return req.cookies.get(ACCESS_TOKEN_COOKIE)?.value;
}

export function getRefreshTokenFromRequest(req: NextRequest): string | undefined {
  return req.cookies.get(REFRESH_TOKEN_COOKIE)?.value;
}

// Client-side: read access token from document.cookie.
// The access token cookie is intentionally non-httpOnly so the api-client
// can read it and forward it to the FastAPI backend.
export function getAccessToken(): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${ACCESS_TOKEN_COOKIE}=([^;]+)`),
  );
  return match?.[1];
}
