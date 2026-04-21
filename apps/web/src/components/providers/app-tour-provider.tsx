"use client";

import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  safeLocalStorageGetValue,
  safeLocalStorageSetValue,
} from "@/lib/browser-storage";
import { appTourStorageCodec } from "@/lib/storage-codecs";
import {
  getFirstTourStepIdForChapter,
  getNextTourStepId,
  getPreviousTourStepId,
  getTourChapterForPathname,
  getTourStepById,
  getTourStepIndex,
  getTourStepsForMode,
  isAutoEligibleTourPath,
  matchesTourRoutePattern,
  resolveTourPersistenceState,
  type TourChapterId,
  type TourMode,
  type TourPersistenceState,
  type TourStatus,
  type TourStepDefinition,
  type TourStepId,
} from "@/lib/tour";
import { TourHost } from "@/components/tour/tour-host";
import { TourRouteBridge } from "@/components/tour/tour-route-bridge";

type TourMachineState = TourPersistenceState & {
  booting: boolean;
  mode: TourMode;
  pendingRouteStepId: TourStepId | null;
};

export type AppTourContextValue = {
  booting: boolean;
  status: TourStatus;
  mode: TourMode;
  currentStep: TourStepDefinition | null;
  currentStepId: TourStepId | null;
  currentStepIndex: number;
  currentStepCount: number;
  pendingRouteStepId: TourStepId | null;
  pathname: string;
  start: () => void;
  resume: () => void;
  next: () => void;
  back: () => void;
  skipAll: () => void;
  restart: () => void;
  openChapter: (chapterId: TourChapterId) => void;
  acknowledgeRouteArrival: () => void;
};

export const AppTourContext = createContext<AppTourContextValue | null>(null);

function getPersistableTourState(state: TourMachineState): TourPersistenceState {
  return {
    version: state.version,
    status: state.status,
    currentStepId: state.currentStepId,
    completedChapters: state.completedChapters,
    updatedAt: state.updatedAt,
    completedAt: state.completedAt,
    skippedAt: state.skippedAt,
  };
}

function getPersistedTourState(): TourMachineState {
  const persisted = safeLocalStorageGetValue(appTourStorageCodec);
  const snapshot = resolveTourPersistenceState(persisted);
  return {
    ...snapshot,
    booting: false,
    mode: snapshot.status === "running" ? "auto" : "manual",
    pendingRouteStepId: null,
  };
}

function buildRunningState(
  current: TourMachineState,
  stepId: TourStepId,
  mode: TourMode,
  pathname: string,
) {
  const step = getTourStepById(stepId);
  const shouldNavigate =
    Boolean(step?.routePattern) &&
    !matchesTourRoutePattern(pathname, step?.routePattern);

  return {
    ...current,
    booting: false,
    status: "running" as const,
    mode,
    currentStepId: stepId,
    pendingRouteStepId: shouldNavigate ? stepId : null,
    updatedAt: Date.now(),
    completedAt: null,
    skippedAt: null,
  };
}

