"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { StorageCodec } from "@/lib/contracts/storage";
import {
  safeLocalStorageGet,
  safeLocalStorageGetValue,
  safeLocalStorageSet,
  safeLocalStorageSetValue,
} from "@/lib/browser-storage";

/**
 * SSR-safe localStorage hook with the same API as useState.
 * Reads from localStorage on mount (client only) and writes on every change.
 */
export function useLocalStorage<T>(
  key: string,
  defaultValue: T,
  codec?: StorageCodec<T>,
): [T, (value: T | ((prev: T) => T)) => void] {
  const [state, setState] = useState<T>(defaultValue);
  const hydrated = useRef(false);

  useEffect(() => {
    try {
      if (codec) {
        setState(safeLocalStorageGetValue(codec));
      } else {
        const raw = safeLocalStorageGet(key);
        if (raw !== null) {
          setState(JSON.parse(raw) as T);
        }
      }
    } catch {
      // Best-effort — ignore malformed or unavailable storage
    } finally {
      hydrated.current = true;
    }
  }, [codec, key]);

  // Persist to localStorage only after the first client-side read.
  useEffect(() => {
    if (!hydrated.current) return;
    if (codec) {
      safeLocalStorageSetValue(codec, state);
      return;
    }

    safeLocalStorageSet(key, JSON.stringify(state));
  }, [codec, key, state]);

  const setValue = useCallback(
    (value: T | ((prev: T) => T)) => {
      setState(value);
    },
    [],
  );

  return [state, setValue];
}
