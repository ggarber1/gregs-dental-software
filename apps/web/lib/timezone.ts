/**
 * Timezone utility functions.
 *
 * All display-facing date/time formatting in the scheduling UI must use these
 * functions with the practice timezone — never rely on the browser's local TZ.
 *
 * All functions use the built-in Intl API (no external deps).
 */

/**
 * Format an ISO datetime string as a display time (e.g. "9:00 AM") in the
 * given IANA timezone.
 */
export function formatTimeInTz(isoString: string, timezone: string): string {
  const d = new Date(isoString);
  return new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(d);
}

/**
 * Format a Date object as a long date header (e.g. "Wednesday, April 16, 2026")
 * in the given IANA timezone.
 */
export function formatDateHeaderInTz(date: Date, timezone: string): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(date);
}

/**
 * Extract the time portion of an ISO datetime string as "HH:mm" (24-hour)
 * in the given IANA timezone. Used for pre-filling time inputs.
 */
export function isoToTimeInTz(isoString: string, timezone: string): string {
  const d = new Date(isoString);
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(d);

  const hour = parts.find((p) => p.type === "hour")?.value ?? "00";
  const minute = parts.find((p) => p.type === "minute")?.value ?? "00";
  // Intl may return "24" for midnight in hour12:false mode — normalise to "00"
  const h = hour === "24" ? "00" : hour;
  return `${h}:${minute}`;
}

/**
 * Extract the date portion of an ISO datetime string as "YYYY-MM-DD"
 * in the given IANA timezone. Used for pre-filling date inputs.
 */
export function isoToDateInTz(isoString: string, timezone: string): string {
  const d = new Date(isoString);
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(d);

  const year = parts.find((p) => p.type === "year")?.value ?? "2026";
  const month = parts.find((p) => p.type === "month")?.value ?? "01";
  const day = parts.find((p) => p.type === "day")?.value ?? "01";
  return `${year}-${month}-${day}`;
}

/**
 * Convert a user-entered date ("YYYY-MM-DD") and time ("HH:mm") in the
 * practice timezone to a UTC ISO string for the API.
 *
 * Strategy: construct a date string with the timezone's UTC offset at that
 * instant so the Date constructor interprets it correctly.
 */
export function localInputToUTC(
  dateStr: string,
  timeStr: string,
  timezone: string,
): string {
  // Build a rough Date in UTC to get the offset for this timezone at this time.
  // Parse the date/time parts — these are the "wall clock" values the user sees.
  const [yearStr, monthStr, dayStr] = dateStr.split("-");
  const [hourStr, minuteStr] = timeStr.split(":");
  const year = Number(yearStr);
  const month = Number(monthStr) - 1; // Date months are 0-indexed
  const day = Number(dayStr);
  const hour = Number(hourStr);
  const minute = Number(minuteStr);

  // Create a "guess" Date in UTC matching the wall-clock values
  const guessUtc = new Date(Date.UTC(year, month, day, hour, minute, 0, 0));

  // Determine what the wall-clock time is at that UTC instant in the target tz.
  // The difference tells us the offset.
  const tzParts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(guessUtc);

  const tzYear = Number(tzParts.find((p) => p.type === "year")?.value);
  const tzMonth = Number(tzParts.find((p) => p.type === "month")?.value) - 1;
  const tzDay = Number(tzParts.find((p) => p.type === "day")?.value);
  let tzHour = Number(tzParts.find((p) => p.type === "hour")?.value);
  if (tzHour === 24) tzHour = 0;
  const tzMinute = Number(tzParts.find((p) => p.type === "minute")?.value);
  const tzSecond = Number(tzParts.find((p) => p.type === "second")?.value);

  // Wall-clock in TZ at the guessUtc instant
  const wallAtGuess = Date.UTC(tzYear, tzMonth, tzDay, tzHour, tzMinute, tzSecond);
  // The offset = wallAtGuess - guessUtc (in ms)
  const offsetMs = wallAtGuess - guessUtc.getTime();

  // The actual UTC time for the user's intended wall-clock time:
  // userUtc = userWall - offset
  const userWallMs = Date.UTC(year, month, day, hour, minute, 0, 0);
  const result = new Date(userWallMs - offsetMs);

  return result.toISOString();
}

/**
 * Return today's date as "YYYY-MM-DD" in the given IANA timezone.
 */
export function todayInTz(timezone: string): string {
  return isoToDateInTz(new Date().toISOString(), timezone);
}

/**
 * Return the UTC start and end of a calendar day in the given IANA timezone.
 *
 * The `date` parameter is a Date object representing the day the user selected
 * (its exact time is irrelevant — only the date as seen in the practice TZ matters).
 */
export function dayBoundsInTz(
  date: Date,
  timezone: string,
): { start: Date; end: Date } {
  // Get the date string in the practice timezone for the given Date
  const dateStr = isoToDateInTz(date.toISOString(), timezone);
  // Midnight in practice TZ → UTC
  const startUtc = localInputToUTC(dateStr, "00:00", timezone);
  // End of day: use next day midnight
  const [y, m, d] = dateStr.split("-").map(Number);
  const nextDay = new Date(Date.UTC(y!, m! - 1, d! + 1));
  const nextDateStr = `${nextDay.getUTCFullYear()}-${String(nextDay.getUTCMonth() + 1).padStart(2, "0")}-${String(nextDay.getUTCDate()).padStart(2, "0")}`;
  const endUtc = localInputToUTC(nextDateStr, "00:00", timezone);

  return {
    start: new Date(startUtc),
    end: new Date(endUtc),
  };
}

/**
 * Convert a Date object to "YYYY-MM-DD" in the given IANA timezone.
 */
export function toDateStringInTz(date: Date, timezone: string): string {
  return isoToDateInTz(date.toISOString(), timezone);
}

/**
 * Extract hours and minutes from a Date object in the given IANA timezone.
 * Returns "HH:mm" format. Used when FullCalendar provides a Date from a click.
 */
export function dateToTimeInTz(date: Date, timezone: string): string {
  return isoToTimeInTz(date.toISOString(), timezone);
}
