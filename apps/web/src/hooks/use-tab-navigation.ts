"use client";

import { useCallback, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

interface UseTabNavigationOptions {
  defaultTab?: string;
  redirects?: Record<string, string>;
}

export function useTabNavigation(
  tabs: string[],
  defaultTabOrOptions?: string | UseTabNavigationOptions,
) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const options: UseTabNavigationOptions =
    typeof defaultTabOrOptions === "string"
      ? { defaultTab: defaultTabOrOptions }
      : defaultTabOrOptions ?? {};
  const { defaultTab, redirects } = options;

  const fallback = defaultTab ?? tabs[0] ?? "";
  const raw = searchParams.get("tab");
  const redirected = raw && redirects && redirects[raw] ? redirects[raw] : null;
  const activeTab = redirected
    ? redirected
    : raw && tabs.includes(raw)
      ? raw
      : fallback;

  useEffect(() => {
    if (!redirected) return;
    const params = new URLSearchParams(searchParams.toString());
    if (redirected === fallback) {
      params.delete("tab");
    } else {
      params.set("tab", redirected);
    }
    const qs = params.toString();
    router.replace(qs ? `?${qs}` : "?", { scroll: false });
  }, [redirected, searchParams, router, fallback]);

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
