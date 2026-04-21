"use client";

import { useEffect, useState } from "react";

interface UseAnimatedPresenceOptions {
  duration?: number;
}

export function useAnimatedPresence<T>(
  isOpen: boolean,
  value: T,
  options: UseAnimatedPresenceOptions = {}
) {
  const { duration = 180 } = options;
  const [shouldRender, setShouldRender] = useState(isOpen);
  const [isVisible, setIsVisible] = useState(isOpen);
  const [renderedValue, setRenderedValue] = useState(value);

  useEffect(() => {
    if (!isOpen) return undefined;

    const frameId = window.requestAnimationFrame(() => {
      setRenderedValue(value);
    });

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [isOpen, value]);

  useEffect(() => {
    let frameId: number | undefined;
    let timeoutId: number | undefined;

    if (isOpen) {
      if (!shouldRender) {
        frameId = window.requestAnimationFrame(() => {
          setShouldRender(true);
        });
      } else {
        frameId = window.requestAnimationFrame(() => {
          setIsVisible(true);
        });
      }
    } else if (shouldRender) {
      frameId = window.requestAnimationFrame(() => {
        setIsVisible(false);
      });
      timeoutId = window.setTimeout(() => {
        setShouldRender(false);
      }, duration);
    }

    return () => {
      if (frameId != null) {
        window.cancelAnimationFrame(frameId);
      }
      if (timeoutId != null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [duration, isOpen, shouldRender]);

  return {
    shouldRender,
    isVisible,
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
