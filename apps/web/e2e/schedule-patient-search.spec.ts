/**
 * Regression test for Module 3.4.5.
 *
 * Verifies that the patient-search input in the create-appointment modal:
 *   1. Matches a patient by phone number typed in a different format than
 *      how the phone is stored (normalization happens server-side).
 *   2. Renders the patient's phone number in the dropdown row so staff can
 *      visually confirm the match on a call.
 */
import { test, expect } from "@playwright/test";

import { apiCreatePatient, apiDeletePatient, apiListOperatories } from "./fixtures/api";

test.describe("Schedule — patient search by phone (Module 3.4.5)", () => {
  let patientId: string;
  const uniqueSuffix = Date.now();
  // Store with one formatting, search with another; the backend strips
  // non-digits on both sides before matching.
  const STORED_PHONE = "(555) 123-9876";
  const SEARCH_INPUT = "555-123-9876";

  test.beforeEach(async () => {
    const patient = await apiCreatePatient({
      firstName: "PhoneSearch",
      lastName: `E2E${uniqueSuffix}`,
      phone: STORED_PHONE,
      email: `phone-search-${uniqueSuffix}@dental-e2e.internal`,
      dateOfBirth: "1990-06-15",
    });
    patientId = patient.id;
  });

  test.afterEach(async () => {
    if (patientId) {
      await apiDeletePatient(patientId);
    }
  });

  test("typing a phone in a different format finds the patient and shows the stored phone", async ({
    page,
  }) => {
    // Sanity: at least one operatory must be seeded — the click-to-create
    // flow we piggyback on requires a column to click on.
    const operatories = await apiListOperatories();
    const operatory = operatories.find((o) => o.isActive);
    if (!operatory) {
      throw new Error("Test practice needs at least one active operatory seeded");
    }

    await page.goto("/schedule");
    await expect(page.locator(".fc-timegrid-slots").first()).toBeVisible({
      timeout: 10_000,
    });

    // Open the create-appointment modal via the toolbar (avoids reliance on
    // a specific empty slot — the 5pm row may or may not be empty depending
    // on seed drift).
    await page.getByRole("button", { name: /new appointment/i }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    const searchInput = dialog.getByLabel("Patient");
    await searchInput.fill(SEARCH_INPUT);

    // 300ms debounce in the modal; wait for the dropdown row to appear.
    const row = dialog.getByRole("button", {
      name: new RegExp(`PhoneSearch E2E${uniqueSuffix}`),
    });
    await expect(row).toBeVisible({ timeout: 5_000 });

    // The stored phone (not the search input format) is what we render.
    await expect(row).toContainText(STORED_PHONE);
  });
});
