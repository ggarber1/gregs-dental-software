import { describe, it, expect } from "vitest";
import {
  CLINICAL_NOTE_TEMPLATES,
  TEMPLATE_TYPE_OPTIONS,
} from "@/lib/clinical-note-templates";

const EXPECTED_TEMPLATE_TYPES = [
  "exam",
  "prophy",
  "extraction",
  "crown_prep",
  "crown_seat",
  "root_canal",
  "filling",
  "srp",
  "other",
] as const;

describe("CLINICAL_NOTE_TEMPLATES", () => {
  it("contains all 9 template types", () => {
    expect(Object.keys(CLINICAL_NOTE_TEMPLATES)).toHaveLength(9);
    for (const type of EXPECTED_TEMPLATE_TYPES) {
      expect(CLINICAL_NOTE_TEMPLATES).toHaveProperty(type);
    }
  });

  it("every template has a non-empty body except 'other'", () => {
    for (const type of EXPECTED_TEMPLATE_TYPES) {
      const tpl = CLINICAL_NOTE_TEMPLATES[type];
      if (type === "other") {
        // 'other' is intentionally blank — provider fills everything
        expect(tpl.body).toBe("");
      } else {
        expect(tpl.body.trim().length).toBeGreaterThan(0);
      }
    }
  });

  it("non-'other' templates include CC, Anesthesia, Treatment, and Next visit sections", () => {
    for (const type of EXPECTED_TEMPLATE_TYPES) {
      if (type === "other") continue;
      const body = CLINICAL_NOTE_TEMPLATES[type].body;
      expect(body, `${type} missing CC:`).toContain("CC:");
      expect(body, `${type} missing Anesthesia:`).toContain("Anesthesia:");
      expect(body, `${type} missing Treatment:`).toContain("Treatment:");
      expect(body, `${type} missing Next visit:`).toContain("Next visit:");
    }
  });

  it("every template has a non-empty multi-line body except 'other'", () => {
    for (const type of EXPECTED_TEMPLATE_TYPES) {
      if (type === "other") continue;
      expect(CLINICAL_NOTE_TEMPLATES[type].body).toContain("\n");
    }
  });

  it("every template type field matches its map key", () => {
    for (const type of EXPECTED_TEMPLATE_TYPES) {
      expect(CLINICAL_NOTE_TEMPLATES[type].type).toBe(type);
    }
  });

  it("every template has a non-empty label", () => {
    for (const type of EXPECTED_TEMPLATE_TYPES) {
      expect(CLINICAL_NOTE_TEMPLATES[type].label.trim().length).toBeGreaterThan(0);
    }
  });
});

describe("TEMPLATE_TYPE_OPTIONS", () => {
  it("has exactly 9 options in the correct order", () => {
    expect(TEMPLATE_TYPE_OPTIONS).toHaveLength(9);
    const values = TEMPLATE_TYPE_OPTIONS.map((o) => o.value);
    expect(values).toEqual(EXPECTED_TEMPLATE_TYPES);
  });

  it("every option has a non-empty label", () => {
    for (const opt of TEMPLATE_TYPE_OPTIONS) {
      expect(opt.label.trim().length).toBeGreaterThan(0);
    }
  });
});
