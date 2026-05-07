"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence } from "framer-motion";
import { TourCoachmark } from "@/components/tour/tour-coachmark";
import { TourOverlay } from "@/components/tour/tour-overlay";
import { getTourSpotlightFrame, TourSpotlight } from "@/components/tour/tour-spotlight";
import { useAppTour } from "@/hooks/use-app-tour";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { matchesTourRoutePattern, resolveTourCopy, type TourPlacement, type TourVariant } from "@/lib/tour";
import { cn } from "@/lib/utils";

type PanelPosition = {
  top: number;
  left: number;
  width: number;
};

type RectBounds = {
  top: number;
  left: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
};

const MOBILE_BREAKPOINT = 640;

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function getFocusableElements(container: HTMLElement | null) {
  if (!container) return [];
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => !element.hasAttribute("aria-hidden"));
}

function isUsableTourTarget(element: HTMLElement | null) {
  if (!element || typeof window === "undefined") return false;

  const style = window.getComputedStyle(element);
  if (
    style.display === "none" ||
    style.visibility === "hidden" ||
    Number.parseFloat(style.opacity || "1") === 0
  ) {
    return false;
  }

  const rect = element.getBoundingClientRect();
  if (rect.width < 8 || rect.height < 8) {
    return false;
  }

  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const visibleWidth = Math.min(rect.right, viewportWidth) - Math.max(rect.left, 0);
  const visibleHeight = Math.min(rect.bottom, viewportHeight) - Math.max(rect.top, 0);

  return visibleWidth >= 8 && visibleHeight >= 8;
}

function getUsableTourTarget(selector: string) {
  if (typeof document === "undefined") {
    return null;
  }

  const elements = Array.from(document.querySelectorAll<HTMLElement>(selector));
  return elements.find((element) => isUsableTourTarget(element)) ?? null;
}

function resolveTargetElement(
  anchor: string | undefined,
  fallbackAnchor: string | undefined,
  routeKey: string | undefined,
) {
  if (typeof document === "undefined") {
    return null;
  }

  if (anchor) {
    const element = getUsableTourTarget(`[data-tour-anchor="${anchor}"]`);
    if (element) return element;
  }

  if (fallbackAnchor) {
    const fallbackElement = getUsableTourTarget(`[data-tour-anchor="${fallbackAnchor}"]`);
    if (fallbackElement) return fallbackElement;
  }

  if (routeKey) {
    const routeElement = getUsableTourTarget(`[data-tour-route="${routeKey}"]`);
    if (routeElement) {
      return routeElement;
    }
  }

  return null;
}

function getVariant(routeKey: string | undefined): TourVariant {
  if (!routeKey || typeof document === "undefined") {
    return "default";
  }

  const value = document
    .querySelector<HTMLElement>(`[data-tour-route="${routeKey}"]`)
    ?.getAttribute("data-tour-variant");

  if (value === "empty" || value === "loading" || value === "unavailable") {
    return value;
  }

  return "default";
}

function getPanelPosition(
  rect: DOMRect | null,
  placement: TourPlacement,
  panel: HTMLDivElement | null,
): PanelPosition {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const isNarrow = viewportWidth < MOBILE_BREAKPOINT;
  const viewportPaddingX = isNarrow ? 12 : 24;
  const viewportPaddingY = isNarrow ? 14 : 32;
  const gap = isNarrow ? 12 : 18;
  const panelWidth = Math.min(
    isNarrow ? viewportWidth - viewportPaddingX * 2 : 340,
    viewportWidth - viewportPaddingX * 2,
  );
  const panelHeight = panel?.getBoundingClientRect().height ?? 220;
  const maxLeft = viewportWidth - panelWidth - viewportPaddingX;
  const maxTop = viewportHeight - panelHeight - viewportPaddingY;

  if (!rect || placement === "center") {
    return {
      width: panelWidth,
      left: clamp((viewportWidth - panelWidth) / 2, viewportPaddingX, maxLeft),
      top: clamp(viewportHeight - panelHeight - viewportPaddingY, viewportPaddingY, maxTop),
    };
  }

  const centerX = rect.left + rect.width / 2;
  const centerY = rect.top + rect.height / 2;
  const targetBounds = getExpandedBounds(rect, 12);
  const placements = getPanelPlacementCandidates(placement);

  let bestPosition: PanelPosition | null = null;
  let bestScore = Number.POSITIVE_INFINITY;

  for (const [index, candidate] of placements.entries()) {
    const position = buildPanelPosition(
      candidate,
      {
        centerX,
        centerY,
        left: rect.left,
        right: rect.right,
        top: rect.top,
        bottom: rect.bottom,
      },
      panelWidth,
      panelHeight,
      viewportPaddingX,
      viewportPaddingY,
      gap,
    );
    const bounds = getPanelBounds(position, panelHeight);
    const overlap = getOverlapArea(bounds, targetBounds);
    const edgePenalty = getViewportEdgePenalty(bounds, viewportPaddingX, viewportPaddingY);
    const preferencePenalty = index * 12;
    const score = overlap * 2400 + edgePenalty + preferencePenalty;

    if (score < bestScore) {
      bestPosition = position;
      bestScore = score;
    }
  }

  if (bestPosition) {
    return bestPosition;
  }

  return {
    width: panelWidth,
    left: clamp(centerX - panelWidth / 2, viewportPaddingX, maxLeft),
    top: clamp(rect.bottom + gap, viewportPaddingY, maxTop),
  };
}

