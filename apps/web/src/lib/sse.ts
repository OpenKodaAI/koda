function simpleHash(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0;
  }
  return hash;
}

const BACKOFF_MULTIPLIER = 1.5;
const MAX_INTERVAL_MS = 15000;
const HEARTBEAT_INTERVAL_MS = 30000;

export function createSSEStream(
  pollFn: () => Promise<Record<string, unknown>>,
  intervalMs: number = 2000
): ReadableStream {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let lastHash: number | null = null;
  let lastStr: string | null = null;
  let cancelled = false;

  return new ReadableStream({
    start(controller) {
      const encoder = new TextEncoder();

      const send = (event: string, data: unknown) => {
        controller.enqueue(
          encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
        );
      };

      let currentInterval = intervalMs;
      let lastHeartbeat = Date.now();

      const tick = async () => {
        if (cancelled) return;

        try {
          const now = Date.now();

          // Heartbeat every 30s regardless of adaptive interval
          if (now - lastHeartbeat >= HEARTBEAT_INTERVAL_MS) {
            send("heartbeat", { ts: now });
            lastHeartbeat = now;
          }

          const state = await pollFn();
          const stateStr = JSON.stringify(state);
          const stateHash = simpleHash(stateStr);

          // Use hash for fast-path comparison; fall back to string equality
          // when hashes match to avoid missed updates from DJB2 collisions.
          if (stateHash !== lastHash || (lastStr !== null && stateStr !== lastStr)) {
            lastHash = stateHash;
            lastStr = stateStr;
            send("update", state);
            // Change detected: reset to base interval
            currentInterval = intervalMs;
          } else {
            // No change: increase interval with backoff
            currentInterval = Math.min(
              currentInterval * BACKOFF_MULTIPLIER,
              MAX_INTERVAL_MS
            );
          }
        } catch (error) {
          console.error("SSE poll error:", error);
        }

        if (!cancelled) {
          timer = setTimeout(tick, currentInterval);
        }
      };

      timer = setTimeout(tick, 0);
    },
    cancel() {
      cancelled = true;
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
    },
  });
}
