/**
 * Typed API client for the FastAPI backend.
 *
 * All requests are authenticated via Cognito JWT (added in 1.5).
 * Idempotency-Key header is required on all mutation methods.
 */

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
