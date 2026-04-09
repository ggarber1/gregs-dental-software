/**
 * E2E tests for the staff intake form flow.
 *
 * Covers: send form → patient fills form → staff reviews → staff applies.
 * Uses the storageState auth from globalSetup for all staff-authenticated actions.
 *
 * Each test creates its own patient in beforeEach and soft-deletes it in afterEach
 * so that patient creation is exercised on every run.
 */
import { test, expect } from "@playwright/test";
import { apiCreatePatient, apiDeletePatient } from "./fixtures/api";

test.describe("Staff intake flow", () => {
  test.describe("full send → review → apply flow", () => {
    let patientId: string;

    test.beforeEach(async () => {
      const patient = await apiCreatePatient({
        firstName: "E2E",
        lastName: "StaffFlowPatient",
        phone: "+19788180488",
        email: "e2e-staff@dental-e2e.internal",
        dateOfBirth: "1985-06-20",
      });
      patientId = patient.id;
    });

    test.afterEach(async () => {
      if (patientId) {
        await apiDeletePatient(patientId);
      }
    });

    test("full flow: send → patient submits → staff reviews → apply", async ({
      page,
      context,
    }) => {
      // ── 1. Navigate to patient detail page ──────────────────────────────────
      await page.goto(`/patients/${patientId}`);
      await expect(page.getByRole("heading", { name: "Intake Forms" })).toBeVisible();

      // ── 2. Staff clicks "Send form" ──────────────────────────────────────────
      const sendResponsePromise = page.waitForResponse(
        (resp) =>
          resp.url().includes("/api/v1/intake/send") &&
          resp.request().method() === "POST"
      );
      await page.getByRole("button", { name: "Send form" }).click();
      const sendResponse = await sendResponsePromise;
      expect(sendResponse.status()).toBe(201);

      const { formUrl } = (await sendResponse.json()) as {
        intakeFormId: string;
        formUrl: string;
      };
      expect(formUrl).toMatch(/\/intake\//);

      await expect(page.getByText("pending")).toBeVisible({ timeout: 5_000 });

      // ── 3. Patient opens formUrl in a separate browser context ───────────────
      const patientContext = await context.browser()!.newContext();
      const patientPage = await patientContext.newPage();

      await patientPage.goto(formUrl);
      await expect(patientPage.getByText(/welcome!/i)).toBeVisible();

      await patientPage.getByPlaceholder("Jane", { exact: true }).fill("E2EUpdated");
      await patientPage.getByPlaceholder("Doe").fill("StaffFlowPatient");
      await patientPage.getByPlaceholder("1990-01-15").fill("1985-06-20");
      await patientPage.getByPlaceholder("555-867-5309").fill("+19788180488");
      await patientPage.getByRole("button", { name: "Next" }).click();

      await expect(patientPage.getByText("Step 2 of 4: Medical History")).toBeVisible();
      await patientPage.getByRole("button", { name: "Next" }).click();

      await expect(
        patientPage.getByText("Step 3 of 4: Dental History & Insurance")
      ).toBeVisible();
      await patientPage.getByRole("button", { name: "Next" }).click();

      await expect(patientPage.getByText("Step 4 of 4: Review & Consent")).toBeVisible();
      await patientPage.getByRole("checkbox").first().check();
      await patientPage.getByPlaceholder("Jane Doe").fill("E2EUpdated StaffFlowPatient");
      await patientPage.getByRole("button", { name: "Submit" }).click();

      await expect(patientPage).toHaveURL(/\/complete$/);
      await expect(
        patientPage.getByRole("heading", { name: "Form submitted!" })
      ).toBeVisible();
      await patientContext.close();

      // ── 4. Back in staff view — badge updates to "completed" ─────────────────
      await page.reload();
      await expect(page.getByText("completed")).toBeVisible({ timeout: 5_000 });

      // ── 5. Staff clicks "Review" ─────────────────────────────────────────────
      await page.getByRole("button", { name: "Review" }).click();
      await expect(
        page.getByRole("heading", { name: "Review intake form" })
      ).toBeVisible();

      await expect(page.getByText("E2EUpdated", { exact: true })).toBeVisible();

      // ── 6. Staff clicks "Apply to patient record" ────────────────────────────
      await page.getByRole("button", { name: "Apply to patient record" }).click();

      await expect(
        page.getByRole("heading", { name: "Review intake form" })
      ).not.toBeVisible({ timeout: 5_000 });

      await expect(page.getByText("E2EUpdated", { exact: true })).toBeVisible();
    });
  });

  test.describe("send button guard", () => {
    let patientId: string;

    test.beforeEach(async () => {
      // Create a patient with no phone — should disable the Send form button
      const patient = await apiCreatePatient({
        firstName: "E2E",
        lastName: "NoPhonePatient",
        email: "e2e-nophone@dental-e2e.internal",
        dateOfBirth: "1985-06-20",
        // phone intentionally omitted
      });
      patientId = patient.id;
    });

    test.afterEach(async () => {
      if (patientId) {
        await apiDeletePatient(patientId);
      }
    });

    test("send button disabled when patient has no phone", async ({ page }) => {
      await page.goto(`/patients/${patientId}`);
      const sendBtn = page.getByRole("button", { name: "Send form" });
      await expect(sendBtn).toBeDisabled();
    });
  });
});
