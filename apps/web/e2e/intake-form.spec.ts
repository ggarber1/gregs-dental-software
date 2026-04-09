/**
 * E2E tests for the public patient-facing intake form.
 *
 * These pages require no authentication — anyone with the link can access them.
 * The staff auth (via storageState) is only used to create the patient + intake
 * form via the API so the test has a valid token URL to navigate to.
 *
 * Each test creates its own patient in beforeEach and soft-deletes it in afterEach
 * so that patient creation is exercised on every run.
 */
import { test, expect } from "@playwright/test";
import { apiCreatePatient, apiDeletePatient, apiSendIntakeForm } from "./fixtures/api";

test.describe("Public intake form", () => {
  let patientId: string;

  test.beforeEach(async () => {
    const patient = await apiCreatePatient({
      firstName: "E2E",
      lastName: "IntakePatient",
      phone: "+19788180488",
      email: "e2e-intake@dental-e2e.internal",
      dateOfBirth: "1985-06-20",
    });
    patientId = patient.id;
  });

  test.afterEach(async () => {
    if (patientId) {
      await apiDeletePatient(patientId);
    }
  });

  test("shows practice name and patient greeting", async ({ page }) => {
    const { formUrl } = await apiSendIntakeForm(patientId);
    await page.goto(formUrl);

    await expect(page.getByText(/welcome!/i)).toBeVisible();
    await expect(page.getByText("Step 1 of 4: Personal Information")).toBeVisible();
  });

  test("full happy-path submit → redirects to complete page", async ({ page }) => {
    const { formUrl } = await apiSendIntakeForm(patientId);
    await page.goto(formUrl);

    // ── Step 1: Personal Information ──────────────────────────────────────────
    await page.getByPlaceholder("Jane", { exact: true }).fill("E2E");
    await page.getByPlaceholder("Doe").fill("TestPatient");
    await page.getByPlaceholder("1990-01-15").fill("1985-06-20");
    await page.getByPlaceholder("555-867-5309").fill("+19788180488");
    await page.getByRole("button", { name: "Next" }).click();

    // ── Step 2: Medical History ───────────────────────────────────────────────
    await expect(page.getByText("Step 2 of 4: Medical History")).toBeVisible();
    await page.locator("textarea").first().fill("aspirin");
    await page.locator("textarea").last().fill("penicillin");
    await page.getByRole("button", { name: "Next" }).click();

    // ── Step 3: Dental History & Insurance ───────────────────────────────────
    await expect(page.getByText("Step 3 of 4: Dental History & Insurance")).toBeVisible();
    await page.getByRole("button", { name: "Next" }).click();

    // ── Step 4: HIPAA Consent ─────────────────────────────────────────────────
    await expect(page.getByText("Step 4 of 4: Review & Consent")).toBeVisible();
    await page.getByRole("checkbox").first().check();
    await page.getByPlaceholder("Jane Doe").fill("E2E TestPatient");
    await page.getByRole("button", { name: "Submit" }).click();

    await expect(page).toHaveURL(/\/complete$/);
    await expect(page.getByRole("heading", { name: "Form submitted!" })).toBeVisible();
  });

  test("re-visiting a completed token shows 'Already submitted'", async ({ page }) => {
    const { formUrl } = await apiSendIntakeForm(patientId);
    await page.goto(formUrl);

    // Complete the form
    await page.getByPlaceholder("Jane", { exact: true }).fill("E2E");
    await page.getByPlaceholder("Doe").fill("TestPatient");
    await page.getByPlaceholder("1990-01-15").fill("1985-06-20");
    await page.getByPlaceholder("555-867-5309").fill("+19788180488");
    await page.getByRole("button", { name: "Next" }).click();
    await page.getByRole("button", { name: "Next" }).click();
    await page.getByRole("button", { name: "Next" }).click();
    await page.getByRole("checkbox").first().check();
    await page.getByPlaceholder("Jane Doe").fill("E2E TestPatient");
    await page.getByRole("button", { name: "Submit" }).click();
    await expect(page).toHaveURL(/\/complete$/);

    // Navigate back to the original token URL
    await page.goto(formUrl);
    await expect(page.getByText("Already submitted")).toBeVisible();
  });

  test("unknown token shows error state", async ({ page }) => {
    await page.goto(`/intake/${"0".repeat(64)}`);
    await expect(page.getByText("Something went wrong")).toBeVisible();
  });
});
