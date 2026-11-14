import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createSlidingWindowLimiter } from "./sliding-window-limiter";

const T0 = Date.UTC(2026, 0, 1);
const MINUTE = 60_000;

describe("createSlidingWindowLimiter", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(T0);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("limits each key within its own sliding window", () => {
    const limiter = createSlidingWindowLimiter({ maxRequests: 2 });

    expect([1, 2, 3].map(() => limiter.isLimited("a"))).toEqual([false, false, true]);
    expect(limiter.isLimited("b")).toBe(false);
    vi.setSystemTime(T0 + MINUTE + 1);
    expect(limiter.isLimited("a")).toBe(false);
  });

  it("prunes its idle clients on its own schedule while another limiter keeps sweeping", () => {
    const loginSession = createSlidingWindowLimiter({ maxRequests: 20 });
    const general = createSlidingWindowLimiter({ maxRequests: 120 });
    for (let n = 0; n < 1000; n += 1) loginSession.isLimited(`2001:db8:0:${n.toString(16)}::/64`);

    vi.setSystemTime(T0 + 5 * MINUTE + 1);
    general.isLimited("198.51.100.1");
    loginSession.isLimited("198.51.100.2");

    expect(loginSession.size).toBe(1);
  });

  it("sweeps at most once per interval rather than on every request", () => {
    const limiter = createSlidingWindowLimiter({ maxRequests: 20 });
    vi.setSystemTime(T0 + 5 * MINUTE + 1);
    for (let n = 0; n < 1000; n += 1) limiter.isLimited(`key-${n}`);

    // Idle for three minutes, so stale, but the next sweep is not due yet.
    vi.setSystemTime(T0 + 8 * MINUTE);
    limiter.isLimited("late");
    expect(limiter.size).toBe(1001);

    vi.setSystemTime(T0 + 10 * MINUTE + 2);
    limiter.isLimited("later");
    expect(limiter.size).toBe(1);
  });

  it("tracks at most maxClients, dropping the least recently seen first", () => {
    const limiter = createSlidingWindowLimiter({ maxRequests: 1, maxClients: 3 });
    for (const key of ["a", "b", "c"]) limiter.isLimited(key);
    expect(limiter.isLimited("a")).toBe(true);

    limiter.isLimited("d");

    expect(limiter.size).toBe(3);
    expect(limiter.isLimited("a")).toBe(true);
    // "b" was the least recently seen, so it starts a new window.
    expect(limiter.isLimited("b")).toBe(false);
    expect(limiter.size).toBe(3);
  });
});
