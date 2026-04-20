import { describe, it, expect } from "vitest";

import {
  activeDentists,
  matchDentistByNpi,
  type DentistCandidate,
} from "@/components/settings/supervisingDentist";

const mk = (overrides: Partial<DentistCandidate>): DentistCandidate => ({
  id: "p-1",
  fullName: "Dr. Default",
  npi: "1000000001",
  providerType: "dentist",
  isActive: true,
  displayOrder: 0,
  ...overrides,
});

describe("activeDentists", () => {
  it("returns only active dentists", () => {
    const providers = [
      mk({ id: "d1", fullName: "Dr. A" }),
      mk({ id: "h1", fullName: "Hygienist H", providerType: "hygienist" }),
      mk({ id: "d2", fullName: "Dr. B", isActive: false }),
      mk({ id: "s1", fullName: "Specialist S", providerType: "specialist" }),
    ];
    const result = activeDentists(providers);
    expect(result.map((p) => p.id)).toEqual(["d1"]);
  });

  it("sorts by displayOrder then fullName", () => {
    const providers = [
      mk({ id: "d1", fullName: "Zeta", displayOrder: 2 }),
      mk({ id: "d2", fullName: "Alpha", displayOrder: 1 }),
      mk({ id: "d3", fullName: "Beta", displayOrder: 1 }),
    ];
    const result = activeDentists(providers);
    expect(result.map((p) => p.id)).toEqual(["d2", "d3", "d1"]);
  });

  it("excludes the provider currently being edited", () => {
    const providers = [
      mk({ id: "d1", fullName: "Dr. A" }),
      mk({ id: "d2", fullName: "Dr. B" }),
    ];
    const result = activeDentists(providers, "d1");
    expect(result.map((p) => p.id)).toEqual(["d2"]);
  });

  it("handles undefined input", () => {
    expect(activeDentists(undefined)).toEqual([]);
  });
});

describe("matchDentistByNpi", () => {
  const dentists = [
    mk({ id: "d1", fullName: "Dr. A", npi: "1111111111" }),
    mk({ id: "d2", fullName: "Dr. B", npi: "2222222222" }),
  ];

  it("returns 'unset' when NPI is empty", () => {
    expect(matchDentistByNpi("", dentists)).toEqual({ kind: "unset" });
  });

  it("returns 'dentist' with id when NPI matches", () => {
    expect(matchDentistByNpi("2222222222", dentists)).toEqual({
      kind: "dentist",
      providerId: "d2",
    });
  });

  it("returns 'custom' when NPI is set but doesn't match any dentist", () => {
    expect(matchDentistByNpi("9999999999", dentists)).toEqual({
      kind: "custom",
    });
  });

  it("returns 'custom' when no dentists exist", () => {
    expect(matchDentistByNpi("1234567890", [])).toEqual({ kind: "custom" });
  });
});
