/**
 * Typed helpers for making direct API calls from Playwright test setup.
 *
 * Reads the Cognito access token + practiceId from the saved storageState so
 * tests can create / inspect resources without going through the browser UI.
 */
import crypto from "crypto";
import fs from "fs";
import { AUTH_STATE_PATH } from "./paths";

interface AuthState {
  cookies: Array<{ name: string; value: string }>;
}

interface ApiHeaders {
  Authorization: string;
  "X-Practice-ID": string;
  "Content-Type": string;
}

function getApiHeaders(idempotencyKey?: string): ApiHeaders & Record<string, string> {
  const state: AuthState = JSON.parse(fs.readFileSync(AUTH_STATE_PATH, "utf-8"));
  const cookie = state.cookies.find((c) => c.name === "dental-access-token");
  if (!cookie) throw new Error("dental-access-token cookie not found in storageState");

  const token = cookie.value;
  const jwtPart = token.split(".")[1];
  if (!jwtPart) throw new Error("Malformed JWT in storageState");
  const payload = JSON.parse(
    Buffer.from(jwtPart, "base64url").toString("utf-8")
  ) as Record<string, unknown>;
  const practiceId = payload["custom:practice_id"] as string | undefined;
  if (!practiceId)
    throw new Error(
      "Practice ID not found: set custom:practice_id on the Cognito test user"
    );

  const headers: ApiHeaders & Record<string, string> = {
    Authorization: `Bearer ${token}`,
    "X-Practice-ID": practiceId,
    "Content-Type": "application/json",
  };
  if (idempotencyKey) {
    headers["Idempotency-Key"] = idempotencyKey;
  }
  return headers;
}

function apiUrl(path: string): string {
  const base = process.env.E2E_API_URL ?? "http://localhost:8000";
  return `${base}${path}`;
}

// ── Patient ───────────────────────────────────────────────────────────────────

export interface CreatePatientBody {
  firstName: string;
  lastName: string;
  phone?: string;
  email?: string;
  dateOfBirth?: string;
}

export interface PatientResult {
  id: string;
  firstName: string;
  lastName: string;
  phone: string | null;
  [key: string]: unknown;
}

export async function apiCreatePatient(body: CreatePatientBody): Promise<PatientResult> {
  const resp = await fetch(apiUrl("/api/v1/patients"), {
    method: "POST",
    headers: getApiHeaders(crypto.randomUUID()),
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`POST /api/v1/patients failed ${resp.status}: ${text}`);
  }
  return resp.json() as Promise<PatientResult>;
}

export async function apiDeletePatient(patientId: string): Promise<void> {
  const resp = await fetch(apiUrl(`/api/v1/patients/${patientId}`), {
    method: "DELETE",
    headers: getApiHeaders(crypto.randomUUID()),
  });
  // 404 is acceptable — patient may have already been cleaned up
  if (!resp.ok && resp.status !== 404) {
    const text = await resp.text();
    throw new Error(`DELETE /api/v1/patients/${patientId} failed ${resp.status}: ${text}`);
  }
}

// ── Intake forms ──────────────────────────────────────────────────────────────

export interface SendIntakeFormResult {
  intakeFormId: string;
  expiresAt: string;
  formUrl: string;
}

export interface IntakeFormSummary {
  id: string;
  patientId: string;
  status: string;
  expiresAt: string;
  createdAt: string;
  createdBy: string;
}

export async function apiSendIntakeForm(patientId: string): Promise<SendIntakeFormResult> {
  const resp = await fetch(apiUrl("/api/v1/intake/send"), {
    method: "POST",
    headers: getApiHeaders(crypto.randomUUID()),
    body: JSON.stringify({ patientId }),
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`POST /api/v1/intake/send failed ${resp.status}: ${body}`);
  }
  return resp.json() as Promise<SendIntakeFormResult>;
}

export async function apiListIntakeForms(patientId: string): Promise<IntakeFormSummary[]> {
  const resp = await fetch(apiUrl(`/api/v1/intake?patient_id=${patientId}`), {
    headers: getApiHeaders(),
  });
  if (!resp.ok) throw new Error(`GET /api/v1/intake failed ${resp.status}`);
  return resp.json() as Promise<IntakeFormSummary[]>;
}

// ── Scheduling ────────────────────────────────────────────────────────────────

export interface ProviderResult {
  id: string;
  firstName: string;
  lastName: string;
  isActive: boolean;
  [key: string]: unknown;
}

export interface OperatoryResult {
  id: string;
  name: string;
  isActive: boolean;
  [key: string]: unknown;
}

export async function apiListProviders(): Promise<ProviderResult[]> {
  const resp = await fetch(apiUrl("/api/v1/providers"), { headers: getApiHeaders() });
  if (!resp.ok) throw new Error(`GET /api/v1/providers failed ${resp.status}`);
  return resp.json() as Promise<ProviderResult[]>;
}

export async function apiListOperatories(): Promise<OperatoryResult[]> {
  const resp = await fetch(apiUrl("/api/v1/operatories"), { headers: getApiHeaders() });
  if (!resp.ok) throw new Error(`GET /api/v1/operatories failed ${resp.status}`);
  return resp.json() as Promise<OperatoryResult[]>;
}

export interface CreateAppointmentBody {
  patientId: string;
  providerId: string;
  operatoryId: string;
  startTime: string;
  endTime: string;
  appointmentTypeId?: string;
  notes?: string;
}

export interface AppointmentResult {
  id: string;
  startTime: string;
  endTime: string;
  [key: string]: unknown;
}

export async function apiCreateAppointment(
  body: CreateAppointmentBody
): Promise<AppointmentResult> {
  const resp = await fetch(apiUrl("/api/v1/appointments"), {
    method: "POST",
    headers: getApiHeaders(crypto.randomUUID()),
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`POST /api/v1/appointments failed ${resp.status}: ${text}`);
  }
  return resp.json() as Promise<AppointmentResult>;
}

export async function apiDeleteAppointment(appointmentId: string): Promise<void> {
  const resp = await fetch(apiUrl(`/api/v1/appointments/${appointmentId}`), {
    method: "DELETE",
    headers: getApiHeaders(crypto.randomUUID()),
  });
  if (!resp.ok && resp.status !== 404) {
    const text = await resp.text();
    throw new Error(`DELETE /api/v1/appointments/${appointmentId} failed ${resp.status}: ${text}`);
  }
}
