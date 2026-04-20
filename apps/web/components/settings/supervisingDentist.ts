/**
 * Supervising-dentist selection logic for the Provider form (Module 3.4.1).
 *
 * Hygienists bill under a supervising dentist's NPI. When creating/editing a
 * hygienist, the form shows a dropdown of active dentists that auto-fills the
 * NPI field. This module holds the pure logic so it can be unit-tested without
 * the component (no jsdom/testing-library needed).
 */

export type SupervisingDentistSelection =
  | { kind: "dentist"; providerId: string }
  | { kind: "custom" }
  | { kind: "unset" };

export interface DentistCandidate {
  id: string;
  fullName: string;
  npi: string;
  providerType: string;
  isActive: boolean;
  displayOrder: number;
}

export const CUSTOM_NPI_SENTINEL = "__custom__";

export function activeDentists<T extends DentistCandidate>(
  providers: readonly T[] | undefined,
  excludeId?: string,
): T[] {
  return (providers ?? [])
    .filter(
      (p) =>
        p.providerType === "dentist" &&
        p.isActive &&
        (excludeId === undefined || p.id !== excludeId),
    )
    .slice()
    .sort(
      (a, b) =>
        a.displayOrder - b.displayOrder || a.fullName.localeCompare(b.fullName),
    );
}

/**
 * Decide how the supervising-dentist dropdown should be pre-selected when the
 * edit modal opens for an existing hygienist, given the row's current NPI and
 * the list of active dentists in the practice.
 */
export function matchDentistByNpi(
  npi: string,
  dentists: readonly DentistCandidate[],
): SupervisingDentistSelection {
  if (!npi) return { kind: "unset" };
  const match = dentists.find((d) => d.npi === npi);
  return match
    ? { kind: "dentist", providerId: match.id }
    : { kind: "custom" };
}
