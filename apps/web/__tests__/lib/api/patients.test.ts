import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  generateId: () => "test-uuid-idempotency",
  ApiError: class ApiError extends Error {
    constructor(
      public readonly status: number,
      public readonly body: unknown,
    ) {
      super(`API error ${status}`);
      this.name = "ApiError";
    }
  },
}));

import { apiClient, ApiError } from "@/lib/api-client";
import {
  listPatients,
  getPatient,
  createPatient,
  updatePatient,
  isNotFoundError,
  type Patient,
  type PatientListResponse,
} from "@/lib/api/patients";

const mockGet = vi.mocked(apiClient.get);
const mockPost = vi.mocked(apiClient.post);
const mockPatch = vi.mocked(apiClient.patch);

const PATIENT: Patient = {
  id: "patient-uuid-1",
  practiceId: "practice-uuid-1",
  firstName: "Jane",
  lastName: "Smith",
  dateOfBirth: "1990-03-15",
  sex: "female",
  maritalStatus: null,
  phone: "555-867-5309",
  email: "jane@example.com",
  addressLine1: "123 Main St",
  addressLine2: null,
  city: "Boston",
  state: "MA",
  zip: "02101",
  ssn: null,
  emergencyContactName: null,
  emergencyContactPhone: null,
  occupation: null,
  employer: null,
  referralSource: null,
  lastXrayDate: null,
  allergies: ["Penicillin"],
  medicalAlerts: [],
  medications: [],
  dentalSymptoms: [],
  lastDentalVisit: null,
  previousDentist: null,
  doctorNotes: null,
  smsOptOut: false,
  deletedAt: null,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
};

beforeEach(() => {
  vi.stubGlobal("crypto", { randomUUID: vi.fn().mockReturnValue("test-uuid-idempotency") });
});

describe("listPatients", () => {
  it("calls GET /api/v1/patients with no query string when params are empty", async () => {
    const response: PatientListResponse = {
      data: [PATIENT],
      meta: { page: 1, pageSize: 20, total: 1, totalPages: 1 },
    };
    mockGet.mockResolvedValue(response);

    const result = await listPatients();

    expect(mockGet).toHaveBeenCalledWith("/api/v1/patients");
    expect(result).toEqual(response);
  });

  it("includes q param when search term is provided", async () => {
    mockGet.mockResolvedValue({ data: [], meta: { page: 1, pageSize: 20, total: 0, totalPages: 1 } });

    await listPatients({ q: "Smith" });

    expect(mockGet).toHaveBeenCalledWith("/api/v1/patients?q=Smith");
  });

  it("includes page and page_size params", async () => {
    mockGet.mockResolvedValue({ data: [], meta: { page: 2, pageSize: 10, total: 50, totalPages: 5 } });

    await listPatients({ page: 2, pageSize: 10 });

    expect(mockGet).toHaveBeenCalledWith("/api/v1/patients?page=2&page_size=10");
  });

  it("includes all params when all are provided", async () => {
    mockGet.mockResolvedValue({ data: [], meta: { page: 3, pageSize: 5, total: 30, totalPages: 6 } });

    await listPatients({ q: "Jane", page: 3, pageSize: 5 });

    expect(mockGet).toHaveBeenCalledWith("/api/v1/patients?q=Jane&page=3&page_size=5");
  });
});

describe("getPatient", () => {
  it("calls GET /api/v1/patients/:id", async () => {
    mockGet.mockResolvedValue(PATIENT);

    const result = await getPatient("patient-uuid-1");

    expect(mockGet).toHaveBeenCalledWith("/api/v1/patients/patient-uuid-1");
    expect(result).toEqual(PATIENT);
  });
});

describe("createPatient", () => {
  it("calls POST /api/v1/patients with the body", async () => {
    mockPost.mockResolvedValue(PATIENT);

    const body = {
      firstName: "Jane",
      lastName: "Smith",
      dateOfBirth: "1990-03-15",
    };

    await createPatient(body);

    expect(mockPost).toHaveBeenCalledWith(
      "/api/v1/patients",
      body,
      expect.objectContaining({ idempotencyKey: expect.any(String) }),
    );
  });

  it("generates a UUID idempotency key on each call", async () => {
    mockPost.mockResolvedValue(PATIENT);

    await createPatient({ firstName: "Jane", lastName: "Smith", dateOfBirth: "1990-03-15" });

    const [, , options] = mockPost.mock.calls[0]!;
    expect((options as { idempotencyKey: string }).idempotencyKey).toBe("test-uuid-idempotency");
  });
});

describe("updatePatient", () => {
  it("calls PATCH /api/v1/patients/:id with the body", async () => {
    const updated = { ...PATIENT, firstName: "Janet" };
    mockPatch.mockResolvedValue(updated);

    const result = await updatePatient("patient-uuid-1", { firstName: "Janet" });

    expect(mockPatch).toHaveBeenCalledWith(
      "/api/v1/patients/patient-uuid-1",
      { firstName: "Janet" },
      expect.objectContaining({ idempotencyKey: expect.any(String) }),
    );
    expect(result.firstName).toBe("Janet");
  });

  it("generates a UUID idempotency key on each call", async () => {
    mockPatch.mockResolvedValue(PATIENT);

    await updatePatient("patient-uuid-1", { phone: "555-0000" });

    const [, , options] = mockPatch.mock.calls[0]!;
    expect((options as { idempotencyKey: string }).idempotencyKey).toBe("test-uuid-idempotency");
  });
});

describe("isNotFoundError", () => {
  it("returns true for a 404 ApiError", () => {
    const err = new ApiError(404, { error: { code: "NOT_FOUND" } });
    expect(isNotFoundError(err)).toBe(true);
  });

  it("returns false for a 403 ApiError", () => {
    const err = new ApiError(403, { error: { code: "FORBIDDEN" } });
    expect(isNotFoundError(err)).toBe(false);
  });

  it("returns false for a plain Error", () => {
    expect(isNotFoundError(new Error("network error"))).toBe(false);
  });

  it("returns false for non-error values", () => {
    expect(isNotFoundError(null)).toBe(false);
    expect(isNotFoundError("string")).toBe(false);
    expect(isNotFoundError(404)).toBe(false);
  });
});