export function AppTourProvider({
  children,
  pathname,
  mobileNavOpen,
  onMobileNavOpenChange,
}: {
  children: ReactNode;
  pathname: string;
  mobileNavOpen: boolean;
  onMobileNavOpenChange: (open: boolean) => void;
}) {
  const [state, setState] = useState<TourMachineState>({
    version: appTourStorageCodec.fallback.version,
    status: appTourStorageCodec.fallback.status,
    currentStepId: appTourStorageCodec.fallback.currentStepId,
    completedChapters: appTourStorageCodec.fallback.completedChapters,
    updatedAt: appTourStorageCodec.fallback.updatedAt,
    completedAt: appTourStorageCodec.fallback.completedAt,
    skippedAt: appTourStorageCodec.fallback.skippedAt,
    booting: true,
    mode: "auto",
    pendingRouteStepId: null,
  });

  const commitState = useCallback(
    (updater: (current: TourMachineState) => TourMachineState) => {
      setState((current) => {
        const next = updater(current);
        if (!next.booting) {
          safeLocalStorageSetValue(appTourStorageCodec, getPersistableTourState(next));
        }
        return next;
      });
    },
    [],
  );

  useEffect(() => {
    setState(getPersistedTourState());
  }, []);

  useEffect(() => {
    if (state.booting) return;
    if (state.status !== "pending") return;
    if (!isAutoEligibleTourPath(pathname)) return;

    const chapterId = getTourChapterForPathname(pathname);
    const nextStepId =
      pathname === "/"
        ? "tour.welcome"
        : chapterId
          ? getFirstTourStepIdForChapter(chapterId, "auto")
          : "tour.welcome";

    if (!nextStepId) return;

    commitState((current) => buildRunningState(current, nextStepId, "auto", pathname));
  }, [commitState, pathname, state.booting, state.status]);

  const stepDefinitions = useMemo(
    () => getTourStepsForMode(state.mode),
    [state.mode],
  );

  const currentStep = useMemo(
    () => (state.currentStepId ? getTourStepById(state.currentStepId) : null),
    [state.currentStepId],
  );

  const currentStepIndex = useMemo(() => {
    if (!state.currentStepId) return -1;
    return getTourStepIndex(state.currentStepId, state.mode);
  }, [state.currentStepId, state.mode]);

  const advanceToStep = useCallback(
    (stepId: TourStepId, mode: TourMode = state.mode) => {
      commitState((current) => buildRunningState(current, stepId, mode, pathname));
    },
    [commitState, pathname, state.mode],
  );

  const start = useCallback(() => {
    const chapterId = getTourChapterForPathname(pathname);
    const nextStepId =
      pathname === "/"
        ? "tour.welcome"
        : chapterId
          ? getFirstTourStepIdForChapter(chapterId, "manual")
          : "tour.welcome";

    if (!nextStepId) return;
    advanceToStep(nextStepId, "manual");
  }, [advanceToStep, pathname]);

  const resume = useCallback(() => {
    if (state.currentStepId) {
      advanceToStep(state.currentStepId, state.mode);
      return;
    }

    start();
  }, [advanceToStep, start, state.currentStepId, state.mode]);

  const restart = useCallback(() => {
    start();
  }, [start]);

  const openChapter = useCallback(
    (chapterId: TourChapterId) => {
      const nextStepId = getFirstTourStepIdForChapter(chapterId, "manual");
      if (!nextStepId) return;
      advanceToStep(nextStepId, "manual");
    },
    [advanceToStep],
  );

  const next = useCallback(() => {
    commitState((current) => {
      if (!current.currentStepId) return current;

      const nextStepId = getNextTourStepId(current.currentStepId, current.mode);
      const currentStepDefinition = getTourStepById(current.currentStepId);
      if (!currentStepDefinition) return current;

      if (!nextStepId) {
        return {
          ...current,
          booting: false,
          status: "completed",
          currentStepId: null,
          completedChapters: Array.from(
            new Set([...current.completedChapters, currentStepDefinition.chapterId]),
          ),
          completedAt: Date.now(),
          skippedAt: null,
          pendingRouteStepId: null,
          updatedAt: Date.now(),
        };
      }

      const nextStepDefinition = getTourStepById(nextStepId);
      const completedChapters =
        nextStepDefinition && nextStepDefinition.chapterId !== currentStepDefinition.chapterId
          ? Array.from(
              new Set([...current.completedChapters, currentStepDefinition.chapterId]),
            )
          : current.completedChapters;

      const shouldNavigate = nextStepDefinition?.routePattern
        ? !matchesTourRoutePattern(pathname, nextStepDefinition.routePattern)
        : false;

      return {
        ...current,
        booting: false,
        status: "running",
        currentStepId: nextStepId,
        completedChapters,
        pendingRouteStepId: shouldNavigate ? nextStepId : null,
        updatedAt: Date.now(),
      };
    });
  }, [commitState, pathname]);

  const back = useCallback(() => {
    commitState((current) => {
      if (!current.currentStepId) return current;
      const previousStepId = getPreviousTourStepId(current.currentStepId, current.mode);
      if (!previousStepId) return current;

      const previousStepDefinition = getTourStepById(previousStepId);
      const shouldNavigate = previousStepDefinition?.routePattern
        ? !matchesTourRoutePattern(pathname, previousStepDefinition.routePattern)
        : false;

      return {
        ...current,
        booting: false,
        status: "running",
        currentStepId: previousStepId,
        pendingRouteStepId: shouldNavigate ? previousStepId : null,
        updatedAt: Date.now(),
      };
    });
  }, [commitState, pathname]);

  const skipAll = useCallback(() => {
    commitState((current) => ({
      ...current,
      booting: false,
      status: "skipped",
      currentStepId: null,
      skippedAt: Date.now(),
      pendingRouteStepId: null,
      updatedAt: Date.now(),
    }));
  }, [commitState]);

  const acknowledgeRouteArrival = useCallback(() => {
    commitState((current) => ({
      ...current,
      pendingRouteStepId:
        current.currentStepId && current.pendingRouteStepId === current.currentStepId
          ? null
          : current.pendingRouteStepId,
    }));
  }, [commitState]);

  const value = useMemo<AppTourContextValue>(
    () => ({
      booting: state.booting,
      status: state.status,
      mode: state.mode,
      currentStep,
      currentStepId: state.currentStepId,
      currentStepIndex,
      currentStepCount: stepDefinitions.length,
      pendingRouteStepId: state.pendingRouteStepId,
      pathname,
      start,
      resume,
      next,
      back,
      skipAll,
      restart,
      openChapter,
      acknowledgeRouteArrival,
    }),
    [
      acknowledgeRouteArrival,
      back,
      currentStep,
      currentStepIndex,
      next,
      openChapter,
      pathname,
      restart,
      resume,
      skipAll,
      start,
      state.booting,
      state.currentStepId,
      state.mode,
      state.pendingRouteStepId,
      state.status,
      stepDefinitions.length,
    ],
  );

  return (
    <AppTourContext.Provider value={value}>
      <TourRouteBridge
        pathname={pathname}
        mobileNavOpen={mobileNavOpen}
        onMobileNavOpenChange={onMobileNavOpenChange}
      />
      {children}
      <TourHost />
    </AppTourContext.Provider>
  );
}
