"use client";

import { useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export function useTabNavigation(tabs: string[], defaultTab?: string) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const fallback = defaultTab ?? tabs[0] ?? "";
  const raw = searchParams.get("tab");
  const activeTab = raw && tabs.includes(raw) ? raw : fallback;

  const setActiveTab = useCallback(
    (tab: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (tab === fallback) {
        params.delete("tab");
      } else {
        params.set("tab", tab);
      }
      const qs = params.toString();
      router.replace(qs ? `?${qs}` : "?", { scroll: false });
    },
    [searchParams, router, fallback],
  );

  return { activeTab, setActiveTab };
}
