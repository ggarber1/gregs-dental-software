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

/**
 * Add (or subtract, via negative value) calendar months to a "YYYY-MM-DD" date
 * string. Pure wall-clock math — operates on the string parts directly so there
 * is no UTC or DST drift. When the target month has fewer days than the source
 * day, the result clamps to the last day of the target month (Jan 31 + 1mo →
 * Feb 28 in a non-leap year, Feb 29 in a leap year).
 *
 * Throws on inputs that don't match "YYYY-MM-DD" (boundary validation).
 */
export function addMonthsLocal(dateStr: string, months: number): string {
  if (!Number.isInteger(months)) {
    throw new Error(`addMonthsLocal: months must be an integer, got ${months}`);
  }
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr);
  if (!match) {
    throw new Error(`addMonthsLocal: expected "YYYY-MM-DD", got ${dateStr}`);
  }
  const year = Number(match[1]);
  const month = Number(match[2]); // 1-12
  const day = Number(match[3]); // 1-31
  if (month < 1 || month > 12 || day < 1 || day > 31) {
    throw new Error(`addMonthsLocal: invalid date ${dateStr}`);
  }

  // Shift into 0-indexed month math for easy modulo handling of year rollover.
  const totalMonths = year * 12 + (month - 1) + months;
  const newYear = Math.floor(totalMonths / 12);
  const newMonth = (totalMonths % 12) + 1; // back to 1-12

  const lastDay = daysInMonth(newYear, newMonth);
  const newDay = Math.min(day, lastDay);

  return `${String(newYear).padStart(4, "0")}-${String(newMonth).padStart(2, "0")}-${String(newDay).padStart(2, "0")}`;
}

function daysInMonth(year: number, month: number): number {
  // month is 1-12
  if (month === 2) {
    const leap = (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
    return leap ? 29 : 28;
  }
  if (month === 4 || month === 6 || month === 9 || month === 11) return 30;
  return 31;
}
