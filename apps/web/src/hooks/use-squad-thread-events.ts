"use client";

import { useEffect, useRef, useState } from "react";

export type SquadThreadEvent = {
  thread_id: string;
  event_type: string;
  data?: Record<string, unknown>;
};

export type UseSquadThreadEventsOptions = {
  threadId: string;
  onEvent: (event: SquadThreadEvent) => void;
  /** When false the EventSource is not opened — useful for SSR / disabled state. */
  enabled?: boolean;
};

export type SquadThreadEventStatus = "idle" | "connecting" | "open" | "error";

const BASE_RECONNECT_MS = 2_000;
const MAX_RECONNECT_MS = 30_000;
const MAX_RECONNECT_ATTEMPTS = 4;

/**
 * Open an SSE stream to ``/api/control-plane/dashboard/squads/threads/{id}/events``
 * and dispatch each parsed event to ``onEvent``. Returns the connection status
 * so the UI can render a live indicator.
 *
 * EventSource is closed on unmount and reopened with bounded backoff on
 * transient errors. The room detail query still polls, so a dead stream should
 * not create an endless browser-level retry loop.
 */
export function useSquadThreadEvents({
  threadId,
  onEvent,
  enabled = true,
}: UseSquadThreadEventsOptions): SquadThreadEventStatus {
  const canStream = enabled && typeof window !== "undefined" && typeof EventSource !== "undefined";
  const [status, setStatus] = useState<SquadThreadEventStatus>(canStream ? "connecting" : "idle");
  const onEventRef = useRef(onEvent);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!canStream || !threadId) {
      return;
    }
    const url = `/api/control-plane/dashboard/squads/threads/${encodeURIComponent(threadId)}/events`;
    let disposed = false;
    let source: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;

    const connect = () => {
      if (disposed) return;
      setStatus("connecting");

      const nextSource = new EventSource(url);
      source = nextSource;

      const handleEvent = (event: MessageEvent) => {
        if (disposed) return;
        let parsed: SquadThreadEvent | null = null;
        try {
          parsed = JSON.parse(event.data) as SquadThreadEvent;
        } catch {
          return;
        }
        if (parsed && parsed.thread_id === threadId) {
          onEventRef.current(parsed);
        }
      };
      const handleOpen = () => {
        if (disposed) return;
        attempt = 0;
        setStatus("open");
      };
      const handleError = () => {
        if (disposed) return;
        nextSource.close();
        if (source === nextSource) {
          source = null;
        }
        setStatus("error");
        if (attempt >= MAX_RECONNECT_ATTEMPTS) {
          return;
        }
        const delay = Math.min(
          BASE_RECONNECT_MS * 2 ** attempt,
          MAX_RECONNECT_MS,
        );
        attempt += 1;
        reconnectTimer = setTimeout(connect, delay);
      };

      nextSource.addEventListener("open", handleOpen);
      nextSource.addEventListener("message_added", handleEvent);
      nextSource.addEventListener("reply_added", handleEvent);
      nextSource.addEventListener("reply_obligation_updated", handleEvent);
      nextSource.addEventListener("synthesis_created", handleEvent);
      nextSource.addEventListener("task_updated", handleEvent);
      nextSource.addEventListener("update", handleEvent);
      nextSource.addEventListener("error", handleError);
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
      }
      if (source) {
        source.close();
      }
    };
  }, [threadId, canStream]);

  return canStream && threadId ? status : "idle";
}
