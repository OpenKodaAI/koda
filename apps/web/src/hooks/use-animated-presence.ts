"use client";

import { useEffect, useState } from "react";

interface UseAnimatedPresenceOptions {
  duration?: number;
}

/**
 * Keeps a portal-rendered overlay (modal, drawer, popover) mounted long
 * enough for its CSS exit animation to finish before unmounting.
 *
 * Pair the returned `dataState` with the canonical CSS classes in
 * `apps/web/src/app/globals.css`:
 *
 *   `.app-overlay-anim`, `.app-modal-anim`, `.app-drawer-anim-right`,
 *   `.app-drawer-anim-left`
 *
 * Each class declares a `@keyframes` enter animation that fires on
 * mount, and an exit animation gated by `[data-state="closed"]`. The
 * `duration` here MUST equal the longest exit keyframe duration in CSS,
 * otherwise the element either unmounts mid-animation or sticks around
 * after fade-out completes.
 *
 * `isVisible` is kept for legacy call sites that bind `data-visible` and
 * is just an alias for `isOpen`.
 */
export function useAnimatedPresence<T>(
  isOpen: boolean,
  value: T,
  options: UseAnimatedPresenceOptions = {},
) {
  const { duration = 200 } = options;
  const [shouldRender, setShouldRender] = useState(isOpen);
  const [renderedValue, setRenderedValue] = useState(value);

  // The lint rule discourages calling setState in an effect body, but
  // this hook is mirroring an external prop (`isOpen`) into local
  // mount/unmount state with a delayed exit timer. That's the textbook
  // legitimate use of effect-driven setState: the external system here
  // is "should this overlay still occupy the DOM tree?".
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (isOpen) {
      setShouldRender(true);
      setRenderedValue(value);
      return;
    }
    if (!shouldRender) return;
    const timer = window.setTimeout(() => {
      setShouldRender(false);
    }, duration);
    return () => window.clearTimeout(timer);
  }, [isOpen, value, shouldRender, duration]);
  /* eslint-enable react-hooks/set-state-in-effect */

  return {
    shouldRender,
    isVisible: isOpen,
    dataState: (isOpen ? "open" : "closed") as "open" | "closed",
    renderedValue,
  };
}

export function useBodyScrollLock(active: boolean) {
  useEffect(() => {
    if (!active || typeof document === "undefined") return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [active]);
}

export function useEscapeToClose(active: boolean, onClose: () => void) {
  useEffect(() => {
    if (!active || typeof document === "undefined") return undefined;

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [active, onClose]);
}

export function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;

    const mediaQuery = window.matchMedia(query);
    const updateMatches = () => {
      setMatches(mediaQuery.matches);
    };

    updateMatches();
    mediaQuery.addEventListener("change", updateMatches);

    return () => {
      mediaQuery.removeEventListener("change", updateMatches);
    };
  }, [query]);

  return matches;
}
