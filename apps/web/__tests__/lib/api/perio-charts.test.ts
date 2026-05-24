import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
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
  listPerioCharts,
  getPerioChart,
  createPerioChart,
  deletePerioChart,
  comparePerioCharts,
  type PerioChartDetail,
  type PerioChartListResponse,
} from "@/lib/api/perio-charts";

const mockGet = vi.mocked(apiClient.get);
const mockPost = vi.mocked(apiClient.post);
const mockDelete = vi.mocked(apiClient.delete);

const PATIENT_ID = "patient-uuid-1";
const CHART_ID = "chart-uuid-1";
const CHART_B_ID = "chart-uuid-2";
const PROVIDER_ID = "provider-uuid-1";

const READING = {
  id: "reading-uuid-1",
  perioChartId: CHART_ID,
  toothNumber: "14",
  site: "b" as const,
  probingDepthMm: 3,
  recessionMm: 0,
  cal: 3,
  bleeding: false,
  suppuration: false,
  furcation: null,
  mobility: null,
  createdAt: "2026-05-05T10:00:00Z",
};

const CHART_DETAIL: PerioChartDetail = {
  id: CHART_ID,
  practiceId: "practice-uuid-1",
  patientId: PATIENT_ID,
  appointmentId: null,
  providerId: PROVIDER_ID,
  chartDate: "2026-05-05",
  notes: null,
  avgProbingDepthMm: 3.0,
  sitesGte4mm: 0,
  sitesGte6mm: 0,
  bleedingSiteCount: 0,
  createdAt: "2026-05-05T10:00:00Z",
  updatedAt: "2026-05-05T10:00:00Z",
  readings: [READING],
};

const LIST_RESPONSE: PerioChartListResponse = {
  items: [CHART_DETAIL],
  nextCursor: null,
  hasMore: false,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("listPerioCharts", () => {
  it("calls GET /api/v1/patients/:id/perio-charts without cursor", async () => {
    mockGet.mockResolvedValue(LIST_RESPONSE);

    const result = await listPerioCharts(PATIENT_ID);

    expect(mockGet).toHaveBeenCalledWith(`/api/v1/patients/${PATIENT_ID}/perio-charts`);
    expect(result.items).toHaveLength(1);
    expect(result.items[0]?.id).toBe(CHART_ID);
  });

  it("appends cursor query param when provided", async () => {
    mockGet.mockResolvedValue({ items: [], nextCursor: null, hasMore: false });

    await listPerioCharts(PATIENT_ID, "abc123");

    expect(mockGet).toHaveBeenCalledWith(
      `/api/v1/patients/${PATIENT_ID}/perio-charts?cursor=abc123`,
    );
  });
});

describe("getPerioChart", () => {
  it("calls GET /api/v1/patients/:id/perio-charts/:chartId", async () => {
    mockGet.mockResolvedValue(CHART_DETAIL);

    const result = await getPerioChart(PATIENT_ID, CHART_ID);

    expect(mockGet).toHaveBeenCalledWith(
      `/api/v1/patients/${PATIENT_ID}/perio-charts/${CHART_ID}`,
    );
    expect(result.readings).toHaveLength(1);
    expect(result.readings[0]?.cal).toBe(
      result.readings[0]!.probingDepthMm + result.readings[0]!.recessionMm,
    );
  });
});

describe("createPerioChart", () => {
  it("calls POST with idempotency key and returns chart detail", async () => {
    mockPost.mockResolvedValue(CHART_DETAIL);

    const result = await createPerioChart(PATIENT_ID, {
      providerId: PROVIDER_ID,
      chartDate: "2026-05-05",
      readings: [],
    });

    expect(mockPost).toHaveBeenCalledWith(
      `/api/v1/patients/${PATIENT_ID}/perio-charts`,
      expect.objectContaining({ providerId: PROVIDER_ID, chartDate: "2026-05-05" }),
      { idempotencyKey: "test-uuid-idempotency" },
    );
    expect(result.id).toBe(CHART_ID);
  });
});

describe("deletePerioChart", () => {
  it("calls DELETE with idempotency key", async () => {
    mockDelete.mockResolvedValue(undefined);

    await deletePerioChart(PATIENT_ID, CHART_ID);

    expect(mockDelete).toHaveBeenCalledWith(
      `/api/v1/patients/${PATIENT_ID}/perio-charts/${CHART_ID}`,
      { idempotencyKey: "test-uuid-idempotency" },
    );
  });
});

describe("comparePerioCharts", () => {
  it("calls GET compare endpoint with both chart IDs", async () => {
    mockGet.mockResolvedValue({ chartA: CHART_DETAIL, chartB: CHART_DETAIL, deltas: [] });

    await comparePerioCharts(PATIENT_ID, CHART_ID, CHART_B_ID);

    expect(mockGet).toHaveBeenCalledWith(
      `/api/v1/patients/${PATIENT_ID}/perio-charts/compare?chartA=${CHART_ID}&chartB=${CHART_B_ID}`,
    );
  });
});
