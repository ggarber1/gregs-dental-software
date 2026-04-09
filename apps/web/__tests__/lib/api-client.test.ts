import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock the cookies module before importing api-client.
vi.mock("@/lib/auth/cookies", () => ({
  getAccessToken: vi.fn(),
  getPracticeId: vi.fn(),
}));

import { getAccessToken, getPracticeId } from "@/lib/auth/cookies";
import { apiClient, ApiError } from "@/lib/api-client";

const mockGetAccessToken = vi.mocked(getAccessToken);
const mockGetPracticeId = vi.mocked(getPracticeId);

const API_BASE = "http://localhost:8000";

function mockFetch(status: number, body: unknown) {
  const response = new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiClient — auth header", () => {
  beforeEach(() => {
    mockGetPracticeId.mockReturnValue(undefined);
  });

  it("attaches Authorization header when access token is present", async () => {
    mockGetAccessToken.mockReturnValue("my-cognito-token");
    mockFetch(200, { data: "ok" });

    await apiClient.get("/patients");

    const [, init] = vi.mocked(fetch).mock.calls[0]!;
    const headers = init?.headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer my-cognito-token");
  });

  it("omits Authorization header when no token is present", async () => {
    mockGetAccessToken.mockReturnValue(undefined);
    mockFetch(200, {});

    await apiClient.get("/patients");

    const [, init] = vi.mocked(fetch).mock.calls[0]!;
    const headers = init?.headers as Record<string, string>;
    expect(headers["Authorization"]).toBeUndefined();
  });
});

describe("apiClient — X-Practice-ID header", () => {
  beforeEach(() => {
    mockGetAccessToken.mockReturnValue(undefined);
  });

  it("attaches X-Practice-ID header when practice ID is present", async () => {
    mockGetPracticeId.mockReturnValue("practice-uuid-123");
    mockFetch(200, {});

    await apiClient.get("/api/v1/patients");

    const [, init] = vi.mocked(fetch).mock.calls[0]!;
    const headers = init?.headers as Record<string, string>;
    expect(headers["X-Practice-ID"]).toBe("practice-uuid-123");
  });

  it("omits X-Practice-ID header when practice ID is absent", async () => {
    mockGetPracticeId.mockReturnValue(undefined);
    mockFetch(200, {});

    await apiClient.get("/api/v1/patients");

    const [, init] = vi.mocked(fetch).mock.calls[0]!;
    const headers = init?.headers as Record<string, string>;
    expect(headers["X-Practice-ID"]).toBeUndefined();
  });
});

describe("apiClient — idempotency key", () => {
  beforeEach(() => {
    mockGetAccessToken.mockReturnValue(undefined);
    mockGetPracticeId.mockReturnValue(undefined);
  });

  it("attaches Idempotency-Key header when provided", async () => {
    mockFetch(200, {});

    await apiClient.post("/appointments", {}, { idempotencyKey: "key-abc" });

    const [, init] = vi.mocked(fetch).mock.calls[0]!;
    const headers = init?.headers as Record<string, string>;
    expect(headers["Idempotency-Key"]).toBe("key-abc");
  });

  it("omits Idempotency-Key when not provided", async () => {
    mockFetch(200, {});

    await apiClient.post("/appointments", {});

    const [, init] = vi.mocked(fetch).mock.calls[0]!;
    const headers = init?.headers as Record<string, string>;
    expect(headers["Idempotency-Key"]).toBeUndefined();
  });
});

describe("apiClient — HTTP methods and URL", () => {
  beforeEach(() => {
    mockGetAccessToken.mockReturnValue(undefined);
    mockGetPracticeId.mockReturnValue(undefined);
  });

  it("GET calls correct URL with GET method", async () => {
    mockFetch(200, { id: 1 });

    await apiClient.get("/patients/1");

    const [url, init] = vi.mocked(fetch).mock.calls[0]!;
    expect(url).toBe(`${API_BASE}/patients/1`);
    expect(init?.method).toBe("GET");
  });

  it("POST serialises body as JSON", async () => {
    mockFetch(201, { id: 2 });

    await apiClient.post("/patients", { firstName: "Jane" });

    const [, init] = vi.mocked(fetch).mock.calls[0]!;
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ firstName: "Jane" }));
  });

  it("PATCH serialises body as JSON", async () => {
    mockFetch(200, { id: 1 });

    await apiClient.patch("/patients/1", { firstName: "Jane" });

    const [, init] = vi.mocked(fetch).mock.calls[0]!;
    expect(init?.method).toBe("PATCH");
    expect(init?.body).toBe(JSON.stringify({ firstName: "Jane" }));
  });

  it("DELETE calls correct URL with DELETE method", async () => {
    mockFetch(200, {});

    await apiClient.delete("/patients/1");

    const [url, init] = vi.mocked(fetch).mock.calls[0]!;
    expect(url).toBe(`${API_BASE}/patients/1`);
    expect(init?.method).toBe("DELETE");
  });
});

describe("apiClient — error handling", () => {
  beforeEach(() => {
    mockGetAccessToken.mockReturnValue(undefined);
    mockGetPracticeId.mockReturnValue(undefined);
  });

  it("throws ApiError with status and body on 4xx response", async () => {
    const errorBody = { error: { code: "NOT_FOUND", message: "Patient not found" } };
    mockFetch(404, errorBody);

    const error = await apiClient.get("/patients/999").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(404);
    expect((error as ApiError).body).toEqual(errorBody);
  });

  it("throws ApiError on 500 response", async () => {
    mockFetch(500, { error: { code: "INTERNAL", message: "Server error" } });

    await expect(apiClient.get("/patients")).rejects.toThrow(ApiError);
  });

  it("returns parsed JSON on 200 success", async () => {
    const data = { id: "abc", firstName: "Jane" };
    mockFetch(200, data);

    const result = await apiClient.get<typeof data>("/patients/abc");
    expect(result).toEqual(data);
  });
});
