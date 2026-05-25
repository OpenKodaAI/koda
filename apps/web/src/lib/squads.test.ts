import { afterEach, describe, expect, it, vi } from "vitest";

import { formatRelativeTimestamp } from "@/lib/squads";

describe("formatRelativeTimestamp", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns dash for null/empty", () => {
    expect(formatRelativeTimestamp(null)).toBe("—");
    expect(formatRelativeTimestamp("")).toBe("—");
  });

  it("returns dash for invalid timestamps", () => {
    expect(formatRelativeTimestamp("not-a-date")).toBe("—");
  });

  it("formats seconds, minutes, hours, days, months", () => {
    vi.useFakeTimers();
    const now = new Date("2024-06-15T12:00:00Z");
    vi.setSystemTime(now);

    const ago = (offsetMs: number) =>
      new Date(now.getTime() - offsetMs).toISOString();

    expect(formatRelativeTimestamp(ago(5 * 1000))).toBe("5s");
    expect(formatRelativeTimestamp(ago(2 * 60 * 1000))).toBe("2m");
    expect(formatRelativeTimestamp(ago(3 * 60 * 60 * 1000))).toBe("3h");
    expect(formatRelativeTimestamp(ago(2 * 24 * 60 * 60 * 1000))).toBe("2d");
    expect(formatRelativeTimestamp(ago(40 * 24 * 60 * 60 * 1000))).toBe("1mo");
    expect(formatRelativeTimestamp(ago(400 * 24 * 60 * 60 * 1000))).toBe("1y");
  });

  it("returns 'now' for future timestamps", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2024-06-15T12:00:00Z"));
    expect(formatRelativeTimestamp("2024-06-15T13:00:00Z")).toBe("now");
  });
});
