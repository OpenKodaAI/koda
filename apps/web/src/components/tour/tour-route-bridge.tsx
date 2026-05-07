"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAppTour } from "@/hooks/use-app-tour";
import {
  getOptionalTourRecoveryAction,
  getTourChapterForPathname,
  matchesTourRoutePattern,
} from "@/lib/tour";

function anchorWantsSidebar(anchor: string | undefined) {
  return Boolean(anchor?.startsWith("shell.sidebar"));
}

function resolveNavigationHref(anchor: string | undefined) {
  if (!anchor || typeof document === "undefined") {
    return null;
  }

  const element =
    Array.from(document.querySelectorAll<HTMLElement>(`[data-tour-anchor="${anchor}"]`)).find(
      (candidate) => {
        const style = window.getComputedStyle(candidate);
        const rect = candidate.getBoundingClientRect();
        return (
          style.display !== "none" &&
          style.visibility !== "hidden" &&
          Number.parseFloat(style.opacity || "1") !== 0 &&
          rect.width >= 8 &&
          rect.height >= 8
        );
      },
    ) ?? null;
  if (!element) {
    return null;
  }

  if (element instanceof HTMLAnchorElement) {
    try {
      const url = new URL(element.href, window.location.origin);
      return `${url.pathname}${url.search}`;
    } catch {
      return element.getAttribute("href");
    }
  }

  return element.getAttribute("data-tour-href");
}

function resolveEditorHref() {
  if (typeof document === "undefined") {
    return null;
  }

  const candidate =
    document.querySelector<HTMLAnchorElement>('a[href^="/control-plane/agents/"]') ??
    document.querySelector<HTMLAnchorElement>('a[href^="/control-plane/agents/"]') ??
    document.querySelector<HTMLAnchorElement>(
      '[data-tour-anchor="catalog.board"] a[href^="/control-plane/agents/"]',
    ) ??
    document.querySelector<HTMLAnchorElement>(
      '[data-tour-anchor="catalog.board"] a[href^="/control-plane/agents/"]',
    );

  if (!candidate) {
    return null;
  }

  try {
    const url = new URL(candidate.href, window.location.origin);
    return `${url.pathname}${url.search}`;
  } catch {
    return candidate.getAttribute("href");
  }
}

export function TourRouteBridge({
  pathname,
  onMobileNavOpenChange,
}: {
  pathname: string;
  onMobileNavOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const rememberedRouteHrefsRef = useRef<Partial<Record<string, string>>>({});
  const {
    booting,
    status,
    mode,
    currentStep,
    pendingRouteStepId,
    acknowledgeRouteArrival,
    back,
    next,
    openChapter,
  } = useAppTour();

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!matchesTourRoutePattern(pathname, "/control-plane/agents/:agentId")) return;

    rememberedRouteHrefsRef.current["/control-plane/agents/:agentId"] = `${window.location.pathname}${window.location.search}`;
  }, [pathname]);

  // Only react to tour-anchor TRANSITIONS — never to user-initiated menu
  // state changes. Otherwise, when the user manually opens the mobile menu
  // on a non-sidebar step, this effect would immediately force it closed.
  const prevWantsSidebarRef = useRef(anchorWantsSidebar(currentStep?.anchor));
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.innerWidth >= 1024) {
      prevWantsSidebarRef.current = anchorWantsSidebar(currentStep?.anchor);
      return;
    }

    const wantsSidebar = anchorWantsSidebar(currentStep?.anchor);
    const prev = prevWantsSidebarRef.current;
    prevWantsSidebarRef.current = wantsSidebar;

    if (wantsSidebar === prev) return;
    onMobileNavOpenChange(wantsSidebar);
  }, [currentStep?.anchor, onMobileNavOpenChange]);

  useEffect(() => {
    if (booting || status !== "running" || !currentStep) {
      return;
    }

    if (matchesTourRoutePattern(pathname, currentStep.routePattern)) {
      if (pendingRouteStepId === currentStep.id) {
        acknowledgeRouteArrival();
      }
      return;
    }

    if (pendingRouteStepId === currentStep.id) {
      const targetHref =
        currentStep.routePattern === "/control-plane/agents/:agentId"
          ? resolveNavigationHref(currentStep.navigationAnchor) ??
            rememberedRouteHrefsRef.current["/control-plane/agents/:agentId"] ??
            resolveEditorHref()
          : currentStep.routePattern ?? null;

      if (targetHref) {
        router.push(targetHref, { scroll: false });
        return;
      }

      if (currentStep.optional) {
        const recoveryAction = getOptionalTourRecoveryAction(currentStep.id, mode, pathname);
        if (recoveryAction === "back") {
          back();
        } else {
          next();
        }
      }
      return;
    }

    const routeChapter = getTourChapterForPathname(pathname);
    if (routeChapter && routeChapter !== currentStep.chapterId) {
      openChapter(routeChapter);
    }
  }, [
    acknowledgeRouteArrival,
    back,
    booting,
    currentStep,
    mode,
    next,
    openChapter,
    pathname,
    pendingRouteStepId,
    router,
    status,
  ]);

  return null;
}
