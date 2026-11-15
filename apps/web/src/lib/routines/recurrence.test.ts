import { describe, expect, it } from "vitest";
import { utcToZonedWallTime, zonedWallTimeToUtc } from "@/lib/routines/recurrence";

// D-081: one-shot times are wall-clock times in the routine's zone, not the browser's.
describe("zoned wall time", () => {
  it.each([
    ["2026-12-01T09:00", "Asia/Tokyo", "2026-12-01T00:00:00.000Z"],
    ["2026-12-01T09:00", "America/Sao_Paulo", "2026-12-01T12:00:00.000Z"],
    ["2026-07-01T09:00", "America/New_York", "2026-07-01T13:00:00.000Z"],
    ["2026-12-01T09:00", "America/New_York", "2026-12-01T14:00:00.000Z"],
    ["2026-12-01T09:00", "Asia/Kolkata", "2026-12-01T03:30:00.000Z"],
    ["2026-12-01T09:00", "UTC", "2026-12-01T09:00:00.000Z"],
  ])("reads %s in %s as %s", (wall, timeZone, iso) => {
    expect(zonedWallTimeToUtc(wall, timeZone).toISOString()).toBe(iso);
    expect(utcToZonedWallTime(new Date(iso), timeZone)).toBe(wall);
  });

  it("rejects a malformed wall time", () => {
    expect(Number.isNaN(zonedWallTimeToUtc("tomorrow", "UTC").getTime())).toBe(true);
  });
});
