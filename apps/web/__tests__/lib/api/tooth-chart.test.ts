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

import { apiClient } from "@/lib/api-client";
import {
  getToothChart,
  addToothCondition,
  updateToothCondition,
  deleteToothCondition,
  type ToothCondition,
  type ToothChartResponse,
} from "@/lib/api/tooth-chart";

const mockGet = vi.mocked(apiClient.get);
const mockPost = vi.mocked(apiClient.post);
const mockPatch = vi.mocked(apiClient.patch);
const mockDelete = vi.mocked(apiClient.delete);

const PATIENT_ID = "patient-uuid-1";
const CONDITION_ID = "condition-uuid-1";
const PROVIDER_ID = "provider-uuid-1";

const CONDITION: ToothCondition = {
  id: CONDITION_ID,
  practiceId: "practice-uuid-1",
  patientId: PATIENT_ID,
  toothNumber: "14",
  notationSystem: "universal",
  conditionType: "crown",
  surface: null,
  material: "zirconia",
  notes: null,
  status: "existing",
  recordedAt: "2026-05-04",
  recordedBy: PROVIDER_ID,
  appointmentId: null,
  createdAt: "2026-05-04T12:00:00Z",
  updatedAt: "2026-05-04T12:00:00Z",
};

const CHART_RESPONSE: ToothChartResponse = {
  conditions: [CONDITION],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getToothChart", () => {
  it("calls GET /api/v1/patients/:id/tooth-chart without asOfDate", async () => {
    mockGet.mockResolvedValue(CHART_RESPONSE);

    const result = await getToothChart(PATIENT_ID);

    expect(mockGet).toHaveBeenCalledWith(
      `/api/v1/patients/${PATIENT_ID}/tooth-chart`,
    );
    expect(result.conditions).toHaveLength(1);
    expect(result.conditions[0]?.toothNumber).toBe("14");
  });

  it("appends as_of_date query param when provided", async () => {
    mockGet.mockResolvedValue({ conditions: [] });

    await getToothChart(PATIENT_ID, "2025-01-01");

    expect(mockGet).toHaveBeenCalledWith(
      `/api/v1/patients/${PATIENT_ID}/tooth-chart?as_of_date=2025-01-01`,
    );
  });
});

describe("addToothCondition", () => {
  it("calls POST /api/v1/patients/:id/tooth-chart/conditions with idempotency key", async () => {
    mockPost.mockResolvedValue(CONDITION);

    const result = await addToothCondition(PATIENT_ID, {
      toothNumber: "14",
      conditionType: "crown",
      recordedAt: "2026-05-04",
      recordedBy: PROVIDER_ID,
    });

    expect(mockPost).toHaveBeenCalledWith(
      `/api/v1/patients/${PATIENT_ID}/tooth-chart/conditions`,
      expect.objectContaining({ toothNumber: "14", conditionType: "crown" }),
      { idempotencyKey: "test-uuid-idempotency" },
    );
    expect(result.id).toBe(CONDITION_ID);
  });
});

describe("updateToothCondition", () => {
  it("calls PATCH /api/v1/patients/:id/tooth-chart/conditions/:conditionId", async () => {
    const updated = { ...CONDITION, status: "treatment_planned" as const };
    mockPatch.mockResolvedValue(updated);

    const result = await updateToothCondition(PATIENT_ID, CONDITION_ID, {
      status: "treatment_planned",
    });

    expect(mockPatch).toHaveBeenCalledWith(
      `/api/v1/patients/${PATIENT_ID}/tooth-chart/conditions/${CONDITION_ID}`,
      { status: "treatment_planned" },
      { idempotencyKey: "test-uuid-idempotency" },
    );
    expect(result.status).toBe("treatment_planned");
  });
});

describe("deleteToothCondition", () => {
  it("calls DELETE /api/v1/patients/:id/tooth-chart/conditions/:conditionId", async () => {
    mockDelete.mockResolvedValue(undefined);

    await deleteToothCondition(PATIENT_ID, CONDITION_ID);

    expect(mockDelete).toHaveBeenCalledWith(
      `/api/v1/patients/${PATIENT_ID}/tooth-chart/conditions/${CONDITION_ID}`,
      { idempotencyKey: "test-uuid-idempotency" },
    );
  });
});
