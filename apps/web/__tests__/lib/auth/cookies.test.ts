import { describe, it, expect, vi, afterEach } from "vitest";

// Mock jose before importing the module under test.
vi.mock("jose", () => ({
  decodeJwt: vi.fn(),
}));

import { decodeJwt } from "jose";
import { getPracticeId } from "@/lib/auth/cookies";

const mockDecodeJwt = vi.mocked(decodeJwt);

const TOKEN_COOKIE_NAME = "dental-access-token";

function stubCookie(value: string | undefined) {
  const cookie = value ? `${TOKEN_COOKIE_NAME}=${value}` : "";
  vi.stubGlobal("document", { cookie });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getPracticeId", () => {
  it("returns the practice ID from the JWT payload", () => {
    stubCookie("header.payload.sig");
    mockDecodeJwt.mockReturnValue({ "custom:practice_id": "practice-abc-123" } as ReturnType<typeof decodeJwt>);

    expect(getPracticeId()).toBe("practice-abc-123");
    expect(mockDecodeJwt).toHaveBeenCalledWith("header.payload.sig");
  });

  it("returns undefined when the access token cookie is absent", () => {
    stubCookie(undefined);

    expect(getPracticeId()).toBeUndefined();
    expect(mockDecodeJwt).not.toHaveBeenCalled();
  });

  it("returns undefined when the JWT payload has no custom:practice_id", () => {
    stubCookie("header.payload.sig");
    mockDecodeJwt.mockReturnValue({ sub: "user-123" } as ReturnType<typeof decodeJwt>);

    expect(getPracticeId()).toBeUndefined();
  });

  it("returns undefined when decodeJwt throws (malformed token)", () => {
    stubCookie("not-a-jwt");
    mockDecodeJwt.mockImplementation(() => {
      throw new Error("Invalid JWT");
    });

    expect(getPracticeId()).toBeUndefined();
  });

  it("returns undefined when document is not defined (server-side context)", () => {
    // Simulate SSR by removing the document global.
    vi.stubGlobal("document", undefined);

    expect(getPracticeId()).toBeUndefined();
    expect(mockDecodeJwt).not.toHaveBeenCalled();
  });
});
