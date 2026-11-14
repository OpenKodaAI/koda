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
        } catch {
          currentInterval = Math.min(
            currentInterval * BACKOFF_MULTIPLIER,
            MAX_INTERVAL_MS
          );
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

/**
 * EventSource cannot read HTTP status codes: any failed stream request reaches
 * the client as a bare `error` event, and the runtime hooks reconnect with it.
 * When the runtime itself rejects the stream request (for example an invalid
 * `after_seq` cursor), repeating it unchanged fails the same way. The runtime
 * stream relays therefore deliver such a rejection in-band, as this named event
 * on a 200 event stream, and clients then retry only after
 * `STREAM_REJECTED_RETRY_MS` instead of on their normal reconnect schedule.
 */
export const STREAM_ERROR_EVENT = "stream_error";

/**
 * Delay before a client retries a rejected stream request. Long enough not to
 * hammer the relay, short enough to recover once the cause has been fixed.
 */
export const STREAM_REJECTED_RETRY_MS = 60_000;

export interface StreamErrorPayload {
  status: number;
  error: string;
}

export const SSE_RESPONSE_HEADERS = {
  "Content-Type": "text/event-stream; charset=utf-8",
  "Cache-Control": "no-cache, no-transform",
  Connection: "keep-alive",
  "X-Accel-Buffering": "no",
} as const;

const MAX_STREAM_ERROR_LENGTH = 300;

/**
 * Statuses that mean the runtime rejected the stream request itself. Apply this
 * only to a response the runtime returned. Everything else is transient: auth
 * failures (401/403 usually mean the relay could not obtain a runtime token
 * from the control plane), 408/425/429, 5xx, and any failure raised before the
 * runtime answered.
 */
const REJECTED_STREAM_STATUSES: ReadonlySet<number> = new Set([400, 404, 422]);

export function isRejectedStreamStatus(status: number): boolean {
  return REJECTED_STREAM_STATUSES.has(status);
}

/** Readable message from an upstream error body: JSON `{ error }` or plain text. */
export function upstreamStreamErrorMessage(body: string, status: number): string {
  let message = body.trim();
  try {
    const parsed: unknown = JSON.parse(message);
    const error =
      parsed && typeof parsed === "object" ? (parsed as { error?: unknown }).error : undefined;
    if (typeof error === "string") {
      message = error.trim();
    } else if (error && typeof error === "object") {
      const nested = (error as { message?: unknown }).message;
      if (typeof nested === "string") message = nested.trim();
    }
  } catch {
    // Plain-text body, e.g. aiohttp's `invalid after_seq`.
  }
  return (message || `Runtime stream request failed (${status})`).slice(
    0,
    MAX_STREAM_ERROR_LENGTH,
  );
}

/**
 * A finished event stream that carries one `stream_error` event. The `retry`
 * hint makes a plain EventSource that ignores the event wait just as long.
 */
export function streamErrorResponse(status: number, error: string): Response {
  const payload: StreamErrorPayload = { status, error };
  const body =
    `retry: ${STREAM_REJECTED_RETRY_MS}\n` +
    `event: ${STREAM_ERROR_EVENT}\ndata: ${JSON.stringify(payload)}\n\n`;
  return new Response(body, { status: 200, headers: SSE_RESPONSE_HEADERS });
}

/** Parse a `stream_error` event; `null` when its data is malformed. */
export function readStreamError(event: Event): StreamErrorPayload | null {
  const data = (event as MessageEvent).data;
  if (typeof data !== "string") return null;
  try {
    const parsed: unknown = JSON.parse(data);
    if (!parsed || typeof parsed !== "object") return null;
    const { status, error } = parsed as Partial<StreamErrorPayload>;
    if (typeof status !== "number" || typeof error !== "string") return null;
    return { status, error };
  } catch {
    return null;
  }
}
