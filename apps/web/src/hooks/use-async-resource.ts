"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { AsyncResourceState } from "@/lib/async-ui";
import { isAbortError, toErrorMessage } from "@/lib/http-client";
import { usePageVisibility } from "@/hooks/use-page-visibility";

type UseAsyncResourceOptions<T> = {
  enabled?: boolean;
  initialData?: T | null;
  pollIntervalMs?: number | null;
  pauseWhenHidden?: boolean;
  fetcher: (signal: AbortSignal) => Promise<T>;
  onSuccess?: (data: T) => void;
  onError?: (message: string) => void;
};

type RefreshOptions = {
  background?: boolean;
  preserveError?: boolean;
};

export function useAsyncResource<T>({
  enabled = true,
  initialData = null,
  pollIntervalMs = null,
  pauseWhenHidden = true,
  fetcher,
  onSuccess,
  onError,
}: UseAsyncResourceOptions<T>) {
  const isVisible = usePageVisibility();
  const [state, setState] = useState<AsyncResourceState<T>>({
    data: initialData,
    initialLoading: enabled && !initialData,
    refreshing: false,
    error: null,
    lastUpdated: null,
  });

  const fetcherRef = useRef(fetcher);
  const controllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const dataRef = useRef<T | null>(initialData);

  useEffect(() => {
    fetcherRef.current = fetcher;
  }, [fetcher]);

  useEffect(() => {
    dataRef.current = state.data;
  }, [state.data]);

  const refresh = useCallback(
    async ({ background = false, preserveError = false }: RefreshOptions = {}) => {
      if (!enabled) {
        controllerRef.current?.abort();
        setState({
          data: null,
          initialLoading: false,
          refreshing: false,
          error: null,
          lastUpdated: null,
        });
        return null;
      }

      requestIdRef.current += 1;
      const requestId = requestIdRef.current;
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      const hasData = Boolean(dataRef.current);
      setState((current) => ({
        ...current,
        initialLoading: !background && !hasData,
        refreshing: background || hasData,
        error: preserveError ? current.error : null,
      }));

      try {
        const data = await fetcherRef.current(controller.signal);
        if (requestId !== requestIdRef.current || controller.signal.aborted) {
          return null;
        }

        dataRef.current = data;
        setState({
          data,
          initialLoading: false,
          refreshing: false,
          error: null,
          lastUpdated: Date.now(),
        });
        onSuccess?.(data);
        return data;
      } catch (error) {
        if (requestId !== requestIdRef.current || isAbortError(error)) {
          return null;
        }

        const message = toErrorMessage(error, "Falha ao carregar dados.");
        setState((current) => ({
          data: current.data,
          initialLoading: false,
          refreshing: false,
          error: current.data ? current.error : message,
          lastUpdated: current.lastUpdated,
        }));
        onError?.(message);
        return null;
      } finally {
        if (controllerRef.current === controller) {
          controllerRef.current = null;
        }
      }
    },
    [enabled, onError, onSuccess],
  );

  const setData = useCallback(
    (updater: T | null | ((current: T | null) => T | null)) => {
      setState((current) => {
        const nextData =
          typeof updater === "function"
            ? (updater as (current: T | null) => T | null)(current.data)
            : updater;
        dataRef.current = nextData;
        return {
          ...current,
          data: nextData,
        };
      });
    },
    [],
  );

  useEffect(() => {
    void refresh();
    return () => {
      controllerRef.current?.abort();
    };
  }, [refresh]);

  useEffect(() => {
    if (!pollIntervalMs) {
      return () => undefined;
    }

    if (pauseWhenHidden && !isVisible) {
      return () => undefined;
    }

    const interval = window.setInterval(() => {
      void refresh({ background: true, preserveError: true });
    }, pollIntervalMs);

    return () => {
      window.clearInterval(interval);
    };
  }, [isVisible, pauseWhenHidden, pollIntervalMs, refresh]);

  return {
    ...state,
    refresh,
    setData,
  };
}
