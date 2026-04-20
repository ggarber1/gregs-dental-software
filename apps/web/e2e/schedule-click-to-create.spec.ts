/**
 * Regression test for Module 3.4.4.
 *
 * Bug: clicking an empty time slot on the schedule didn't reliably open the
 * create-appointment modal. The `select` handler only fires on drag, so a
 * plain single-click silently did nothing.
 *
 * This test asserts:
 *   1. Single-click on a slot opens the modal with date/startTime/operatory
 *      pre-filled and endTime = start + 30min (the modal fallback).
 *   2. Drag-to-range opens the modal with the *dragged* endTime preserved
 *      (requires `defaultEndTime` threaded through the modal).
 *   3. A single click produces exactly one open dialog (no double-fire
 *      between `dateClick` and `select` — guarded by `selectMinDistance`).
 */
import { test, expect, type Page } from "@playwright/test";
import { DateTime } from "luxon";

import { apiListOperatories } from "./fixtures/api";

const PRACTICE_TZ = "America/New_York";

/**
 * Find the pixel coordinates of a specific (operatory column, slot time) cell
 * in FullCalendar's resourceTimeGridDay view. Returns the center x of the
 * operatory column and the top y of the slot row.
 */
async function locateSlot(
  page: Page,
  operatoryName: string,
  slotTime: string, // "HH:MM:SS"
): Promise<{ x: number; y: number; slotHeight: number }> {
  const slotLabel = page
    .locator(`.fc-timegrid-slot-label[data-time="${slotTime}"]`)
    .first();
  // FC's time grid scrolls internally; late slots (5pm+) are below the fold
  // at default viewport height. Scroll the target row into view before reading
  // its bounding box.
  await slotLabel.scrollIntoViewIfNeeded();
  const slotBox = await slotLabel.boundingBox();

  // Column header is sticky inside the FC scroll container, so its x is
  // stable and we can read it after the scroll without jitter.
  const header = page
    .locator(".fc-col-header-cell", { hasText: operatoryName })
    .first();
  await expect(header).toBeVisible({ timeout: 10_000 });
  const headerBox = await header.boundingBox();

  if (!headerBox || !slotBox) {
    throw new Error(
      `Could not locate slot: operatory="${operatoryName}" time="${slotTime}"`,
    );
  }

  return {
    x: headerBox.x + headerBox.width / 2,
    y: slotBox.y + 4, // nudge inside the lane, away from the grid line
    slotHeight: slotBox.height,
  };
}

test.describe("Schedule — click-to-create (Module 3.4.4)", () => {
  let operatoryName: string;
  let todayIsoDate: string; // YYYY-MM-DD in practice TZ

  test.beforeAll(async () => {
    const operatories = await apiListOperatories();
    const operatory = operatories.find((o) => o.isActive);
    if (!operatory) {
      throw new Error("Test practice needs at least one active operatory seeded");
    }
    operatoryName = operatory.name;
    todayIsoDate = DateTime.now().setZone(PRACTICE_TZ).toISODate()!;
  });

  // Seed data fills the business-hours window (9am–5pm) with appointments, so
  // clicking at 9am on operatory 1 can land on an existing event tile and
  // trigger eventClick instead of dateClick. 5pm–6pm is outside businessHours
  // and consistently empty across seed variations.
  const EMPTY_START = "17:00:00"; // 5pm
  const EMPTY_END = "18:00:00"; // 6pm

  test("single click on an empty slot opens modal with start/end pre-filled and operatory preselected", async ({
    page,
  }) => {
    await page.goto("/schedule");

    // Wait for the resource grid to render before probing for cells.
    await expect(page.locator(".fc-timegrid-slots").first()).toBeVisible({
      timeout: 10_000,
    });

    const slot = await locateSlot(page, operatoryName, EMPTY_START);
    await page.mouse.click(slot.x, slot.y);

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    await expect(dialog.locator("#date")).toHaveValue(todayIsoDate);
    await expect(dialog.locator("#start-time")).toHaveValue("17:00");
    await expect(dialog.locator("#end-time")).toHaveValue("17:30");

    // Operatory select — shadcn renders the selected label inside the trigger.
    await expect(dialog.locator("#operatory")).toContainText(operatoryName);

    // No double-fire: exactly one dialog open.
    await expect(page.getByRole("dialog")).toHaveCount(1);
  });

  test("drag from 5pm to 6pm preserves the dragged endTime", async ({ page }) => {
    await page.goto("/schedule");

    await expect(page.locator(".fc-timegrid-slots").first()).toBeVisible({
      timeout: 10_000,
    });

    const start = await locateSlot(page, operatoryName, EMPTY_START);
    const end = await locateSlot(page, operatoryName, EMPTY_END);

    // FC selects the slot the cursor is *over*: end the drag a few pixels
    // above the 6pm label (i.e. inside the 5:45 row) so the half-open
    // selection snaps to 18:00. Ending 4px below (inside the 6pm row) would
    // extend the selection to 18:15.
    const dragEndY = end.y - 4;

    // Mouse drag across 4 quarter-hour slots. `selectMinDistance={5}` is
    // satisfied because 5pm→6pm is well over 5 pixels vertically.
    await page.mouse.move(start.x, start.y);
    await page.mouse.down();
    // Intermediate step — some browsers coalesce move+down+up into a click
    // unless at least one move event is dispatched.
    await page.mouse.move(start.x, (start.y + dragEndY) / 2, { steps: 5 });
    await page.mouse.move(start.x, dragEndY, { steps: 5 });
    await page.mouse.up();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    await expect(dialog.locator("#start-time")).toHaveValue("17:00");
    await expect(dialog.locator("#end-time")).toHaveValue("18:00");
    await expect(dialog.locator("#operatory")).toContainText(operatoryName);
  });
});
