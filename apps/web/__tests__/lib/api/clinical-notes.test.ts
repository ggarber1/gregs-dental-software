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
  listClinicalNotes,
  getClinicalNote,
  createClinicalNote,
  updateClinicalNote,
  signClinicalNote,
  type ClinicalNote,
  type ClinicalNoteListResponse,
} from "@/lib/api/clinical-notes";

const mockGet = vi.mocked(apiClient.get);
const mockPost = vi.mocked(apiClient.post);
const mockPatch = vi.mocked(apiClient.patch);

const PATIENT_ID = "patient-uuid-1";
const NOTE_ID = "note-uuid-1";

const NOTE: ClinicalNote = {
  id: NOTE_ID,
  practiceId: "practice-uuid-1",
  patientId: PATIENT_ID,
  appointmentId: null,
  providerId: "provider-uuid-1",
  visitDate: "2026-05-03",
  chiefComplaint: "Tooth pain",
  anesthesia: null,
  patientTolerance: null,
  complications: null,
  treatmentRendered: "Exam and X-rays completed",
  nextVisitPlan: null,
  notes: null,
  templateType: "exam",
  isSigned: false,
  signedAt: null,
  signedByProviderId: null,
  createdAt: "2026-05-03T12:00:00Z",
  updatedAt: "2026-05-03T12:00:00Z",
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("crypto", { randomUUID: vi.fn().mockReturnValue("test-uuid-idempotency") });
});

// ── listClinicalNotes ─────────────────────────────────────────────────────────

describe("listClinicalNotes", () => {
  it("calls GET /api/v1/patients/:id/clinical-notes with limit param", async () => {
    const response: ClinicalNoteListResponse = {
      items: [NOTE],
      nextCursor: null,
      hasMore: false,
    };
    mockGet.mockResolvedValue(response);

    const result = await listClinicalNotes(PATIENT_ID, 20);

    expect(mockGet).toHaveBeenCalledWith(
      `/api/v1/patients/${PATIENT_ID}/clinical-notes?limit=20`,
    );
    expect(result).toEqual(response);
  });

  it("includes cursor param when provided", async () => {
    mockGet.mockResolvedValue({ items: [], nextCursor: null, hasMore: false });

    await listClinicalNotes(PATIENT_ID, 20, "abc123cursor");

    expect(mockGet).toHaveBeenCalledWith(
      `/api/v1/patients/${PATIENT_ID}/clinical-notes?limit=20&cursor=abc123cursor`,
    );
  });

  it("includes appointment_id filter when provided", async () => {
    mockGet.mockResolvedValue({ items: [], nextCursor: null, hasMore: false });
    const apptId = "appt-uuid-1";

    await listClinicalNotes(PATIENT_ID, 20, undefined, apptId);

    const [url] = mockGet.mock.calls[0]!;
    expect(url).toContain(`appointment_id=${apptId}`);
  });
});

// ── getClinicalNote ───────────────────────────────────────────────────────────

describe("getClinicalNote", () => {
  it("calls GET /api/v1/patients/:id/clinical-notes/:noteId", async () => {
    mockGet.mockResolvedValue(NOTE);

    const result = await getClinicalNote(PATIENT_ID, NOTE_ID);

    expect(mockGet).toHaveBeenCalledWith(
      `/api/v1/patients/${PATIENT_ID}/clinical-notes/${NOTE_ID}`,
    );
    expect(result).toEqual(NOTE);
  });

  it("propagates ApiError on 404", async () => {
    mockGet.mockRejectedValue(new ApiError(404, { error: { code: "NOTE_NOT_FOUND" } }));

    await expect(getClinicalNote(PATIENT_ID, NOTE_ID)).rejects.toMatchObject({
      status: 404,
    });
  });
});

// ── createClinicalNote ────────────────────────────────────────────────────────

describe("createClinicalNote", () => {
  it("calls POST with correct body and idempotency key", async () => {
    mockPost.mockResolvedValue(NOTE);

    const body = {
      providerId: "provider-uuid-1",
      visitDate: "2026-05-03",
      treatmentRendered: "Exam completed",
      templateType: "exam" as const,
    };
    await createClinicalNote(PATIENT_ID, body);

    expect(mockPost).toHaveBeenCalledWith(
      `/api/v1/patients/${PATIENT_ID}/clinical-notes`,
      body,
      { idempotencyKey: "test-uuid-idempotency" },
    );
  });
});

// ── updateClinicalNote ────────────────────────────────────────────────────────

describe("updateClinicalNote", () => {
  it("calls PATCH with correct body and idempotency key", async () => {
    mockPatch.mockResolvedValue({ ...NOTE, treatmentRendered: "Updated" });

    await updateClinicalNote(PATIENT_ID, NOTE_ID, { treatmentRendered: "Updated" });

    expect(mockPatch).toHaveBeenCalledWith(
      `/api/v1/patients/${PATIENT_ID}/clinical-notes/${NOTE_ID}`,
      { treatmentRendered: "Updated" },
      { idempotencyKey: "test-uuid-idempotency" },
    );
  });

  it("propagates ApiError 409 when note is signed", async () => {
    mockPatch.mockRejectedValue(
      new ApiError(409, { error: { code: "NOTE_ALREADY_SIGNED" } }),
    );

    await expect(
      updateClinicalNote(PATIENT_ID, NOTE_ID, { treatmentRendered: "edit" }),
    ).rejects.toMatchObject({ status: 409 });
  });
});

// ── signClinicalNote ──────────────────────────────────────────────────────────

describe("signClinicalNote", () => {
  it("calls POST /sign with empty body and idempotency key", async () => {
    mockPost.mockResolvedValue({ ...NOTE, isSigned: true });

    await signClinicalNote(PATIENT_ID, NOTE_ID);

    expect(mockPost).toHaveBeenCalledWith(
      `/api/v1/patients/${PATIENT_ID}/clinical-notes/${NOTE_ID}/sign`,
      {},
      { idempotencyKey: "test-uuid-idempotency" },
    );
  });

  it("propagates ApiError 409 on second sign attempt", async () => {
    mockPost.mockRejectedValue(
      new ApiError(409, { error: { code: "NOTE_ALREADY_SIGNED" } }),
    );

    await expect(signClinicalNote(PATIENT_ID, NOTE_ID)).rejects.toMatchObject({
      status: 409,
    });
  });
});
