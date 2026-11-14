/**
 * Per-client sliding-window request counters for the Next.js proxy (`proxy.ts`).
 *
 * Each limiter sweeps its own idle windows on its own schedule and tracks at
 * most `maxClients` clients, dropping the least recently seen one first. A
 * flood of distinct clients (a routed IPv6 /48 holds 65,536 /64 keys)
 * therefore costs bounded memory, and no request pays for a full scan.
 */

const SWEEP_INTERVAL_MS = 5 * 60_000;

interface SlidingWindow {
  timestamps: number[];
  updatedAt: number;
}

export interface SlidingWindowLimiterOptions {
  maxRequests: number;
  windowMs?: number;
  maxClients?: number;
}

export interface SlidingWindowLimiter {
  /** Records a request from `key`; true when `key` already used its window. */
  isLimited(key: string): boolean;
  /** Number of clients currently tracked. */
  readonly size: number;
}

export function createSlidingWindowLimiter({
  maxRequests,
  windowMs = 60_000,
  maxClients = 4096,
}: SlidingWindowLimiterOptions): SlidingWindowLimiter {
  // Insertion order is recency order: a request re-inserts its key at the end.
  const windows = new Map<string, SlidingWindow>();
  let lastSweep = Date.now();

  function sweepIdleWindows(now: number) {
    if (now - lastSweep < SWEEP_INTERVAL_MS) return;
    lastSweep = now;
    for (const [key, window] of windows) {
      if (now - window.updatedAt > windowMs * 2) {
        windows.delete(key);
      }
    }
  }

  return {
    get size() {
      return windows.size;
    },
    isLimited(key) {
      const now = Date.now();
      sweepIdleWindows(now);

      const window = windows.get(key) ?? { timestamps: [], updatedAt: now };
      windows.delete(key);
      windows.set(key, window);
      if (windows.size > maxClients) {
        const leastRecent = windows.keys().next().value;
        if (leastRecent !== undefined) windows.delete(leastRecent);
      }

      const cutoff = now - windowMs;
      window.timestamps = window.timestamps.filter((t) => t > cutoff);
      window.updatedAt = now;
      if (window.timestamps.length >= maxRequests) {
        return true;
      }
      window.timestamps.push(now);
      return false;
    },
  };
}
