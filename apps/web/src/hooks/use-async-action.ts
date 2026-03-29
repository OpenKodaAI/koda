"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useToast } from "@/hooks/use-toast";
import type { AsyncActionOptions, AsyncActionState } from "@/lib/async-ui";
import { isAbortError, toErrorMessage } from "@/lib/http-client";

type StatusMap = Record<string, AsyncActionState>;

export function useAsyncAction() {
  const { showToast } = useToast();
  const [statusMap, setStatusMap] = useState<StatusMap>({});
  const [pendingKeys, setPendingKeys] = useState<string[]>([]);
  const pendingRef = useRef(new Set<string>());
  const resetTimersRef = useRef<Record<string, number>>({});

  useEffect(() => {
    const resetTimers = resetTimersRef.current;
    return () => {
      Object.values(resetTimers).forEach((timer) => {
        window.clearTimeout(timer);
      });
    };
  }, []);

  const setStatus = useCallback((key: string, status: AsyncActionState) => {
    setStatusMap((current) => ({ ...current, [key]: status }));
  }, []);

  const clearStatus = useCallback((key: string) => {
    window.clearTimeout(resetTimersRef.current[key]);
    delete resetTimersRef.current[key];
    setStatusMap((current) => {
      if (!(key in current)) return current;
      const next = { ...current };
      delete next[key];
      return next;
    });
  }, []);

  const runAction = useCallback(
    async <T,>(
      key: string,
      action: () => Promise<T>,
      options: AsyncActionOptions<T> = {},
    ): Promise<T | undefined> => {
      if (pendingRef.current.has(key)) {
        return undefined;
      }

      pendingRef.current.add(key);
      setPendingKeys((current) => [...current, key]);
      setStatus(key, "pending");

      if (options.policy === "optimistic") {
        options.optimisticUpdate?.();
      }

      try {
        const result = await action();
        await options.onSuccess?.(result);

        if (!options.silentSuccess && options.successMessage) {
          showToast(options.successMessage, "success");
        }

        setStatus(key, "success");
        const resetAfter = options.resetStatusAfterMs ?? 1600;
        resetTimersRef.current[key] = window.setTimeout(
          () => clearStatus(key),
          resetAfter,
        );

        return result;
      } catch (error) {
        if (options.policy === "optimistic") {
          options.rollbackOptimistic?.();
        }

        if (!isAbortError(error)) {
          const normalized = new Error(
            toErrorMessage(
              error,
              options.errorMessage ?? "Ocorreu um erro inesperado.",
            ),
          );
          await options.onError?.(normalized);
          if (!options.silentError) {
            showToast(normalized.message, "error");
          }
          setStatus(key, "error");
          resetTimersRef.current[key] = window.setTimeout(
            () => clearStatus(key),
            options.resetStatusAfterMs ?? 2200,
          );
        } else {
          clearStatus(key);
        }
        return undefined;
      } finally {
        pendingRef.current.delete(key);
        setPendingKeys((current) => current.filter((item) => item !== key));
        await options.onSettled?.();
      }
    },
    [clearStatus, setStatus, showToast],
  );

  const isPending = useCallback(
    (key?: string) => {
      if (!key) return pendingKeys.length > 0;
      return pendingRef.current.has(key);
    },
    [pendingKeys.length],
  );

  const getStatus = useCallback(
    (key: string): AsyncActionState => statusMap[key] ?? "idle",
    [statusMap],
  );

  return {
    runAction,
    pendingKeys,
    isPending,
    getStatus,
    clearStatus,
  };
}
