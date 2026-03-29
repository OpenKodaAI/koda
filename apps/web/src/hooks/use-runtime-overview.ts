"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useBotCatalog } from "@/components/providers/bot-catalog-provider";
import { useAsyncResource } from "@/hooks/use-async-resource";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { resolveBotSelection } from "@/lib/bot-selection";
import { parseResponseError, readJsonResponse } from "@/lib/http-client";
import type { RuntimeEvent, RuntimeOverview } from "@/lib/runtime-types";

interface UseRuntimeOverviewResult {
  overviews: Record<string, RuntimeOverview>;
  loading: boolean;
  refreshing: boolean;
  connected: Record<string, boolean>;
  error: string | null;
  refreshBot: (botId: string) => Promise<void>;
  lastUpdated: number | null;
}

export function useRuntimeOverview(selectedBotIds?: string[]): UseRuntimeOverviewResult {
  const { language } = useAppI18n();
  const { bots } = useBotCatalog();
  const availableBotIds = useMemo(() => bots.map((bot) => bot.id), [bots]);
  const visibleBotIds = useMemo(
    () => resolveBotSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds]
  );
  const [connected, setConnected] = useState<Record<string, boolean>>({});
  const lastSeqRef = useRef<Record<string, number>>({});
  const refreshTimersRef = useRef<Record<string, number>>({});
  const didInitialFetchRef = useRef(false);
  const fetchBotOverview = useCallback(async (botId: string, signal?: AbortSignal) => {
    const params = new URLSearchParams({ lang: language });
    const response = await fetch(`/api/runtime/bots/${botId}/overview?${params.toString()}`, {
      cache: "no-store",
      signal,
    });

    if (!response.ok) {
      throw new Error(
        await parseResponseError(
          response,
          `Erro ao carregar runtime do bot ${botId}`,
        ),
      );
    }

    return readJsonResponse<RuntimeOverview>(response);
  }, [language]);

  const resource = useAsyncResource<Record<string, RuntimeOverview>>({
    enabled: visibleBotIds.length > 0,
    initialData: {},
    pollIntervalMs: 20_000,
    fetcher: async (signal) => {
      const entries = await Promise.all(
        visibleBotIds.map(async (botId) => [botId, await fetchBotOverview(botId, signal)] as const),
      );
      return Object.fromEntries(entries);
    },
  });
  const {
    data,
    error,
    initialLoading,
    lastUpdated,
    refresh,
    refreshing,
    setData,
  } = resource;
  const overviews = useMemo(() => data ?? {}, [data]);
  const visibleBotKey = useMemo(() => visibleBotIds.join(","), [visibleBotIds]);
  const streamBotIds = useMemo(
    () =>
      visibleBotIds.filter(
        (botId) => overviews[botId]?.availability.runtime === "available"
      ),
    [overviews, visibleBotIds]
  );
  const streamKey = streamBotIds.join(",");

  useEffect(() => {
    if (!didInitialFetchRef.current) {
      didInitialFetchRef.current = true;
      return;
    }

    if (visibleBotIds.length === 0) return;
    void refresh();
  }, [language, refresh, visibleBotIds.length, visibleBotKey]);

  useEffect(() => {
    let disposed = false;
    const reconnectTimers: number[] = [];
    const sources: EventSource[] = [];
    const refreshTimers = refreshTimersRef.current;
    const activeStreamBotIds = streamKey ? streamKey.split(",") : [];

    if (activeStreamBotIds.length === 0) {
      return () => undefined;
    }

    const scheduleRefresh = (botId: string) => {
      window.clearTimeout(refreshTimers[botId]);
      refreshTimers[botId] = window.setTimeout(() => {
        void fetchBotOverview(botId)
          .then((payload) => {
            setData((current) => ({
              ...(current ?? {}),
              [botId]: payload,
            }));
          })
          .catch(() => undefined);
      }, 220);
    };

    const connectBot = (botId: string) => {
      if (disposed) return;
      const es = new EventSource(
        `/api/runtime/bots/${botId}/stream?after_seq=${lastSeqRef.current[botId] ?? 0}`
      );
      sources.push(es);

      es.onopen = () => {
        setConnected((current) => ({ ...current, [botId]: true }));
      };

      es.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as RuntimeEvent;
          if (typeof payload.seq === "number") {
            lastSeqRef.current[botId] = Math.max(
              lastSeqRef.current[botId] ?? 0,
              payload.seq
            );
          }
          scheduleRefresh(botId);
        } catch {
          // Ignore malformed stream events.
        }
      };

      es.onerror = () => {
        setConnected((current) => ({ ...current, [botId]: false }));
        es.close();
        if (!disposed) {
          reconnectTimers.push(window.setTimeout(() => connectBot(botId), 3000));
        }
      };
    };

    activeStreamBotIds.forEach((botId) => connectBot(botId));

    return () => {
      disposed = true;
      sources.forEach((source) => source.close());
      reconnectTimers.forEach((timer) => window.clearTimeout(timer));
      Object.values(refreshTimers).forEach((timer) => window.clearTimeout(timer));
    };
  }, [fetchBotOverview, setData, streamKey]);

  return {
    overviews,
    loading: initialLoading || visibleBotIds.some((botId) => !overviews[botId]),
    refreshing,
    connected,
    error,
    refreshBot: async (botId) => {
      const payload = await fetchBotOverview(botId);
      setData((current) => ({
        ...(current ?? {}),
        [botId]: payload,
      }));
    },
    lastUpdated,
  };
}
