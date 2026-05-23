import { describe, it, expect } from "vitest";

import {
  buildCreateBody,
  hasLegacyFields,
  legacyFieldsFromNote,
  validateFields,
  type NoteFields,
} from "@/components/patients/ClinicalNoteEditor";
import type { ClinicalNote } from "@/lib/api/clinical-notes";

const baseNote = (overrides: Partial<ClinicalNote> = {}): ClinicalNote => ({
  id: "note-1",
  practiceId: "practice-1",
  patientId: "patient-1",
  appointmentId: null,
  providerId: "provider-1",
  visitDate: "2026-05-23",
  chiefComplaint: null,
  anesthesia: null,
  patientTolerance: null,
  complications: null,
  treatmentRendered: "Treatment text",
  nextVisitPlan: null,
  notes: null,
  templateType: null,
  isSigned: false,
  signedAt: null,
  signedByProviderId: null,
  createdAt: "2026-05-23T12:00:00Z",
  updatedAt: "2026-05-23T12:00:00Z",
  ...overrides,
});

const validFields = (overrides: Partial<NoteFields> = {}): NoteFields => ({
  providerId: "provider-1",
  visitDate: "2026-05-23",
  templateType: "",
  treatmentRendered: "Exam completed.",
  ...overrides,
});

// ── validateFields ────────────────────────────────────────────────────────────

describe("validateFields", () => {
  it("returns ok when all required fields are present", () => {
    expect(validateFields(validFields())).toEqual({ ok: true });
  });

  it("fails with 'Treatment rendered is required.' when textarea is blank", () => {
    const result = validateFields(validFields({ treatmentRendered: "   " }));
    expect(result).toEqual({
      ok: false,
      error: "Treatment rendered is required.",
    });
  });

  it("fails when visit date is empty", () => {
    expect(validateFields(validFields({ visitDate: "" }))).toEqual({
      ok: false,
      error: "Visit date is required.",
    });
  });

  it("fails when provider is empty", () => {
    expect(validateFields(validFields({ providerId: "" }))).toEqual({
      ok: false,
      error: "Provider is required.",
    });
  });
});

// ── hasLegacyFields ───────────────────────────────────────────────────────────

describe("hasLegacyFields", () => {
  it("returns false for undefined (new note)", () => {
    expect(hasLegacyFields(undefined)).toBe(false);
  });

  it("returns false when all deprecated fields are null", () => {
    expect(hasLegacyFields(baseNote())).toBe(false);
  });

  it("returns false when deprecated fields are only whitespace", () => {
    expect(
      hasLegacyFields(
        baseNote({
          chiefComplaint: "   ",
          anesthesia: "",
          notes: "\n\t",
        }),
      ),
    ).toBe(false);
  });

  it("returns true when chiefComplaint is populated", () => {
    expect(
      hasLegacyFields(baseNote({ chiefComplaint: "Tooth pain on #14" })),
    ).toBe(true);
  });

  it("returns true when any one of the six deprecated fields is populated", () => {
    for (const field of [
      "chiefComplaint",
      "anesthesia",
      "patientTolerance",
      "complications",
      "nextVisitPlan",
      "notes",
    ] as const) {
      const note = baseNote({ [field]: "value" } as Partial<ClinicalNote>);
      expect(hasLegacyFields(note), `expected true for ${field}`).toBe(true);
    }
  });
});

// ── legacyFieldsFromNote ──────────────────────────────────────────────────────

describe("legacyFieldsFromNote", () => {
  it("returns the six deprecated fields from the note", () => {
    const note = baseNote({
      chiefComplaint: "CC text",
      anesthesia: "Lido 2%",
      patientTolerance: "good",
      complications: "none",
      nextVisitPlan: "Recall 6mo",
      notes: "Patient nervous",
    });
    expect(legacyFieldsFromNote(note)).toEqual({
      chiefComplaint: "CC text",
      anesthesia: "Lido 2%",
      patientTolerance: "good",
      complications: "none",
      nextVisitPlan: "Recall 6mo",
      notes: "Patient nervous",
    });
  });
});

// ── buildCreateBody ───────────────────────────────────────────────────────────

describe("buildCreateBody", () => {
  it("only includes providerId, visitDate, treatmentRendered when no template or appointment", () => {
    expect(buildCreateBody(validFields())).toEqual({
      providerId: "provider-1",
      visitDate: "2026-05-23",
      treatmentRendered: "Exam completed.",
    });
  });

  it("includes appointmentId when provided", () => {
    const body = buildCreateBody(validFields(), "appt-7");
    expect(body.appointmentId).toBe("appt-7");
  });

  it("includes templateType when set", () => {
    const body = buildCreateBody(validFields({ templateType: "prophy" }));
    expect(body.templateType).toBe("prophy");
  });

  it("does not include any of the deprecated multi-field properties", () => {
    const body = buildCreateBody(validFields({ templateType: "exam" }), "appt-1");
    expect(body).not.toHaveProperty("chiefComplaint");
    expect(body).not.toHaveProperty("anesthesia");
    expect(body).not.toHaveProperty("patientTolerance");
    expect(body).not.toHaveProperty("complications");
    expect(body).not.toHaveProperty("nextVisitPlan");
    expect(body).not.toHaveProperty("notes");
  });
});
