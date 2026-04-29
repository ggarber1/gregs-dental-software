/**
 * Typed API client for the FastAPI backend.
 *
 * Reads the Cognito access token from the dental-access-token cookie and
 * forwards it as Authorization: Bearer <token> on every request. The FastAPI
 * middleware validates this token against Cognito JWKS and reads
 * custom:practice_id and cognito:groups from its claims.
 *
 * Idempotency-Key header is required on all mutation methods (POST/PATCH/DELETE).
 */

import { getAccessToken, getPracticeId } from "@/lib/auth/cookies";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Generate a UUID for idempotency keys.
 * crypto.randomUUID() requires a secure context (HTTPS); fall back to
 * Math.random()-based generation on plain HTTP (staging without TLS).
 */
export function generateId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // RFC 4122 v4 fallback
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

type HttpMethod = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

interface RequestOptions {
  idempotencyKey?: string;
  signal?: AbortSignal;
}

async function request<T>(
  method: HttpMethod,
  path: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  const token = getAccessToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const practiceId = getPracticeId();
  if (practiceId) {
    headers["X-Practice-ID"] = practiceId;
  }

  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    ...(body !== undefined && { body: JSON.stringify(body) }),
    ...(options.signal !== undefined && { signal: options.signal }),
  });

  if (!response.ok) {
    if (response.status === 401 && typeof window !== "undefined") {
      window.location.href = "/login";
      return undefined as T;
    }
    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
    const errorBody: unknown = await response
      .json()
      .catch(() => ({ error: { code: "UNKNOWN", message: response.statusText } }));
    throw new ApiError(response.status, errorBody);
  }

  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(`API error ${status}`);
    this.name = "ApiError";
  }
}

export const apiClient = {
  get: <T>(path: string, options?: RequestOptions) =>
    request<T>("GET", path, undefined, options),

  post: <T>(path: string, body: unknown, options?: RequestOptions) =>
    request<T>("POST", path, body, options),

  patch: <T>(path: string, body: unknown, options?: RequestOptions) =>
    request<T>("PATCH", path, body, options),

  put: <T>(path: string, body: unknown, options?: RequestOptions) =>
    request<T>("PUT", path, body, options),

  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>("DELETE", path, undefined, options),
};
