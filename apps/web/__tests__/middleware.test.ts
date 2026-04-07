import { NextRequest, NextResponse } from "next/server";
import { describe, it, expect, vi } from "vitest";
import type { CognitoJwtPayload } from "@/lib/auth/jwks";

// Mock the JWKS validator — we test routing logic, not JWT crypto.
vi.mock("@/lib/auth/jwks", () => ({
  validateAccessToken: vi.fn(),
}));

import { validateAccessToken } from "@/lib/auth/jwks";
import { middleware } from "@/middleware";

const mockValidate = vi.mocked(validateAccessToken);

const ORIGIN = "http://localhost:3000";
const MOCK_PAYLOAD: CognitoJwtPayload = {
  sub: "user-123",
  email: "dentist@example.com",
  token_use: "access",
  iss: `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TEST`,
  exp: Math.floor(Date.now() / 1000) + 3600,
};

function makeReq(pathname: string, accessToken?: string): NextRequest {
  const req = new NextRequest(`${ORIGIN}${pathname}`);
  if (accessToken) {
    req.cookies.set("dental-access-token", accessToken);
  }
  return req;
}

describe("middleware — route protection", () => {
  describe("unauthenticated user (no token)", () => {
    it("redirects /dashboard to /login", async () => {
      mockValidate.mockResolvedValue(null);
      const res = await middleware(makeReq("/dashboard"));
      expect(res.status).toBe(307);
      expect(res.headers.get("location")).toBe(`${ORIGIN}/login`);
    });

    it("redirects /patients/123 to /login", async () => {
      mockValidate.mockResolvedValue(null);
      const res = await middleware(makeReq("/patients/123"));
      expect(res.status).toBe(307);
      expect(res.headers.get("location")).toBe(`${ORIGIN}/login`);
    });

    it("redirects /billing to /login", async () => {
      mockValidate.mockResolvedValue(null);
      const res = await middleware(makeReq("/billing"));
      expect(res.status).toBe(307);
      expect(res.headers.get("location")).toBe(`${ORIGIN}/login`);
    });

    it("passes through /login", async () => {
      mockValidate.mockResolvedValue(null);
      const res = await middleware(makeReq("/login"));
      expect(res.status).toBe(200);
      expect(res.headers.get("location")).toBeNull();
    });
  });

  describe("authenticated user (valid token)", () => {
    it("redirects /login to /dashboard", async () => {
      mockValidate.mockResolvedValue(MOCK_PAYLOAD);
      const res = await middleware(makeReq("/login", "valid-token"));
      expect(res.status).toBe(307);
      expect(res.headers.get("location")).toBe(`${ORIGIN}/dashboard`);
    });

    it("passes through /dashboard", async () => {
      mockValidate.mockResolvedValue(MOCK_PAYLOAD);
      const res = await middleware(makeReq("/dashboard", "valid-token"));
      expect(res.status).toBe(200);
      expect(res.headers.get("location")).toBeNull();
    });

    it("passes through /patients", async () => {
      mockValidate.mockResolvedValue(MOCK_PAYLOAD);
      const res = await middleware(makeReq("/patients", "valid-token"));
      expect(res.status).toBe(200);
      expect(res.headers.get("location")).toBeNull();
    });
  });
});
