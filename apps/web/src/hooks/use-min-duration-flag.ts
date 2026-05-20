"use client";

/* eslint-disable react-hooks/set-state-in-effect */

import { useEffect, useRef, useState } from "react";

/**
 * Holds a boolean flag `true` for at least `minMs` after it first becomes true,
 * so transient loading states stay visible long enough for the user to see
 * (and don't flash on/off when data arrives faster than the eye can perceive).
 *
 * Returns the held flag. Once `active` flips false, the hook keeps the flag
 * true until the minimum duration has elapsed, then releases it.
 */
export function useMinDurationFlag(active: boolean, minMs: number): boolean {
  const [held, setHeld] = useState(active);
  const startedAtRef = useRef<number | null>(null);

  useEffect(() => {
    if (active) {
      if (startedAtRef.current === null) {
        startedAtRef.current = Date.now();
      }
      if (!held) setHeld(true);
      return;
    }

    if (startedAtRef.current === null) {
      if (held) setHeld(false);
      return;
    }

    const elapsed = Date.now() - startedAtRef.current;
    if (elapsed >= minMs) {
      startedAtRef.current = null;
      if (held) setHeld(false);
      return;
    }

    const remaining = minMs - elapsed;
    const timer = window.setTimeout(() => {
      startedAtRef.current = null;
      setHeld(false);
    }, remaining);
    return () => window.clearTimeout(timer);
  }, [active, minMs, held]);

  return held;
}
