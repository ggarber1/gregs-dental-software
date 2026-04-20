/**
 * Regression test for the cancel-from-calendar flow (follow-on to Module 3.4.4).
 *
 * Flow: click an event on the schedule → edit modal opens → click
 * "Cancel appointment" → confirmation dialog opens → confirm → event is
 * removed from the calendar (the schedule filters out cancelled appointments).
 */
import { test, expect } from "@playwright/test";
import { DateTime } from "luxon";

import {
  apiCreateAppointment,
  apiCreatePatient,
  apiDeleteAppointment,
  apiDeletePatient,
  apiListOperatories,
  apiListProviders,
} from "./fixtures/api";

const PRACTICE_TZ = "America/New_York";
const APPT_HOUR = 14;
const APPT_MINUTE = 30;

test.describe("Schedule — cancel from calendar event", () => {
  let patientId: string;
  let appointmentId: string;
  const uniqueLastName = `CancelFlow${Date.now()}`;

  test.beforeEach(async () => {
    const patient = await apiCreatePatient({
      firstName: "E2E",
      lastName: uniqueLastName,
      phone: "+19788180499",
      email: `e2e-cancel-${Date.now()}@dental-e2e.internal`,
      dateOfBirth: "1988-03-15",
    });
    patientId = patient.id;

    const [providers, operatories] = await Promise.all([
      apiListProviders(),
      apiListOperatories(),
    ]);
    const provider = providers.find((p) => p.isActive);
    const operatory = operatories.find((o) => o.isActive);
    if (!provider || !operatory) {
      throw new Error("Test practice needs at least one active provider and operatory");
    }

    const start = DateTime.now().setZone(PRACTICE_TZ).set({
      hour: APPT_HOUR,
      minute: APPT_MINUTE,
      second: 0,
      millisecond: 0,
    });
    const end = start.plus({ minutes: 30 });

    const appointment = await apiCreateAppointment({
      patientId,
      providerId: provider.id,
      operatoryId: operatory.id,
      startTime: start.toUTC().toISO()!,
      endTime: end.toUTC().toISO()!,
    });
    appointmentId = appointment.id;
  });

  test.afterEach(async () => {
    // Appointment may have been cancelled by the test — swallow 404s.
    if (appointmentId) {
      await apiDeleteAppointment(appointmentId).catch(() => undefined);
    }
    if (patientId) {
      await apiDeletePatient(patientId);
    }
  });

  test("clicking an event → Cancel appointment → confirm removes it from the calendar", async ({
    page,
  }) => {
    await page.goto("/schedule");

    // Locate our appointment by the unique patient name we generated.
    const event = page.locator(".fc-event", { hasText: uniqueLastName }).first();
    await expect(event).toBeVisible({ timeout: 10_000 });

    await event.click();

    const editDialog = page.getByRole("dialog").filter({ hasText: "Edit Appointment" });
    await expect(editDialog).toBeVisible();

    await editDialog.getByRole("button", { name: "Cancel appointment" }).click();

    // Edit modal closes, confirmation dialog opens — wait for the edit modal
    // to be gone so `getByRole('dialog')` matches only one.
    await expect(editDialog).toBeHidden();

    const confirmDialog = page.getByRole("dialog").filter({ hasText: "Cancel Appointment" });
    await expect(confirmDialog).toBeVisible();
    await expect(confirmDialog).toContainText(uniqueLastName);

    await confirmDialog.getByRole("button", { name: "Cancel Appointment" }).click();

    // Confirmation dialog closes after the mutation succeeds.
    await expect(confirmDialog).toBeHidden({ timeout: 10_000 });

    // Cancelled appointments are filtered out of the calendar view.
    await expect(
      page.locator(".fc-event", { hasText: uniqueLastName }),
    ).toHaveCount(0);
  });
});
