"use client";

import { useEffect, useRef, type RefObject } from "react";

interface AutoGrowOptions {
  minHeight?: number;
  maxHeight?: number;
}

export function useAutoGrowTextarea(
  value: string,
  { minHeight = 32, maxHeight = 160 }: AutoGrowOptions = {},
): RefObject<HTMLTextAreaElement | null> {
  const ref = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    element.style.height = "0px";
    const next = Math.min(Math.max(element.scrollHeight, minHeight), maxHeight);
    element.style.height = `${next}px`;
    element.style.overflowY = element.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [value, minHeight, maxHeight]);

  return ref;
}
