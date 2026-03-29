"use client";

import { useEffect, useState } from "react";

export function useDelayedFlag(active: boolean, delayMs = 120) {
  const [visible, setVisible] = useState(active);

  useEffect(() => {
    if (!active) {
      const timeout = window.setTimeout(() => setVisible(false), 0);
      return () => window.clearTimeout(timeout);
    }

    const resetTimeout = window.setTimeout(() => setVisible(false), 0);
    const timeout = window.setTimeout(() => setVisible(true), delayMs);
    return () => {
      window.clearTimeout(resetTimeout);
      window.clearTimeout(timeout);
    };
  }, [active, delayMs]);

  return active && visible;
}
