"use client";

import { useEffect, useState } from "react";

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

/**
 * Open an SSE stream to ``/api/control-plane/dashboard/squads/threads/{id}/events``
 * and dispatch each parsed event to ``onEvent``. Returns the connection status
 * so the UI can render a live indicator.
 *
 * EventSource is closed on unmount and reopened automatically on threadId change.
 */
export function useSquadThreadEvents({
  threadId,
  onEvent,
  enabled = true,
}: UseSquadThreadEventsOptions): SquadThreadEventStatus {
  const canStream = enabled && typeof window !== "undefined" && typeof EventSource !== "undefined";
  const [status, setStatus] = useState<SquadThreadEventStatus>(canStream ? "connecting" : "idle");

  useEffect(() => {
    if (!canStream) {
      return;
    }
    const url = `/api/control-plane/dashboard/squads/threads/${encodeURIComponent(threadId)}/events`;
    const source = new EventSource(url);

    const handleEvent = (event: MessageEvent) => {
      let parsed: SquadThreadEvent | null = null;
      try {
        parsed = JSON.parse(event.data) as SquadThreadEvent;
      } catch {
        return;
      }
      if (parsed && parsed.thread_id === threadId) {
        onEvent(parsed);
      }
    };
    const handleOpen = () => setStatus("open");
    const handleError = () => setStatus("error");

    source.addEventListener("open", handleOpen);
    source.addEventListener("message_added", handleEvent);
    source.addEventListener("reply_added", handleEvent);
    source.addEventListener("reply_obligation_updated", handleEvent);
    source.addEventListener("synthesis_created", handleEvent);
    source.addEventListener("task_updated", handleEvent);
    source.addEventListener("update", handleEvent);
    source.addEventListener("error", handleError);

    return () => {
      source.close();
    };
  }, [threadId, canStream, onEvent]);

  return status;
}
