import { describe, it, expect } from "vitest";

import { lastStatementLabel, statementFilename } from "@/lib/api/statements";

describe("statementFilename", () => {
  it("uses the date part of the ISO timestamp", () => {
    expect(statementFilename("2026-09-18T12:00:00Z")).toBe("statement-2026-09-18.pdf");
  });
});

describe("lastStatementLabel", () => {
  const now = new Date("2026-09-18T15:00:00Z");

  it("is Never for null", () => {
    expect(lastStatementLabel(null, now)).toBe("Never");
  });

  it("is Today within the same calendar day", () => {
    expect(lastStatementLabel("2026-09-18T01:00:00Z", now)).toBe("Today");
  });

  it("singular and plural days", () => {
    expect(lastStatementLabel("2026-09-17T12:00:00Z", now)).toBe("1 day ago");
    expect(lastStatementLabel("2026-09-15T12:00:00Z", now)).toBe("3 days ago");
  });

  it("switches to weeks after 13 days", () => {
    expect(lastStatementLabel("2026-09-04T12:00:00Z", now)).toBe("2 weeks ago");
  });

  it("switches to months after 8 weeks", () => {
    expect(lastStatementLabel("2026-06-01T12:00:00Z", now)).toBe("3 months ago");
  });
});
