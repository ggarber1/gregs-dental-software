import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock the cookies module before importing api-client.
vi.mock("@/lib/auth/cookies", () => ({
  getAccessToken: vi.fn(),
  getPracticeId: vi.fn(),
}));
vi.mock("@/lib/auth/clientSession", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/auth/clientSession")>()),
  refreshSession: vi.fn(),
}));

import { getAccessToken, getPracticeId } from "@/lib/auth/cookies";
import { refreshSession } from "@/lib/auth/clientSession";
import { apiClient, ApiError, apiErrorMessage } from "@/lib/api-client";

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

describe("apiClient.getBlob", () => {
  beforeEach(() => {
    mockGetAccessToken.mockReturnValue("tok-123");
    mockGetPracticeId.mockReturnValue("practice-1");
  });

  it("sends auth headers without a JSON content-type and returns a Blob", async () => {
    const bytes = new Uint8Array([0x25, 0x50, 0x44, 0x46]); // %PDF
    const response = new Response(bytes, {
      status: 200,
      headers: { "Content-Type": "application/pdf" },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    const blob = await apiClient.getBlob("/api/v1/patients/p1/statements/preview");

    expect(blob.type).toBe("application/pdf");
    expect(blob.size).toBe(4);
    const [url, init] = vi.mocked(fetch).mock.calls[0]!;
    expect(url).toBe(`${API_BASE}/api/v1/patients/p1/statements/preview`);
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers["Authorization"]).toBe("Bearer tok-123");
    expect(headers["X-Practice-ID"]).toBe("practice-1");
    expect(headers["Content-Type"]).toBeUndefined();
  });

  it("throws ApiError with the JSON error body on failure", async () => {
    mockFetch(400, { error: { code: "NO_OUTSTANDING_BALANCE", message: "No outstanding balance." } });

    await expect(apiClient.getBlob("/api/v1/x")).rejects.toMatchObject({
      status: 400,
      body: { error: { code: "NO_OUTSTANDING_BALANCE" } },
    });
  });
});

describe("apiErrorMessage", () => {
  it("uses the API error body message for ApiError", () => {
    const err = new ApiError(400, { error: { code: "X", message: "No outstanding balance." } });
    expect(apiErrorMessage(err)).toBe("No outstanding balance.");
  });

  it("falls back to the status when the ApiError body has no message", () => {
    expect(apiErrorMessage(new ApiError(502, null))).toBe("Unexpected error (502)");
  });

  it("uses the message of a plain Error", () => {
    expect(apiErrorMessage(new Error("PDF could not be downloaded."))).toBe(
      "PDF could not be downloaded.",
    );
  });

  it("uses a generic message for non-Error values", () => {
    expect(apiErrorMessage("boom")).toBe("Something went wrong. Please try again.");
  });
});

describe("apiClient — expired session (401)", () => {
  const mockRefresh = vi.mocked(refreshSession);
  let location: { href: string; pathname: string; search: string };

  function respond(...statuses: number[]) {
    const fetchMock = vi.fn<typeof fetch>();
    for (const status of statuses) {
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: status }), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  beforeEach(() => {
    location = { href: "", pathname: "/schedule", search: "?date=2026-10-19" };
    vi.stubGlobal("window", { location });
    mockGetPracticeId.mockReturnValue(undefined);
    mockGetAccessToken.mockReturnValueOnce("expired-token").mockReturnValue("fresh-token");
    mockRefresh.mockReset();
  });

  it("refreshes once and retries the request with the new token", async () => {
    mockRefresh.mockResolvedValue(true);
    const fetchMock = respond(401, 200);

    await expect(apiClient.get("/patients")).resolves.toEqual({ ok: 200 });

    expect(mockRefresh).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const retryHeaders = fetchMock.mock.calls[1]![1]?.headers as Record<string, string>;
    expect(retryHeaders["Authorization"]).toBe("Bearer fresh-token");
    expect(location.href).toBe("");
  });

  it("reuses the idempotency key on the retried mutation", async () => {
    mockRefresh.mockResolvedValue(true);
    const fetchMock = respond(401, 201);

    await apiClient.post("/patients", { firstName: "A" }, { idempotencyKey: "key-1" });

    const keys = fetchMock.mock.calls.map(
      ([, init]) => (init?.headers as Record<string, string>)["Idempotency-Key"],
    );
    expect(keys).toEqual(["key-1", "key-1"]);
  });

  it("sends the user to login with a return path when the retry is still 401", async () => {
    mockRefresh.mockResolvedValue(true);
    const fetchMock = respond(401, 401);

    await apiClient.get("/patients");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(location.href).toBe("/login?next=%2Fschedule%3Fdate%3D2026-10-19");
  });

  it("does not retry when the refresh fails", async () => {
    mockRefresh.mockResolvedValue(false);
    const fetchMock = respond(401);

    await apiClient.get("/patients");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(location.href).toBe("/login?next=%2Fschedule%3Fdate%3D2026-10-19");
  });

  it("leaves non-401 errors alone", async () => {
    respond(403);

    await expect(apiClient.get("/patients")).rejects.toBeInstanceOf(ApiError);
    expect(mockRefresh).not.toHaveBeenCalled();
  });

  it("retries blob downloads the same way", async () => {
    mockRefresh.mockResolvedValue(true);
    const fetchMock = respond(401, 200);

    await apiClient.getBlob("/statements/1/pdf");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(location.href).toBe("");
  });
});