function buildPanelPosition(
  placement: Exclude<TourPlacement, "center">,
  rect: Pick<RectBounds, "top" | "right" | "bottom" | "left"> & {
    centerX: number;
    centerY: number;
  },
  panelWidth: number,
  panelHeight: number,
  viewportPaddingX: number,
  viewportPaddingY: number,
  gap: number,
): PanelPosition {
  const maxLeft = window.innerWidth - panelWidth - viewportPaddingX;
  const maxTop = window.innerHeight - panelHeight - viewportPaddingY;

  if (placement === "left") {
    return {
      width: panelWidth,
      left: clamp(rect.left - panelWidth - gap, viewportPaddingX, maxLeft),
      top: resolveSidePlacementTop(rect, panelHeight, viewportPaddingY, maxTop),
    };
  }

  if (placement === "right") {
    return {
      width: panelWidth,
      left: clamp(rect.right + gap, viewportPaddingX, maxLeft),
      top: resolveSidePlacementTop(rect, panelHeight, viewportPaddingY, maxTop),
    };
  }

  if (placement === "top") {
    return {
      width: panelWidth,
      left: clamp(rect.centerX - panelWidth / 2, viewportPaddingX, maxLeft),
      top: clamp(rect.top - panelHeight - gap, viewportPaddingY, maxTop),
    };
  }

  return {
    width: panelWidth,
    left: clamp(rect.centerX - panelWidth / 2, viewportPaddingX, maxLeft),
    top: clamp(rect.bottom + gap, viewportPaddingY, maxTop),
  };
}

function resolveSidePlacementTop(
  rect: Pick<RectBounds, "top" | "bottom"> & { centerY: number },
  panelHeight: number,
  viewportPaddingY: number,
  maxTop: number,
) {
  const targetHeight = rect.bottom - rect.top;
  const topAligned = rect.top + (targetHeight > 220 ? 16 : -6);
  const centered = rect.centerY - panelHeight / 2;
  const preferred =
    targetHeight > window.innerHeight * 0.4 || centered < viewportPaddingY + 16
      ? topAligned
      : centered;

  return clamp(preferred, viewportPaddingY, maxTop);
}

function getExpandedBounds(rect: DOMRect, padding: number): RectBounds {
  return {
    top: rect.top - padding,
    left: rect.left - padding,
    right: rect.right + padding,
    bottom: rect.bottom + padding,
    width: rect.width + padding * 2,
    height: rect.height + padding * 2,
  };
}

function getPanelBounds(position: PanelPosition, panelHeight: number): RectBounds {
  return {
    top: position.top,
    left: position.left,
    right: position.left + position.width,
    bottom: position.top + panelHeight,
    width: position.width,
    height: panelHeight,
  };
}

function getOverlapArea(a: RectBounds, b: RectBounds) {
  const width = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
  const height = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  return width * height;
}

function getViewportEdgePenalty(
  bounds: RectBounds,
  viewportPaddingX: number,
  viewportPaddingY: number,
) {
  const desiredInsetX = viewportPaddingX + 8;
  const desiredInsetY = viewportPaddingY + 6;
  const horizontalInsets = [bounds.left, window.innerWidth - bounds.right];
  const verticalInsets = [bounds.top, window.innerHeight - bounds.bottom];

  const horizontalPenalty = horizontalInsets.reduce((penalty, inset) => {
    if (inset >= desiredInsetX) return penalty;
    return penalty + (desiredInsetX - inset) * 6;
  }, 0);

  return verticalInsets.reduce((penalty, inset) => {
    if (inset >= desiredInsetY) return penalty;
    return penalty + (desiredInsetY - inset) * 8;
  }, horizontalPenalty);
}

