"use client";

import { useCallback, useEffect, useMemo } from "react";
import { usePathname } from "next/navigation";
import { useLocalStorage } from "@/hooks/use-local-storage";
import { recentRoutesStorageCodec } from "@/lib/storage-codecs";

export interface RecentRoute {
  href: string;
  label: string;
  visitedAt: number;
}

const MAX_RECENTS = 5;
const TRACKED_PATH_PREFIXES = [
  "/runtime",
  "/executions",
  "/sessions",
  "/schedules",
  "/dlq",
  "/memory",
  "/costs",
  "/control-plane",
];

const EXCLUDED_PATHS = new Set(["/", "/control-plane/system"]);

function shouldTrack(path: string): boolean {
  if (EXCLUDED_PATHS.has(path)) return false;
  if (path.startsWith("/control-plane/system")) return false;
  return TRACKED_PATH_PREFIXES.some((prefix) => path.startsWith(prefix));
}

function labelForPath(path: string): string {
  const segments = path.split("/").filter(Boolean);
  if (!segments.length) return path;
  const last = segments[segments.length - 1];
  if (!last) return path;
  return last.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function useRecents(labelResolver?: (path: string) => string | null) {
  const [recents, setRecents] = useLocalStorage<RecentRoute[]>(
    recentRoutesStorageCodec.key,
    [],
    recentRoutesStorageCodec,
  );
  const pathname = usePathname();

  useEffect(() => {
    if (!pathname) return;
    if (!shouldTrack(pathname)) return;

    const resolvedLabel = labelResolver?.(pathname) ?? labelForPath(pathname);
    const now = Date.now();

    setRecents((prev) => {
      const filtered = prev.filter((entry) => entry.href !== pathname);
      const next: RecentRoute[] = [
        { href: pathname, label: resolvedLabel, visitedAt: now },
        ...filtered,
      ];
      return next.slice(0, MAX_RECENTS);
    });
  }, [labelResolver, pathname, setRecents]);

  const clear = useCallback(() => setRecents([]), [setRecents]);

  return useMemo(() => ({ recents, clear }), [recents, clear]);
}
