import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  generateId: () => "test-uuid-idempotency",
}));

import { apiClient } from "@/lib/api-client";
import { listPatientInsurance, createInsurance, updateInsurance, deleteInsurance } from "@/lib/api/insurance";

const mockGet = vi.mocked(apiClient.get);
const mockPost = vi.mocked(apiClient.post);
const mockPatch = vi.mocked(apiClient.patch);
const mockDelete = vi.mocked(apiClient.delete);

beforeEach(() => {
  vi.stubGlobal("crypto", { randomUUID: vi.fn().mockReturnValue("test-uuid-idempotency") });
});

describe("listPatientInsurance", () => {
  it("calls GET /api/v1/patients/:patientId/insurance", async () => {
    mockGet.mockResolvedValue([]);

    await listPatientInsurance("patient-1");

    expect(mockGet).toHaveBeenCalledWith("/api/v1/patients/patient-1/insurance");
  });
});

describe("createInsurance", () => {
  it("calls POST with body and an idempotency key", async () => {
    mockPost.mockResolvedValue({});

    const body = { carrier: "Delta Dental", priority: "primary" as const };
    await createInsurance("patient-1", body);

    expect(mockPost).toHaveBeenCalledWith(
      "/api/v1/patients/patient-1/insurance",
      body,
      expect.objectContaining({ idempotencyKey: expect.any(String) }),
    );
  });
});

describe("updateInsurance", () => {
  it("calls PATCH with body and an idempotency key", async () => {
    mockPatch.mockResolvedValue({});

    await updateInsurance("patient-1", "ins-1", { carrier: "Cigna" });

    expect(mockPatch).toHaveBeenCalledWith(
      "/api/v1/patients/patient-1/insurance/ins-1",
      { carrier: "Cigna" },
      expect.objectContaining({ idempotencyKey: expect.any(String) }),
    );
  });
});

describe("deleteInsurance", () => {
  it("calls DELETE /api/v1/patients/:patientId/insurance/:insuranceId", async () => {
    mockDelete.mockResolvedValue(undefined);

    await deleteInsurance("patient-1", "ins-1");

    expect(mockDelete).toHaveBeenCalledWith(
      "/api/v1/patients/patient-1/insurance/ins-1",
      expect.objectContaining({ idempotencyKey: expect.any(String) }),
    );
  });

  it("sends an idempotency key", async () => {
    mockDelete.mockResolvedValue(undefined);

    await deleteInsurance("patient-1", "ins-1");

    const [, options] = mockDelete.mock.calls[0]!;
    expect((options as { idempotencyKey: string }).idempotencyKey).toBe("test-uuid-idempotency");
  });
});
