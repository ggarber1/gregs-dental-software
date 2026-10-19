import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("aws-amplify/auth", () => ({
  fetchAuthSession: vi.fn(),
  signOut: vi.fn(),
}));

import { fetchAuthSession, signOut } from "aws-amplify/auth";
import {
  REFRESH_LEAD_MS,
  clearSession,
  loginUrl,
  msUntilRefresh,
  refreshSession,
  safeNextPath,
} from "@/lib/auth/clientSession";

const mockFetchAuthSession = vi.mocked(fetchAuthSession);
const mockSignOut = vi.mocked(signOut);

function unsignedJwt(payload: Record<string, unknown>): string {
  const enc = (o: unknown) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${enc({ alg: "none" })}.${enc(payload)}.sig`;
}

function sessionWith(idToken: string | undefined) {
  return {
    tokens: idToken ? { idToken: { toString: () => idToken } } : undefined,
  } as unknown as Awaited<ReturnType<typeof fetchAuthSession>>;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 200 })));
  vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("msUntilRefresh", () => {
  const now = 1_700_000_000_000;

  it("schedules the refresh REFRESH_LEAD_MS before expiry", () => {
    const token = unsignedJwt({ exp: (now + 60 * 60 * 1000) / 1000 });
    expect(msUntilRefresh(token, now)).toBe(60 * 60 * 1000 - REFRESH_LEAD_MS);
  });

  it("returns 0 for an already-expired token", () => {
    const token = unsignedJwt({ exp: (now - 1000) / 1000 });
    expect(msUntilRefresh(token, now)).toBe(0);
  });

  it("returns 0 for a missing or malformed token", () => {
    expect(msUntilRefresh(undefined, now)).toBe(0);
    expect(msUntilRefresh("not-a-jwt", now)).toBe(0);
    expect(msUntilRefresh(unsignedJwt({}), now)).toBe(0);
  });
});

describe("refreshSession", () => {
  it("stores the fresh ID token in the session cookie", async () => {
    mockFetchAuthSession.mockResolvedValue(sessionWith("new-id-token"));

    await expect(refreshSession()).resolves.toBe(true);

    expect(mockFetchAuthSession).toHaveBeenCalledWith({ forceRefresh: true });
    const [url, init] = vi.mocked(fetch).mock.calls[0]!;
    expect(url).toBe("/auth/session");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ accessToken: "new-id-token" });
  });

  it("shares one refresh between concurrent callers", async () => {
    mockFetchAuthSession.mockResolvedValue(sessionWith("new-id-token"));

    const [a, b] = await Promise.all([refreshSession(), refreshSession()]);

    expect([a, b]).toEqual([true, true]);
    expect(mockFetchAuthSession).toHaveBeenCalledTimes(1);
  });

  it("returns false and stores nothing when the session is gone", async () => {
    mockFetchAuthSession.mockResolvedValue(sessionWith(undefined));

    await expect(refreshSession()).resolves.toBe(false);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("returns false when Amplify throws", async () => {
    mockFetchAuthSession.mockRejectedValue(new Error("NotAuthorizedException"));

    await expect(refreshSession()).resolves.toBe(false);
  });

  it("returns false when the cookie route fails", async () => {
    mockFetchAuthSession.mockResolvedValue(sessionWith("new-id-token"));
    vi.mocked(fetch).mockResolvedValue(new Response("{}", { status: 500 }));

    await expect(refreshSession()).resolves.toBe(false);
  });
});

describe("clearSession", () => {
  it("clears the session cookies via the /auth/session route", async () => {
    await clearSession();

    expect(mockSignOut).toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledWith("/auth/session", { method: "DELETE" });
  });

  it("still clears the cookies when Amplify sign-out fails", async () => {
    mockSignOut.mockRejectedValue(new Error("network"));

    await clearSession();

    expect(fetch).toHaveBeenCalledWith("/auth/session", { method: "DELETE" });
  });
});

describe("safeNextPath", () => {
  it.each(["/schedule", "/patients/123?tab=ledger", "/billing/patient-aging"])(
    "accepts in-app path %s",
    (path) => {
      expect(safeNextPath(path)).toBe(path);
    },
  );

  it.each([null, undefined, "", "//evil.com", "/\\evil.com", "https://evil.com", "javascript:alert(1)"])(
    "falls back to /dashboard for %s",
    (path) => {
      expect(safeNextPath(path)).toBe("/dashboard");
    },
  );
});

describe("loginUrl", () => {
  it("encodes the return path", () => {
    expect(loginUrl("/schedule?date=2026-10-19")).toBe(
      "/login?next=%2Fschedule%3Fdate%3D2026-10-19",
    );
  });
});