function getPanelPlacementCandidates(
  placement: Exclude<TourPlacement, "center">,
): Exclude<TourPlacement, "center">[] {
  const opposite =
    placement === "top"
      ? "bottom"
      : placement === "bottom"
        ? "top"
        : placement === "left"
          ? "right"
          : "left";

  const crossAxis =
    placement === "top" || placement === "bottom"
      ? ["right", "left"]
      : ["top", "bottom"];

  return Array.from(new Set([placement, opposite, ...crossAxis])) as Exclude<
    TourPlacement,
    "center"
  >[];
}

export function TourHost() {
  const {
    booting,
    status,
    currentStep,
    currentStepIndex,
    currentStepCount,
    pathname,
    back,
    next,
    skipAll,
  } = useAppTour();
  const { t } = useAppI18n();
  const panelRef = useRef<HTMLDivElement | null>(null);
  const lastScrolledStepIdRef = useRef<string | null>(null);
  const [target, setTarget] = useState<HTMLElement | null>(null);
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);
  const [panelPosition, setPanelPosition] = useState<PanelPosition | null>(null);
  const [resolvedStepId, setResolvedStepId] = useState<string | null>(null);
  const [resolvedToPrimary, setResolvedToPrimary] = useState(false);
  const [stepDirection, setStepDirection] = useState(1);
  const isOpen = !booting && status === "running" && Boolean(currentStep);
  const variant = useMemo(
    () => getVariant(currentStep?.routeKey),
    [currentStep?.routeKey],
  );
  const copy = useMemo(
    () => (currentStep ? resolveTourCopy(currentStep, variant) : null),
    [currentStep, variant],
  );
  const isWelcomeStep = currentStep?.id === "tour.welcome";
  const spotlightRect = useMemo(() => {
    if (!target || !targetRect) return null;
    if (typeof window === "undefined") return null;

    const radius =
      Number.parseFloat(window.getComputedStyle(target).borderRadius || "0") || 14;

    return getTourSpotlightFrame({
      top: targetRect.top,
      left: targetRect.left,
      width: targetRect.width,
      height: targetRect.height,
      radius,
    });
  }, [targetRect, target]);

  const handleBack = useCallback(() => {
    setStepDirection(-1);
    back();
  }, [back]);

  const handleNext = useCallback(() => {
    setStepDirection(1);
    next();
  }, [next]);

  const isCurrentStepResolved =
    Boolean(currentStep) && resolvedStepId === currentStep?.id;
  const isAnchorReady =
    isCurrentStepResolved && Boolean(target) && Boolean(panelPosition) && resolvedToPrimary;
  const useCenteredFrame =
    !currentStep ||
    currentStep.kind === "modal" ||
    !isAnchorReady;

  const coachmarkStyle = useMemo<React.CSSProperties | undefined>(() => {
    if (!currentStep) {
      return undefined;
    }

    if (useCenteredFrame) {
      return {
        position: "relative",
        width: "min(440px, 100%)",
        maxHeight: "100%",
        pointerEvents: "auto",
      };
    }

    return {
      position: "fixed",
      top: panelPosition!.top,
      left: panelPosition!.left,
      width: panelPosition!.width,
    };
  }, [currentStep, panelPosition, useCenteredFrame]);

  useLayoutEffect(() => {
    if (typeof window === "undefined") return;

    if (!isOpen || !currentStep || currentStep.kind === "modal") {
      return;
    }

    if (
      currentStep.routePattern &&
      !matchesTourRoutePattern(pathname, currentStep.routePattern)
    ) {
      return;
    }

    const stepId = currentStep.id;
    let lastResolved: HTMLElement | null = null;
    let frame = 0;
    let attempts = 0;

    const tryResolve = (): boolean => {
      attempts += 1;
      const primaryEl = currentStep.anchor
        ? document.querySelector<HTMLElement>(
            `[data-tour-anchor="${currentStep.anchor}"]`,
          )
        : null;
      const primaryUsable = primaryEl ? isUsableTourTarget(primaryEl) : false;

      // Prefer primary if it's now usable — even if we previously settled on
      // a fallback (page may have just finished hydrating).
      const nextTarget = primaryUsable
        ? primaryEl
        : resolveTargetElement(
            currentStep.anchor,
            currentStep.fallbackAnchor,
            currentStep.routeKey,
          );

      if (!nextTarget) {
        return false;
      }

      const isPrimaryAnchor = primaryUsable && nextTarget === primaryEl;
      const lastIsPrimaryAnchor =
        lastResolved && primaryEl && lastResolved === primaryEl;

      // Never downgrade from primary to fallback.
      if (lastIsPrimaryAnchor && !isPrimaryAnchor) {
        return false;
      }

      // Skip redundant updates.
      if (nextTarget === lastResolved) {
        if (isPrimaryAnchor && !resolvedToPrimary) {
          setResolvedToPrimary(true);
        }
        return isPrimaryAnchor;
      }

      lastResolved = nextTarget;
      const rect = nextTarget.getBoundingClientRect();
      setTarget(nextTarget);
      setTargetRect(rect);
      setPanelPosition(
        getPanelPosition(rect, currentStep.placement ?? "bottom", panelRef.current),
      );
      setResolvedStepId(stepId);
      setResolvedToPrimary(isPrimaryAnchor);
      return isPrimaryAnchor;
    };

    const settledOnPrimary = tryResolve();

    if (settledOnPrimary) {
      return;
    }

    let stopped = false;
    let observer: MutationObserver | null = null;
    let timer = 0;

    const stop = () => {
      stopped = true;
      window.clearTimeout(timer);
      window.cancelAnimationFrame(frame);
      observer?.disconnect();
      observer = null;
    };

    // Page may still be hydrating — keep re-resolving until we either land on
    // the primary anchor, or we've exhausted reasonable attempts.
    const scheduleResolve = (delay: number) => {
      if (stopped) return;
      timer = window.setTimeout(() => {
        if (stopped) return;
        frame = window.requestAnimationFrame(() => {
          if (stopped) return;
          const settled = tryResolve();
          if (settled) {
            stop();
            return;
          }
          if (attempts < 8) {
            scheduleResolve(Math.min(delay * 1.5, 600));
          } else {
            // Give up waiting for primary — accept whatever target we have so
            // the user isn't stuck in centered mode forever (e.g., when the
            // primary anchor genuinely doesn't render on this page).
            if (lastResolved) {
              setResolvedToPrimary(true);
            }
            observer?.disconnect();
            observer = null;
          }
        });
      }, delay);
    };

    scheduleResolve(80);

    if (typeof MutationObserver !== "undefined") {
      observer = new MutationObserver(() => {
        if (stopped) return;
        window.clearTimeout(timer);
        scheduleResolve(40);
      });
      observer.observe(document.body, { childList: true, subtree: true });
    }

    return stop;
    // resolvedToPrimary is intentionally read inside tryResolve via the
    // closure but is set BY this effect — including it would cause an
    // infinite re-run loop on every resolution.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentStep, isOpen, pathname]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!target || !currentStep || currentStep.kind === "modal") return;

    let frame = 0;

    const remeasure = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        if (!target.isConnected) return;
        const rect = target.getBoundingClientRect();
        setTargetRect(rect);
        setPanelPosition(
          getPanelPosition(rect, currentStep.placement ?? "bottom", panelRef.current),
        );
      });
    };

    const resizeObserver =
      typeof ResizeObserver !== "undefined" ? new ResizeObserver(remeasure) : null;
    resizeObserver?.observe(target);
    window.addEventListener("resize", remeasure);
    window.addEventListener("scroll", remeasure, true);

    return () => {
      window.cancelAnimationFrame(frame);
      resizeObserver?.disconnect();
      window.removeEventListener("resize", remeasure);
      window.removeEventListener("scroll", remeasure, true);
    };
  }, [target, currentStep]);

  useEffect(() => {
    if (!target || !currentStep || currentStep.kind === "modal") return;
    if (lastScrolledStepIdRef.current === currentStep.id) return;
    if (typeof target.scrollIntoView !== "function") return;

    const rect = target.getBoundingClientRect();
    const outOfView =
      rect.top < 90 ||
      rect.bottom > window.innerHeight - 120 ||
      rect.left < 12 ||
      rect.right > window.innerWidth - 12;

    if (outOfView) {
      target.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
    }

    lastScrolledStepIdRef.current = currentStep.id;
  }, [currentStep, target]);

  useEffect(() => {
    if (!isOpen || !panelRef.current) return;

    const focusable = getFocusableElements(panelRef.current);
    focusable[0]?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (window.confirm(t("tour.confirmSkip"))) {
          skipAll();
        }
        return;
      }

      if (event.key !== "Tab") return;

      const items = getFocusableElements(panelRef.current);
      if (items.length === 0) return;

      const activeElement = document.activeElement as HTMLElement | null;
      const currentIndex = activeElement ? items.indexOf(activeElement) : -1;
      const nextIndex = event.shiftKey
        ? currentIndex <= 0
          ? items.length - 1
          : currentIndex - 1
        : currentIndex === items.length - 1
          ? 0
          : currentIndex + 1;

      event.preventDefault();
      items[nextIndex]?.focus();
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, skipAll, t]);

  if (!isOpen || !currentStep || !copy) {
    return null;
  }

  if (
    currentStep.kind === "anchored" &&
    currentStep.routePattern &&
    !matchesTourRoutePattern(pathname, currentStep.routePattern)
  ) {
    return null;
  }

  const progressTotal = Math.max(currentStepCount - 2, 0);
  const progressCurrent =
    currentStep.id === "tour.welcome"
      ? 0
      : currentStep.id === "tour.complete"
        ? progressTotal
        : Math.max(currentStepIndex, 1);

  const showSpotlight =
    currentStep.kind === "anchored" &&
    matchesTourRoutePattern(pathname, currentStep.routePattern) &&
    isAnchorReady &&
    Boolean(targetRect);

  const showCoachmark =
    currentStep.kind === "modal" ||
    (currentStep.kind === "anchored" &&
      matchesTourRoutePattern(pathname, currentStep.routePattern));

  return (
    <TourOverlay spotlightRect={showSpotlight ? spotlightRect : null}>
      <div className="sr-only" aria-live="polite">
        {t(copy.titleKey)}
      </div>
      <AnimatePresence initial={false}>
        {showSpotlight ? (
          <TourSpotlight key="tour-spotlight" rect={spotlightRect} />
        ) : null}
      </AnimatePresence>
      {useCenteredFrame ? (
        <div className="tour-coachmark-frame" aria-hidden={!showCoachmark}>
          <AnimatePresence mode="wait" initial={false}>
            {showCoachmark ? (
              <TourCoachmark
                key={currentStep.id}
                title={t(copy.titleKey)}
                description={t(copy.descriptionKey)}
                current={progressCurrent}
                total={progressTotal}
                onBack={handleBack}
                onContinue={handleNext}
                onSkip={skipAll}
                backLabel={t("tour.actions.back")}
                continueLabel={t(copy.continueLabelKey ?? "tour.actions.continue")}
                skipLabel={t("tour.actions.skip")}
                showBack={currentStepIndex > 0}
                showSkip={currentStep.id !== "tour.complete"}
                panelRef={panelRef}
                stepKey={currentStep.id}
                stepDirection={stepDirection}
                welcome={isWelcomeStep}
                className={cn(
                  currentStep.kind === "modal"
                    ? "tour-coachmark--modal"
                    : "tour-coachmark--anchored",
                  isWelcomeStep && "tour-coachmark--welcome",
                )}
                style={coachmarkStyle}
              />
            ) : null}
          </AnimatePresence>
        </div>
      ) : (
        <AnimatePresence mode="wait" initial={false}>
          {showCoachmark ? (
            <TourCoachmark
              key={currentStep.id}
              title={t(copy.titleKey)}
              description={t(copy.descriptionKey)}
              current={progressCurrent}
              total={progressTotal}
              onBack={handleBack}
              onContinue={handleNext}
              onSkip={skipAll}
              backLabel={t("tour.actions.back")}
              continueLabel={t(copy.continueLabelKey ?? "tour.actions.continue")}
              skipLabel={t("tour.actions.skip")}
              showBack={currentStepIndex > 0}
              showSkip={currentStep.id !== "tour.complete"}
              panelRef={panelRef}
              stepKey={currentStep.id}
              stepDirection={stepDirection}
              welcome={isWelcomeStep}
              className="tour-coachmark--anchored"
              style={coachmarkStyle}
            />
          ) : null}
        </AnimatePresence>
      )}
    </TourOverlay>
  );
}
