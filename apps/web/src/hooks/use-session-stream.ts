"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { isSessionStreamEvent, type SessionStreamEvent } from "@/lib/contracts/sessions";

interface UseSessionStreamOptions {
  agentId: string | null | undefined;
  sessionId: string | null | undefined;
  enabled?: boolean;
  onEvent?: (event: SessionStreamEvent) => void;
}

interface UseSessionStreamResult {
  connected: boolean;
  lastEvent: SessionStreamEvent | null;
  error: string | null;
  reconnect: () => void;
}

const BASE_RECONNECT_MS = 1_500;
const MAX_RECONNECT_MS = 15_000;

export function useSessionStream({
  agentId,
  sessionId,
  enabled = true,
  onEvent,
}: UseSessionStreamOptions): UseSessionStreamResult {
  const [isOpen, setIsOpen] = useState(false);
  const [lastEvent, setLastEvent] = useState<SessionStreamEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reconnectNonce, setReconnectNonce] = useState(0);
  const onEventRef = useRef(onEvent);

  const active = Boolean(enabled && agentId && sessionId);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!active) {
      return;
    }
    if (typeof EventSource === "undefined") {
      return;
    }

    let disposed = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let eventSource: EventSource | null = null;
    let lastSeq = 0;
    let attempt = 0;

    const connect = () => {
      if (disposed) return;
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }

      const query = lastSeq > 0 ? `?after_seq=${lastSeq}` : "";
      const endpoint = `/api/runtime/agents/${encodeURIComponent(
        agentId as string,
      )}/sessions/${encodeURIComponent(sessionId as string)}/stream${query}`;

      const es = new EventSource(endpoint);
      eventSource = es;

      es.onopen = () => {
        if (disposed) return;
        attempt = 0;
        setIsOpen(true);
        setError(null);
      };

      es.onmessage = (messageEvent: MessageEvent) => {
        if (disposed || !messageEvent.data) return;
        let parsed: unknown;
        try {
          parsed = JSON.parse(messageEvent.data);
        } catch {
          return;
        }
        if (!isSessionStreamEvent(parsed)) return;
        if (typeof parsed.seq === "number" && parsed.seq > lastSeq) {
          lastSeq = parsed.seq;
        }
        setLastEvent(parsed);
        onEventRef.current?.(parsed);
      };

      es.onerror = () => {
        if (disposed) return;
        setIsOpen(false);
        es.close();
        eventSource = null;
        attempt += 1;
        const delay = Math.min(
          BASE_RECONNECT_MS * 2 ** Math.max(0, attempt - 1),
          MAX_RECONNECT_MS,
        );
        setError(`stream disconnected (retry in ${Math.round(delay / 1000)}s)`);
        reconnectTimer = setTimeout(() => {
          connect();
        }, delay);
      };
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (eventSource) eventSource.close();
    };
  }, [agentId, sessionId, active, reconnectNonce]);

  const reconnect = useCallback(() => {
    setReconnectNonce((value) => value + 1);
  }, []);

  const connected = useMemo(() => active && isOpen, [active, isOpen]);

  return {
    connected,
    lastEvent,
    error,
    reconnect,
  };
}
