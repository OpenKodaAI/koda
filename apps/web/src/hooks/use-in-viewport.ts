"use client";

import { useEffect, useRef, useState, type RefObject } from "react";

interface UseInViewportOptions {
  rootMargin?: string;
  threshold?: number | number[];
  /** Once true, never go back to false. */
  once?: boolean;
}

/**
 * Tracks whether a referenced element is intersecting the viewport.
 *
 * Used to lazy-mount expensive resources (e.g. WebGL `<Canvas>`) only when
 * the host element is on screen, then unmount when it scrolls away — keeping
 * the page under the browser's WebGL context limit (~16 in Chrome) even when
 * a list contains many orb-bearing rows.
 */
export function useInViewport<T extends Element>(
  options?: UseInViewportOptions,
): { ref: RefObject<T | null>; inView: boolean } {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(false);
  const rootMargin = options?.rootMargin ?? "300px 0px";
  const threshold = options?.threshold ?? 0;
  const once = options?.once ?? false;

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (typeof IntersectionObserver === "undefined") {
      // Old browsers / non-DOM environments: assume visible so consumers
      // don't get stuck waiting for an observer that will never fire.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setInView(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setInView(true);
            if (once) observer.disconnect();
          } else if (!once) {
            setInView(false);
          }
        }
      },
      { rootMargin, threshold },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [rootMargin, threshold, once]);

  return { ref, inView };
}
