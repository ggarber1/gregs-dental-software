/**
 * Regression test for Module 3.4.3.
 *
 * Bug: appointment booked at 9am appeared at 1pm on the calendar because
 * FullCalendar's `timeZone` prop requires the Luxon plugin to resolve named
 * IANA zones. Without it, FC silently falls back to UTC, so a `"...Z"` event
 * renders at its UTC wall-clock time instead of the practice's local time.
 *
 * This test creates an appointment at a specific NY-local time, navigates to
 * /schedule, and asserts the event renders in the expected hourly row.
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
// 14:15 is unusual enough that a spurious match on the calendar is unlikely,
// and not on an hour boundary so it can't be confused with an adjacent event.
const APPT_LOCAL_HOUR = 14;
const APPT_LOCAL_MINUTE = 15;

test.describe("Schedule — timezone rendering (Module 3.4.3)", () => {
  let patientId: string;
  let appointmentId: string;

  test.beforeEach(async () => {
    const patient = await apiCreatePatient({
      firstName: "E2E",
      lastName: "TimezonePatient",
      phone: "+19788180499",
      email: "e2e-timezone@dental-e2e.internal",
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
      throw new Error("Test practice needs at least one active provider and operatory seeded");
    }

    // Build the target datetime in the practice's local time, then convert to
    // UTC ISO for the API. This is what the schedule page does on create, so
    // we mirror that contract.
    const todayInTz = DateTime.now().setZone(PRACTICE_TZ);
    const start = todayInTz.set({
      hour: APPT_LOCAL_HOUR,
      minute: APPT_LOCAL_MINUTE,
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
    if (appointmentId) {
      await apiDeleteAppointment(appointmentId);
    }
    if (patientId) {
      await apiDeletePatient(patientId);
    }
  });

  test("event created at 2:15pm NY renders in the 2pm row (not the UTC hour)", async ({
    page,
  }) => {
    await page.goto("/schedule");

    // Wait for the calendar to render at least one event. The event we just
    // created is for today, so it should be on the initial view.
    const event = page.locator(".fc-event").first();
    await expect(event).toBeVisible({ timeout: 10_000 });

    // The .fc-event-time element shows the event's start in the configured
    // timeZone. With the luxon plugin wired up, this should read "2:15p" (or
    // locale variant). Without it, FC would render in UTC and show "6:15p" in
    // EDT / "7:15p" in EST — which is exactly the bug being guarded against.
    const eventTime = event.locator(".fc-event-time");
    await expect(eventTime).toBeVisible();
    const text = (await eventTime.textContent()) ?? "";
    expect(
      /2:15/.test(text),
      `Expected .fc-event-time to include "2:15" (the practice-local time), got "${text}". ` +
        `If it reads "6:15" or "7:15", the Luxon plugin for FullCalendar's timeZone prop is missing ` +
        `in apps/web/app/(app)/schedule/page.tsx.`
    ).toBe(true);

    // Belt-and-suspenders: assert the event's top pixel is inside the row
    // labeled "2pm". FullCalendar labels slot times in the left gutter.
    const twoPmLabel = page.locator(".fc-timegrid-slot-label-cushion", { hasText: /2\s?p/i }).first();
    const twoPmBox = await twoPmLabel.boundingBox();
    const eventBox = await event.boundingBox();
    expect(twoPmBox).not.toBeNull();
    expect(eventBox).not.toBeNull();
    // The event's top should be within ~1 slot-height of the 2pm row. Slot
    // duration is 15 min and slotLabelInterval is 1h, so the cushion is about
    // 60px but vary by font/theme. Use a generous 80px tolerance — the bug
    // would displace the event by 4 hours (~240px), well outside this window.
    if (twoPmBox && eventBox) {
      expect(Math.abs(eventBox.y - twoPmBox.y)).toBeLessThan(80);
    }
  });
});
