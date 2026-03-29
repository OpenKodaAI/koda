"use client";

import { useState, useEffect, useRef, useCallback } from "react";

export function useSSE(botId: string, enabled: boolean = true) {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [connected, setConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cleanup = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!enabled || !botId) {
      cleanup();
      return;
    }

    function connect() {
      cleanup();

      const es = new EventSource(`/api/runtime/bots/${botId}/stream`);
      eventSourceRef.current = es;

      es.onopen = () => {
        setConnected(true);
      };

      es.addEventListener("update", (event: MessageEvent) => {
        try {
          const parsed = JSON.parse(event.data);
          setData(parsed);
        } catch {
          // Ignore malformed JSON
        }
      });

      es.addEventListener("heartbeat", () => {
        // Keep-alive; no action needed
      });

      es.onerror = () => {
        setConnected(false);
        es.close();
        eventSourceRef.current = null;

        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, 3000);
      };
    }

    connect();

    return () => {
      cleanup();
    };
  }, [botId, enabled, cleanup]);

  return { data, connected };
}
