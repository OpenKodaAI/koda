"use client";

import { useEffect } from "react";
import { useSystemSettings } from "@/hooks/use-system-settings";

export function UnsavedChangesGuard() {
  const { dirty } = useSystemSettings();

  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  useEffect(() => {
    if (!dirty) return;

    // Intercept browser back/forward
    const handlePopState = () => {
      if (window.location.pathname.startsWith("/control-plane/system")) return;
      // User navigated away — no clean way to prevent popstate, but we tried
    };

    // Intercept programmatic navigation via pushState
    const originalPushState = window.history.pushState.bind(window.history);
    window.history.pushState = function (...args: Parameters<typeof originalPushState>) {
      const url = args[2];
      const targetPath = typeof url === "string" ? url : url?.toString() ?? "";
      if (!targetPath.startsWith("/control-plane/system")) {
        const confirmed = window.confirm("You have unsaved changes. Are you sure you want to leave?");
        if (!confirmed) return;
      }
      return originalPushState(...args);
    };

    return () => {
      window.history.pushState = originalPushState;
      window.removeEventListener("popstate", handlePopState);
    };
  }, [dirty]);

  return null;
}
