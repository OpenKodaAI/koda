"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

type UseUrlSyncedSearchOptions = {
  debounceMs?: number;
  initialValue?: string | null;
  param?: string;
  syncToUrl?: boolean;
};

function normalizeSearchValue(value: string | null | undefined) {
  return String(value ?? "").trim();
}

function currentPathWithSearch(url: URL) {
  return `${url.pathname}${url.search}${url.hash}`;
}

export function readCurrentUrlSearchParam(param: string, fallback = "") {
  if (typeof window === "undefined") return fallback;
  return new URL(window.location.href).searchParams.get(param) ?? fallback;
}

export function replaceUrlSearchParamsSilently(
  update: (params: URLSearchParams) => void,
) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  update(url.searchParams);

  const next = currentPathWithSearch(url);
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (next === current) return;

  window.history.replaceState(window.history.state, "", next);
}

export function setUrlSearchParamSilently(
  param: string,
  value: string | null | undefined,
) {
  replaceUrlSearchParamsSilently((params) => {
    const normalized = normalizeSearchValue(value);
    if (normalized) params.set(param, normalized);
    else params.delete(param);
  });
}

export function useUrlSyncedSearch({
  debounceMs = 240,
  initialValue = "",
  param = "search",
  syncToUrl = true,
}: UseUrlSyncedSearchOptions = {}) {
  const fallback = normalizeSearchValue(initialValue);
  const [value, setValue] = useState(() =>
    readCurrentUrlSearchParam(param, fallback),
  );
  const debouncedRawValue = useDebouncedValue(value, debounceMs);
  const debouncedValue = useMemo(
    () => normalizeSearchValue(debouncedRawValue),
    [debouncedRawValue],
  );
  const normalizedValue = normalizeSearchValue(value);
  const isSearching = normalizedValue !== debouncedValue;

  useEffect(() => {
    const handlePopState = () => {
      setValue(readCurrentUrlSearchParam(param, fallback));
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [fallback, param]);

  useEffect(() => {
    if (!syncToUrl) return;
    setUrlSearchParamSilently(param, debouncedValue);
  }, [debouncedValue, param, syncToUrl]);

  const clear = useCallback(() => setValue(""), []);

  return {
    clear,
    debouncedValue,
    isSearching,
    setValue,
    value,
  };
}
