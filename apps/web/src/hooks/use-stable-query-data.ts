"use client";

/* eslint-disable react-hooks/refs */

import { useMemo, useRef } from "react";

type StableQueryDataOptions<T> = {
  data: T | null | undefined;
  resetKey?: unknown;
  isCompatible?: (data: T) => boolean;
  isPending?: boolean;
  isFetching?: boolean;
  error?: unknown;
};

function serializeResetKey(value: unknown): string {
  if (value === undefined) return "__default__";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean" || value === null) {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function useStableQueryData<T>({
  data,
  resetKey,
  isCompatible,
  isPending = false,
  isFetching = false,
  error = null,
}: StableQueryDataOptions<T>) {
  const normalizedResetKey = useMemo(() => serializeResetKey(resetKey), [resetKey]);
  const stateRef = useRef<{ resetKey: string; data: T | null }>({
    resetKey: normalizedResetKey,
    data: null,
  });

  if (stateRef.current.resetKey !== normalizedResetKey) {
    stateRef.current = { resetKey: normalizedResetKey, data: null };
  }

  if (data !== null && data !== undefined && (!isCompatible || isCompatible(data))) {
    stateRef.current.data = data;
  }

  const stableData = stateRef.current.data;
  const hasData = stableData !== null && stableData !== undefined;
  const initialLoading = Boolean(isPending && !hasData);
  const refreshing = Boolean(isFetching && hasData);
  const showBlockingError = Boolean(error && !hasData);

  return {
    data: stableData,
    hasData,
    initialLoading,
    refreshing,
    showBlockingError,
  };
}
