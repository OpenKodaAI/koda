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
  right?: number | string;
  transform?: string;
  position?: "fixed";
};

type RectBounds = {
  top: number;
  left: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
};

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
  mobile: boolean,
  panel: HTMLDivElement | null,
) {
  const viewportPaddingX = mobile ? 18 : 28;
  const viewportPaddingY = mobile ? 18 : 40;
  const gap = mobile ? 16 : 24;
  const panelWidth = mobile
    ? Math.min(window.innerWidth - viewportPaddingX * 2, 420)
    : Math.min(360, window.innerWidth - viewportPaddingX * 2);
  const panelHeight = panel?.getBoundingClientRect().height ?? 244;
  const maxLeft = window.innerWidth - panelWidth - viewportPaddingX;
  const maxTop = window.innerHeight - panelHeight - viewportPaddingY;

  if (mobile || !rect || placement === "center") {
    return {
      width: panelWidth,
      left: clamp(
        (window.innerWidth - panelWidth) / 2,
        viewportPaddingX,
        maxLeft,
      ),
      top: clamp(
        window.innerHeight - panelHeight - viewportPaddingY,
        viewportPaddingY,
        maxTop,
      ),
    };
  }

  const centerX = rect.left + rect.width / 2;
  const centerY = rect.top + rect.height / 2;
  const targetBounds = getExpandedBounds(rect, 16);
  const placements = getPanelPlacementCandidates(placement);

  let fallbackPosition: PanelPosition | null = null;
  let fallbackScore = Number.POSITIVE_INFINITY;

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
    const edgePenalty = getViewportEdgePenalty(
      bounds,
      viewportPaddingX,
      viewportPaddingY,
    );
    const distancePenalty =
      Math.abs(bounds.left + bounds.width / 2 - (targetBounds.left + targetBounds.width / 2)) * 0.2 +
      Math.abs(bounds.top + bounds.height / 2 - (targetBounds.top + targetBounds.height / 2)) * 0.12;
    const preferencePenalty = index * 18;
    const score =
      overlap * 2400 +
      edgePenalty +
      distancePenalty +
      preferencePenalty;

    if (score < fallbackScore) {
      fallbackPosition = position;
      fallbackScore = score;
    }
  }

  if (fallbackPosition) {
    return fallbackPosition;
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
  const topAligned = rect.top + (targetHeight > 220 ? 20 : -8);
  const centered = rect.centerY - panelHeight / 2;
  const preferred =
    targetHeight > window.innerHeight * 0.4 || centered < viewportPaddingY + 18
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

function getRectDelta(a: DOMRect | null, b: DOMRect | null) {
  if (!a || !b) {
    return Number.POSITIVE_INFINITY;
  }

  return (
    Math.abs(a.top - b.top) +
    Math.abs(a.left - b.left) +
    Math.abs(a.width - b.width) +
    Math.abs(a.height - b.height)
  );
}

function getViewportEdgePenalty(
  bounds: RectBounds,
  viewportPaddingX: number,
  viewportPaddingY: number,
) {
  const desiredInsetX = viewportPaddingX + 14;
  const desiredInsetY = viewportPaddingY + 10;
  const insets = [
    bounds.left,
    window.innerWidth - bounds.right,
  ];
  const verticalInsets = [
    bounds.top,
    window.innerHeight - bounds.bottom,
  ];

  const horizontalPenalty = insets.reduce((penalty, inset) => {
    if (inset >= desiredInsetX) {
      return penalty;
    }

    return penalty + (desiredInsetX - inset) * 8;
  }, 0);

  return verticalInsets.reduce((penalty, inset) => {
    if (inset >= desiredInsetY) {
      return penalty;
    }

    return penalty + (desiredInsetY - inset) * 10;
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

  return Array.from(
    new Set([placement, opposite, ...crossAxis]),
  ) as Exclude<TourPlacement, "center">[];
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
  const previousPathnameRef = useRef(pathname);
  const spotlightRevealAtRef = useRef(0);
  const [target, setTarget] = useState<HTMLElement | null>(null);
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);
  const [spotlightTargetRect, setSpotlightTargetRect] = useState<DOMRect | null>(null);
  const [panelPosition, setPanelPosition] = useState<{ top: number; left: number; width: number } | null>(null);
  const [mobile, setMobile] = useState(false);
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
  const spotlightRect = useMemo(
    () => {
      if (!spotlightTargetRect) return null;

      const radius =
        target && typeof window !== "undefined"
          ? Number.parseFloat(window.getComputedStyle(target).borderRadius || "0") || 18
          : 18;

      return getTourSpotlightFrame({
        top: spotlightTargetRect.top,
        left: spotlightTargetRect.left,
        width: spotlightTargetRect.width,
        height: spotlightTargetRect.height,
        radius,
      });
    },
    [spotlightTargetRect, target],
  );
  const handleBack = useCallback(() => {
    setStepDirection(-1);
    back();
  }, [back]);
  const handleNext = useCallback(() => {
    setStepDirection(1);
    next();
  }, [next]);
  const coachmarkStyle = useMemo<React.CSSProperties | undefined>(() => {
    if (!currentStep) {
      return undefined;
    }

    if (currentStep.id === "tour.welcome") {
      return {
        position: "fixed",
        top: "50%",
        left: "50%",
        width: mobile
          ? "min(680px, calc(100vw - 1.5rem))"
          : "min(860px, calc(100vw - 3.5rem))",
        maxHeight: mobile ? "calc(100dvh - 1.5rem)" : "calc(100vh - 4rem)",
        transform: "translate(-50%, -50%)",
      };
    }

    if (currentStep.kind === "modal") {
      return mobile
        ? {
            position: "fixed",
            top: "max(1rem, env(safe-area-inset-top))",
            left: "max(0.75rem, calc(env(safe-area-inset-left) + 0.75rem))",
            right: "max(0.75rem, calc(env(safe-area-inset-right) + 0.75rem))",
            width: "auto",
            maxHeight: "calc(100dvh - max(1.5rem, env(safe-area-inset-top) + env(safe-area-inset-bottom) + 0.75rem))",
          }
        : {
            position: "fixed",
            top: "clamp(1.5rem, 8vh, 3rem)",
            left: "50%",
            width: "min(720px, calc(100vw - 3rem))",
            transform: "translateX(-50%)",
          };
    }

    if (mobile) {
      return {
        position: "fixed",
        left: "max(0.75rem, calc(env(safe-area-inset-left) + 0.75rem))",
        right: "max(0.75rem, calc(env(safe-area-inset-right) + 0.75rem))",
        bottom: "max(0.75rem, calc(env(safe-area-inset-bottom) + 0.75rem))",
        top: "auto",
        width: "auto",
        maxHeight: "min(26rem, calc(100dvh - max(6rem, env(safe-area-inset-top) + 5.25rem)))",
      };
    }

    return {
      position: "fixed",
      ...(panelPosition ?? {}),
    };
  }, [currentStep, mobile, panelPosition]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const updateViewport = () => setMobile(window.innerWidth < 1024);
    updateViewport();

    window.addEventListener("resize", updateViewport);
    return () => window.removeEventListener("resize", updateViewport);
  }, []);

  useEffect(() => {
    let frame = 0;
    let timeout = 0;
    const pathChanged = previousPathnameRef.current !== pathname;
    previousPathnameRef.current = pathname;
    spotlightRevealAtRef.current = performance.now() + (pathChanged ? 420 : 80);

    const scheduleTargetUpdate = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        if (!isOpen || !currentStep || currentStep.kind === "modal") {
          setTarget(null);
          setTargetRect(null);
          setSpotlightTargetRect(null);
          setPanelPosition(null);
          return;
        }

        if (
          currentStep.routePattern &&
          !matchesTourRoutePattern(pathname, currentStep.routePattern)
        ) {
          setTarget(null);
          setTargetRect(null);
          setSpotlightTargetRect(null);
          setPanelPosition(null);
          return;
        }

        const nextTarget = resolveTargetElement(
          currentStep.anchor,
          currentStep.fallbackAnchor,
          currentStep.routeKey,
        );

        setTarget(nextTarget);

        if (!nextTarget) {
          setTargetRect(null);
          setSpotlightTargetRect(null);
          setPanelPosition(null);
        }
      });
    };

    scheduleTargetUpdate();
    timeout = window.setTimeout(scheduleTargetUpdate, 180);
    const observer =
      typeof MutationObserver !== "undefined"
        ? new MutationObserver(() => {
            scheduleTargetUpdate();
          })
        : null;

    observer?.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "style", "hidden", "aria-hidden"],
    });
    window.addEventListener("resize", scheduleTargetUpdate);

    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(timeout);
      observer?.disconnect();
      window.removeEventListener("resize", scheduleTargetUpdate);
    };
  }, [currentStep, isOpen, pathname]);

  useEffect(() => {
    if (!target || typeof target.scrollIntoView !== "function") return;

    const rect = target.getBoundingClientRect();
    const outOfView =
      rect.top < 90 ||
      rect.bottom > window.innerHeight - 120 ||
      rect.left < 12 ||
      rect.right > window.innerWidth - 12;

    if (outOfView) {
      target.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
    }
  }, [target]);

  useLayoutEffect(() => {
    let resetFrame = 0;
    const clearMeasuredState = () => {
      window.cancelAnimationFrame(resetFrame);
      resetFrame = window.requestAnimationFrame(() => {
        setTargetRect(null);
        setSpotlightTargetRect(null);
        setPanelPosition(null);
      });
    };

    if (!isOpen || !currentStep || currentStep.kind === "modal") {
      clearMeasuredState();
      return () => {
        window.cancelAnimationFrame(resetFrame);
      };
    }

    if (!target) {
      clearMeasuredState();
      return () => {
        window.cancelAnimationFrame(resetFrame);
      };
    }

    let lastMeasuredRect: DOMRect | null = null;
    let settledMeasurements = 0;
    let measureCount = 0;
    const revealNotBefore = spotlightRevealAtRef.current;

    const update = () => {
      const nextRect = target.getBoundingClientRect();
      setTargetRect(nextRect);
      setPanelPosition(
        getPanelPosition(
          nextRect,
          currentStep.placement ?? "bottom",
          mobile,
          panelRef.current,
        ),
      );

      const delta = getRectDelta(lastMeasuredRect, nextRect);
      settledMeasurements = delta <= 3 ? settledMeasurements + 1 : 0;
      measureCount += 1;
      lastMeasuredRect = nextRect;

      if (
        performance.now() >= revealNotBefore &&
        (settledMeasurements >= 1 || measureCount >= 5)
      ) {
        setSpotlightTargetRect(nextRect);
      }
    };

    update();
    const frame = window.requestAnimationFrame(update);
    const settleFrame = window.requestAnimationFrame(() => {
      window.requestAnimationFrame(update);
    });
    const settleTimeoutA = window.setTimeout(update, 120);
    const settleTimeoutB = window.setTimeout(update, 280);
    const settleTimeoutC = window.setTimeout(update, 520);
    const settleTimeoutD = window.setTimeout(update, 760);
    const revealTimeout = window.setTimeout(
      update,
      Math.max(0, revealNotBefore - performance.now() + 18),
    );
    const settleInterval = window.setInterval(update, 90);
    const settleIntervalStop = window.setTimeout(() => {
      window.clearInterval(settleInterval);
    }, 900);
    const resizeObserver =
      typeof ResizeObserver !== "undefined" ? new ResizeObserver(update) : null;

    resizeObserver?.observe(target);
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);

    return () => {
      window.cancelAnimationFrame(resetFrame);
      window.cancelAnimationFrame(frame);
      window.cancelAnimationFrame(settleFrame);
      window.clearTimeout(settleTimeoutA);
      window.clearTimeout(settleTimeoutB);
      window.clearTimeout(settleTimeoutC);
      window.clearTimeout(settleTimeoutD);
      window.clearTimeout(revealTimeout);
      window.clearInterval(settleInterval);
      window.clearTimeout(settleIntervalStop);
      resizeObserver?.disconnect();
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [currentStep, isOpen, mobile, target]);

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

  const showAnchoredCoachmark =
    currentStep.kind === "anchored" &&
    matchesTourRoutePattern(pathname, currentStep.routePattern) &&
    (targetRect || mobile);

  return (
    <TourOverlay spotlightRect={showAnchoredCoachmark ? spotlightRect : null}>
      <div className="sr-only" aria-live="polite">
        {t(copy.titleKey)}
      </div>
      <AnimatePresence initial={false}>
        {showAnchoredCoachmark ? (
          <TourSpotlight key="tour-spotlight" rect={spotlightRect} />
        ) : null}
      </AnimatePresence>
      <AnimatePresence mode="wait" initial={false}>
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
          mobile={mobile || (currentStep.kind !== "modal" && !targetRect)}
          welcome={isWelcomeStep}
          className={
            currentStep.kind === "modal"
              ? cn(
                  "tour-coachmark--modal",
                  isWelcomeStep && "tour-coachmark--welcome",
                )
              : cn(
                  "tour-coachmark--anchored",
                  mobile && "tour-coachmark--mobile-sheet",
                )
          }
          style={coachmarkStyle}
        />
      </AnimatePresence>
    </TourOverlay>
  );
}
