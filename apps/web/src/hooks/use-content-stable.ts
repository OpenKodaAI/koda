"use client";

import { useMemo } from "react";

/**
 * Stabilizes a value's identity across renders by content equality.
 * If the new value serializes identically to the last render, the previous
 * reference is preserved. Protects downstream `useMemo` / `React.memo` chains
 * from reference-churn when the backend returns structurally-identical
 * payloads with drifting object identities (which can defeat React Query's
 * structuralSharing for some payload shapes).
 */
export function useContentStable<T>(value: T): T {
  const key = value === undefined ? "__undef__" : JSON.stringify(value);
  // `useMemo` with a string key returns the cached value when content matches,
  // giving us a stable reference across polling refetches.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => value, [key]);
}
