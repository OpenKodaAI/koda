"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

interface UseTabNavigationOptions {
  defaultTab?: string;
  redirects?: Record<string, string>;
}

function syncUrlTab(tab: string, fallback: string) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (tab === fallback) {
    url.searchParams.delete("tab");
  } else {
    url.searchParams.set("tab", tab);
  }
  window.history.replaceState(window.history.state, "", url.toString());
}

export function useTabNavigation(
  tabs: string[],
  defaultTabOrOptions?: string | UseTabNavigationOptions,
) {
  const searchParams = useSearchParams();

  const options: UseTabNavigationOptions =
    typeof defaultTabOrOptions === "string"
      ? { defaultTab: defaultTabOrOptions }
      : defaultTabOrOptions ?? {};
  const { defaultTab, redirects } = options;

  const fallback = defaultTab ?? tabs[0] ?? "";

  const [activeTab, setActiveTabState] = useState(() => {
    const raw = searchParams.get("tab");
    const redirected = raw && redirects && redirects[raw] ? redirects[raw] : null;
    if (redirected) return redirected;
    return raw && tabs.includes(raw) ? raw : fallback;
  });

  useEffect(() => {
    const raw = searchParams.get("tab");
    const redirected = raw && redirects && redirects[raw] ? redirects[raw] : null;
    if (redirected && redirected !== activeTab) {
      setActiveTabState(redirected);
      syncUrlTab(redirected, fallback);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setActiveTab = useCallback(
    (tab: string) => {
      setActiveTabState(tab);
      syncUrlTab(tab, fallback);
    },
    [fallback],
  );

  return { activeTab, setActiveTab };
}
