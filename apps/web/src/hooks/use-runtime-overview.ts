"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useBotCatalog } from "@/components/providers/bot-catalog-provider";
import { useRuntimeQuery } from "@/hooks/use-app-query";
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
  const queryClient = useQueryClient();
  const availableBotIds = useMemo(() => bots.map((bot) => bot.id), [bots]);
  const visibleBotIds = useMemo(
    () => resolveBotSelection(selectedBotIds, availableBotIds),
    [availableBotIds, selectedBotIds],
  );
  const [connected, setConnected] = useState<Record<string, boolean>>({});
  const connectedRef = useRef(connected);
  const lastSeqRef = useRef<Record<string, number>>({});
  const didInitialFetchRef = useRef(false);
  const sseDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    connectedRef.current = connected;
  }, [connected]);

  const visibleBotKey = useMemo(() => visibleBotIds.join(","), [visibleBotIds]);
  const visibleBotIdsRef = useRef(visibleBotIds);
  useEffect(() => {
    visibleBotIdsRef.current = visibleBotIds;
  }, [visibleBotIds]);

  const fetchBotOverview = useCallback(
    async (botId: string, signal?: AbortSignal) => {
      const params = new URLSearchParams({ lang: language });
      const response = await fetch(
        `/api/runtime/bots/${botId}/overview?${params.toString()}`,
        { cache: "no-store", signal },
      );

      if (!response.ok) {
        throw new Error(
          await parseResponseError(
            response,
            `Erro ao carregar runtime do bot ${botId}`,
          ),
        );
      }

      return readJsonResponse<RuntimeOverview>(response);
    },
    [language],
  );

  const fetchBatchOverview = useCallback(
    async (botIds: string[], signal?: AbortSignal) => {
      if (botIds.length === 0) return {};

      const params = new URLSearchParams({
        lang: language,
        bots: botIds.join(","),
      });
      const response = await fetch(
        `/api/runtime/bots/overview?${params.toString()}`,
        { cache: "no-store", signal },
      );

      if (!response.ok) {
        throw new Error(
          await parseResponseError(
            response,
            "Erro ao carregar runtime overview em lote",
          ),
        );
      }

      return readJsonResponse<Record<string, RuntimeOverview>>(response);
    },
    [language],
  );

  const overviewQueryKey = useMemo(
    () => ["runtime", "overview-batch", visibleBotKey, language] as const,
    [visibleBotKey, language],
  );
  const overviewQueryKeyRef = useRef(overviewQueryKey);
  useEffect(() => {
    overviewQueryKeyRef.current = overviewQueryKey;
  }, [overviewQueryKey]);

  const overviewQuery = useRuntimeQuery<Record<string, RuntimeOverview>>({
    queryKey: overviewQueryKey,
    enabled: visibleBotIds.length > 0,
    refetchInterval: () => {
      const currentConnected = connectedRef.current;
      const currentBotIds = visibleBotIdsRef.current;
      const streamBots = currentBotIds.filter((id) => currentConnected[id]);
      const allConnected =
        streamBots.length > 0 && streamBots.length === currentBotIds.length;
      // Safety net: keep a slow 60s poll even when all SSE streams are connected
      return allConnected ? 60_000 : 20_000;
    },
    queryFn: async ({ signal }) => fetchBatchOverview(visibleBotIds, signal),
  });

  const overviews = useMemo(
    () => overviewQuery.data ?? {},
    [overviewQuery.data],
  );

  const streamBotIds = useMemo(
    () =>
      visibleBotIds.filter(
        (botId) => overviews[botId]?.availability.runtime === "available",
      ),
    [overviews, visibleBotIds],
  );
  const streamKey = streamBotIds.join(",");

  useEffect(() => {
    if (!didInitialFetchRef.current) {
      didInitialFetchRef.current = true;
      return;
    }

    if (visibleBotIds.length === 0) return;
    void queryClient.invalidateQueries({ queryKey: overviewQueryKey });
  }, [language, queryClient, overviewQueryKey, visibleBotIds.length, visibleBotKey]);

  useEffect(() => {
    let disposed = false;
    const reconnectTimers: number[] = [];
    const sources: EventSource[] = [];
    const activeStreamBotIds = streamKey ? streamKey.split(",") : [];

    if (activeStreamBotIds.length === 0) {
      return () => undefined;
    }

    const scheduleInvalidation = () => {
      if (sseDebounceRef.current) {
        clearTimeout(sseDebounceRef.current);
      }
      sseDebounceRef.current = setTimeout(() => {
        sseDebounceRef.current = null;
        queryClient.invalidateQueries({
          queryKey: overviewQueryKeyRef.current,
        });
      }, 1_000);
    };

    const connectBot = (botId: string) => {
      if (disposed) return;
      const es = new EventSource(
        `/api/runtime/bots/${botId}/stream?after_seq=${lastSeqRef.current[botId] ?? 0}`,
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
              payload.seq,
            );
          }

          // Debounce SSE-triggered invalidation: multiple events within 1s
          // coalesce into a single refetch via TanStack Query deduplication.
          scheduleInvalidation();
        } catch {
          // Ignore malformed stream events.
        }
      };

      es.onerror = () => {
        setConnected((current) => ({ ...current, [botId]: false }));
        es.close();
        if (!disposed) {
          reconnectTimers.push(
            window.setTimeout(() => connectBot(botId), 3000),
          );
        }
      };
    };

    activeStreamBotIds.forEach((botId) => connectBot(botId));

    return () => {
      disposed = true;
      sources.forEach((source) => source.close());
      reconnectTimers.forEach((timer) => window.clearTimeout(timer));
      if (sseDebounceRef.current) {
        clearTimeout(sseDebounceRef.current);
        sseDebounceRef.current = null;
      }
    };
  }, [queryClient, streamKey]);

  return {
    overviews,
    loading:
      overviewQuery.isLoading ||
      visibleBotIds.some((botId) => !overviews[botId]),
    refreshing: overviewQuery.isFetching && !overviewQuery.isLoading,
    connected,
    error: overviewQuery.error?.message ?? null,
    refreshBot: async (botId) => {
      const payload = await fetchBotOverview(botId);
      queryClient.setQueryData(
        overviewQueryKey,
        (current: Record<string, RuntimeOverview> | undefined) => ({
          ...(current ?? {}),
          [botId]: payload,
        }),
      );
    },
    lastUpdated: overviewQuery.dataUpdatedAt || null,
  };
}
