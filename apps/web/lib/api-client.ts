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
    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
    const errorBody: unknown = await response
      .json()
      .catch(() => ({ error: { code: "UNKNOWN", message: response.statusText } }));
    throw new ApiError(response.status, errorBody);
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

  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>("DELETE", path, undefined, options),
};
