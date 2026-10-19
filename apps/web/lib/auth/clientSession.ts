/**
 * Client-side session lifecycle (browser only; server reads live in ./session.ts).
 *
 * The API authenticates with the Cognito ID token stored in the
 * dental-access-token cookie (1h). Amplify keeps the refresh token (30 days) and
 * can mint a new ID token; these helpers copy fresh tokens into the cookie so
 * staff aren't logged out every hour.
 */
import { decodeJwt } from "jose";

/** Refresh this long before the token expires. */
export const REFRESH_LEAD_MS = 5 * 60 * 1000;

const DEFAULT_AFTER_LOGIN = "/dashboard";

/** Milliseconds until the token should be refreshed; 0 = refresh now. */
export function msUntilRefresh(token: string | undefined, nowMs: number): number {
  if (!token) return 0;
  try {
    const { exp } = decodeJwt(token);
    if (typeof exp !== "number") return 0;
    return Math.max(0, exp * 1000 - REFRESH_LEAD_MS - nowMs);
  } catch {
    return 0;
  }
}

/** Store an ID token in the session cookie via the /auth/session route. */
export async function saveSessionCookie(idToken: string): Promise<boolean> {
  const res = await fetch("/auth/session", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ accessToken: idToken }),
  });
  return res.ok;
}

let inFlight: Promise<boolean> | null = null;

/**
 * Get a fresh ID token from Amplify and store it in the cookie.
 * Concurrent callers share one refresh. Resolves false when the session is gone
 * (refresh token expired or revoked) — the caller should send the user to login.
 */
export function refreshSession(): Promise<boolean> {
  inFlight ??= doRefresh().finally(() => {
    inFlight = null;
  });
  return inFlight;
}

async function doRefresh(): Promise<boolean> {
  try {
    const { fetchAuthSession } = await import("aws-amplify/auth");
    const session = await fetchAuthSession({ forceRefresh: true });
    const idToken = session.tokens?.idToken?.toString();
    if (!idToken) return false;
    return await saveSessionCookie(idToken);
  } catch (err) {
    console.warn("[session] refresh failed:", err instanceof Error ? err.name : "unknown");
    return false;
  }
}

/** Sign out of Amplify (best effort) and clear the session cookies. */
export async function clearSession(): Promise<void> {
  try {
    const { signOut } = await import("aws-amplify/auth");
    await signOut();
  } catch {
    // Amplify sign-out failures are non-fatal — the cookies still get cleared.
  }
  await fetch("/auth/session", { method: "DELETE" });
}

/** Only same-app paths may be used as a post-login destination (no open redirect). */
export function safeNextPath(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return DEFAULT_AFTER_LOGIN;
  }
  return next;
}

/** Login URL that returns the user to `currentPath` afterwards. */
export function loginUrl(currentPath: string): string {
  return `/login?next=${encodeURIComponent(currentPath)}`;
}
