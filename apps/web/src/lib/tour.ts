export const APP_TOUR_VERSION = 1;
export const APP_TOUR_STORAGE_KEY = "ui:onboarding-tour";

export const TOUR_CHAPTER_IDS = [
  "shell_intro",
  "overview",
  "control_plane_catalog",
  "control_plane_editor",
  "runtime",
  "sessions",
  "executions",
  "memory",
  "costs",
  "schedules",
  "dlq",
  "system_settings",
] as const;

export const TOUR_STEP_IDS = [
  "tour.welcome",
  "tour.shell.sidebar",
  "tour.shell.topbar",
  "tour.overview.metrics",
  "tour.overview.livePlan",
  "tour.controlPlane.primaryAction",
  "tour.controlPlane.board",
  "tour.controlPlaneEditor.header",
  "tour.controlPlaneEditor.steps",
  "tour.controlPlaneEditor.publish",
  "tour.runtime.header",
  "tour.runtime.liveList",
  "tour.sessions.rail",
  "tour.sessions.thread",
  "tour.executions.filters",
  "tour.executions.table",
  "tour.memory.primary",
  "tour.costs.primary",
  "tour.schedules.primary",
  "tour.dlq.primary",
  "tour.systemSettings.primary",
  "tour.complete",
] as const;

export type TourChapterId = (typeof TOUR_CHAPTER_IDS)[number];
export type TourStepId = (typeof TOUR_STEP_IDS)[number];
export type TourStatus = "pending" | "running" | "skipped" | "completed";
export type TourMode = "auto" | "manual";
export type TourVariant = "default" | "empty" | "loading" | "unavailable";
export type TourPlacement = "top" | "bottom" | "left" | "right" | "center";

export type TourRoutePattern =
  | "/"
  | "/control-plane"
  | "/control-plane/agents/:agentId"
  | "/runtime"
  | "/sessions"
  | "/executions"
  | "/memory"
  | "/costs"
  | "/schedules"
  | "/dlq"
  | "/control-plane/system";

export type TourRouteKey =
  | "overview"
  | "control-plane.catalog"
  | "control-plane.editor"
  | "runtime"
  | "sessions"
  | "executions"
  | "memory"
  | "costs"
  | "schedules"
  | "dlq"
  | "system-settings"
  | "shell.topbar"
  | "shell.sidebar";

export interface TourStepCopy {
  titleKey: string;
  descriptionKey: string;
  continueLabelKey?: string;
}

export interface TourStepDefinition {
  id: TourStepId;
  chapterId: TourChapterId;
  routePattern?: TourRoutePattern;
  routeKey?: TourRouteKey;
  kind: "modal" | "anchored";
  anchor?: string;
  fallbackAnchor?: string;
  navigationAnchor?: string;
  placement?: TourPlacement;
  autoIncluded: boolean;
  optional?: boolean;
  copy: Record<"default", TourStepCopy> & Partial<Record<Exclude<TourVariant, "default">, TourStepCopy>>;
}

export interface TourPersistenceState {
  version: number;
  status: TourStatus;
  currentStepId: TourStepId | null;
  completedChapters: TourChapterId[];
  updatedAt: number;
  completedAt: number | null;
  skippedAt: number | null;
}

export const TOUR_DEFAULT_PERSISTENCE_STATE: TourPersistenceState = {
  version: APP_TOUR_VERSION,
  status: "pending",
  currentStepId: null,
  completedChapters: [],
  updatedAt: 0,
  completedAt: null,
  skippedAt: null,
};

export const TOUR_STEPS: TourStepDefinition[] = [
  {
    id: "tour.welcome",
    chapterId: "shell_intro",
    routePattern: "/",
    routeKey: "overview",
    kind: "modal",
    placement: "center",
    autoIncluded: true,
    copy: {
      default: {
        titleKey: "tour.welcome.title",
        descriptionKey: "tour.welcome.description",
        continueLabelKey: "tour.actions.start",
      },
    },
  },
  {
    id: "tour.shell.sidebar",
    chapterId: "shell_intro",
    routePattern: "/",
    routeKey: "overview",
    kind: "anchored",
    anchor: "shell.sidebar.nav.home",
    fallbackAnchor: "shell.sidebar.brand",
    placement: "right",
    autoIncluded: true,
    copy: {
      default: {
        titleKey: "tour.steps.shellSidebar.title",
        descriptionKey: "tour.steps.shellSidebar.description",
      },
    },
  },
  {
    id: "tour.shell.topbar",
    chapterId: "shell_intro",
    routePattern: "/",
    routeKey: "shell.topbar",
    kind: "anchored",
    anchor: "shell.topbar.actions",
    fallbackAnchor: "shell.topbar.language-switcher.trigger",
    placement: "bottom",
    autoIncluded: true,
    copy: {
      default: {
        titleKey: "tour.steps.shellTopbar.title",
        descriptionKey: "tour.steps.shellTopbar.description",
      },
    },
  },
  {
    id: "tour.overview.metrics",
    chapterId: "overview",
    routePattern: "/",
    routeKey: "overview",
    kind: "anchored",
    anchor: "overview.stats",
    fallbackAnchor: "overview.bot-switcher",
    placement: "bottom",
    autoIncluded: true,
    copy: {
      default: {
        titleKey: "tour.steps.overviewMetrics.title",
        descriptionKey: "tour.steps.overviewMetrics.description",
      },
      empty: {
        titleKey: "tour.steps.overviewMetrics.emptyTitle",
        descriptionKey: "tour.steps.overviewMetrics.emptyDescription",
      },
    },
  },
  {
    id: "tour.overview.livePlan",
    chapterId: "overview",
    routePattern: "/",
    routeKey: "overview",
    kind: "anchored",
    anchor: "overview.live-plan",
    fallbackAnchor: "overview.runtime-control",
    placement: "top",
    autoIncluded: true,
    copy: {
      default: {
        titleKey: "tour.steps.overviewLivePlan.title",
        descriptionKey: "tour.steps.overviewLivePlan.description",
      },
    },
  },
  {
    id: "tour.controlPlane.primaryAction",
    chapterId: "control_plane_catalog",
    routePattern: "/control-plane",
    routeKey: "control-plane.catalog",
    kind: "anchored",
    anchor: "catalog.primary-actions",
    fallbackAnchor: "catalog.create-bot",
    placement: "bottom",
    autoIncluded: true,
    copy: {
      default: {
        titleKey: "tour.steps.controlPlanePrimaryAction.title",
        descriptionKey: "tour.steps.controlPlanePrimaryAction.description",
      },
      empty: {
        titleKey: "tour.steps.controlPlanePrimaryAction.emptyTitle",
        descriptionKey: "tour.steps.controlPlanePrimaryAction.emptyDescription",
      },
    },
  },
  {
    id: "tour.controlPlane.board",
    chapterId: "control_plane_catalog",
    routePattern: "/control-plane",
    routeKey: "control-plane.catalog",
    kind: "anchored",
    anchor: "catalog.board",
    fallbackAnchor: "catalog.empty",
    placement: "top",
    autoIncluded: true,
    copy: {
      default: {
        titleKey: "tour.steps.controlPlaneBoard.title",
        descriptionKey: "tour.steps.controlPlaneBoard.description",
      },
      empty: {
        titleKey: "tour.steps.controlPlaneBoard.emptyTitle",
        descriptionKey: "tour.steps.controlPlaneBoard.emptyDescription",
      },
    },
  },
  {
    id: "tour.controlPlaneEditor.header",
    chapterId: "control_plane_editor",
    routePattern: "/control-plane/agents/:agentId",
    routeKey: "control-plane.editor",
    kind: "anchored",
    anchor: "editor.header",
    fallbackAnchor: "editor.active-step",
    placement: "bottom",
    autoIncluded: true,
    optional: true,
    copy: {
      default: {
        titleKey: "tour.steps.controlPlaneEditorHeader.title",
        descriptionKey: "tour.steps.controlPlaneEditorHeader.description",
      },
    },
  },
  {
    id: "tour.controlPlaneEditor.steps",
    chapterId: "control_plane_editor",
    routePattern: "/control-plane/agents/:agentId",
    routeKey: "control-plane.editor",
    kind: "anchored",
    anchor: "editor.step-rail",
    fallbackAnchor: "editor.active-step",
    placement: "right",
    autoIncluded: true,
    optional: true,
    copy: {
      default: {
        titleKey: "tour.steps.controlPlaneEditorSteps.title",
        descriptionKey: "tour.steps.controlPlaneEditorSteps.description",
      },
    },
  },
  {
    id: "tour.controlPlaneEditor.publish",
    chapterId: "control_plane_editor",
    routePattern: "/control-plane/agents/:agentId",
    routeKey: "control-plane.editor",
    kind: "anchored",
    anchor: "editor.save",
    fallbackAnchor: "editor.next-step",
    placement: "left",
    autoIncluded: true,
    optional: true,
    copy: {
      default: {
        titleKey: "tour.steps.controlPlaneEditorPublish.title",
        descriptionKey: "tour.steps.controlPlaneEditorPublish.description",
      },
    },
  },
  {
    id: "tour.runtime.header",
    chapterId: "runtime",
    routePattern: "/runtime",
    routeKey: "runtime",
    kind: "anchored",
    anchor: "runtime.header",
    fallbackAnchor: "runtime.toolbar",
    placement: "bottom",
    autoIncluded: true,
    copy: {
      default: {
        titleKey: "tour.steps.runtimeHeader.title",
        descriptionKey: "tour.steps.runtimeHeader.description",
      },
      empty: {
        titleKey: "tour.steps.runtimeHeader.emptyTitle",
        descriptionKey: "tour.steps.runtimeHeader.emptyDescription",
      },
      unavailable: {
        titleKey: "tour.steps.runtimeHeader.unavailableTitle",
        descriptionKey: "tour.steps.runtimeHeader.unavailableDescription",
      },
    },
  },
  {
    id: "tour.runtime.liveList",
    chapterId: "runtime",
    routePattern: "/runtime",
    routeKey: "runtime",
    kind: "anchored",
    anchor: "runtime.metrics",
    fallbackAnchor: "runtime.empty-live",
    placement: "right",
    autoIncluded: true,
    copy: {
      default: {
        titleKey: "tour.steps.runtimeLiveList.title",
        descriptionKey: "tour.steps.runtimeLiveList.description",
      },
      empty: {
        titleKey: "tour.steps.runtimeLiveList.emptyTitle",
        descriptionKey: "tour.steps.runtimeLiveList.emptyDescription",
      },
    },
  },
  {
    id: "tour.sessions.rail",
    chapterId: "sessions",
    routePattern: "/sessions",
    routeKey: "sessions",
    kind: "anchored",
    anchor: "sessions.rail-header",
    fallbackAnchor: "sessions.conversation-rail",
    placement: "right",
    autoIncluded: true,
    copy: {
      default: {
        titleKey: "tour.steps.sessionsRail.title",
        descriptionKey: "tour.steps.sessionsRail.description",
      },
      empty: {
        titleKey: "tour.steps.sessionsRail.emptyTitle",
        descriptionKey: "tour.steps.sessionsRail.emptyDescription",
      },
    },
  },
  {
    id: "tour.sessions.thread",
    chapterId: "sessions",
    routePattern: "/sessions",
    routeKey: "sessions",
    kind: "anchored",
    anchor: "sessions.thread",
    fallbackAnchor: "sessions.composer",
    placement: "left",
    autoIncluded: true,
    copy: {
      default: {
        titleKey: "tour.steps.sessionsThread.title",
        descriptionKey: "tour.steps.sessionsThread.description",
      },
      empty: {
        titleKey: "tour.steps.sessionsThread.emptyTitle",
        descriptionKey: "tour.steps.sessionsThread.emptyDescription",
      },
    },
  },
  {
    id: "tour.executions.filters",
    chapterId: "executions",
    routePattern: "/executions",
    routeKey: "executions",
    kind: "anchored",
    anchor: "executions.search",
    fallbackAnchor: "executions.status-filters",
    placement: "bottom",
    autoIncluded: true,
    copy: {
      default: {
        titleKey: "tour.steps.executionsFilters.title",
        descriptionKey: "tour.steps.executionsFilters.description",
      },
      unavailable: {
        titleKey: "tour.steps.executionsFilters.unavailableTitle",
        descriptionKey: "tour.steps.executionsFilters.unavailableDescription",
      },
    },
  },
  {
    id: "tour.executions.table",
    chapterId: "executions",
    routePattern: "/executions",
    routeKey: "executions",
    kind: "anchored",
    anchor: "executions.table",
    fallbackAnchor: "executions.metrics",
    placement: "top",
    autoIncluded: true,
    copy: {
      default: {
        titleKey: "tour.steps.executionsTable.title",
        descriptionKey: "tour.steps.executionsTable.description",
      },
      empty: {
        titleKey: "tour.steps.executionsTable.emptyTitle",
        descriptionKey: "tour.steps.executionsTable.emptyDescription",
      },
      unavailable: {
        titleKey: "tour.steps.executionsTable.unavailableTitle",
        descriptionKey: "tour.steps.executionsTable.unavailableDescription",
      },
    },
  },
  {
    id: "tour.memory.primary",
    chapterId: "memory",
    routePattern: "/memory",
    routeKey: "memory",
    kind: "anchored",
    anchor: "memory.primary",
    fallbackAnchor: "page.header",
    placement: "bottom",
    autoIncluded: false,
    copy: {
      default: {
        titleKey: "tour.steps.memoryPrimary.title",
        descriptionKey: "tour.steps.memoryPrimary.description",
      },
    },
  },
  {
    id: "tour.costs.primary",
    chapterId: "costs",
    routePattern: "/costs",
    routeKey: "costs",
    kind: "anchored",
    anchor: "costs.primary",
    fallbackAnchor: "page.header",
    placement: "bottom",
    autoIncluded: false,
    copy: {
      default: {
        titleKey: "tour.steps.costsPrimary.title",
        descriptionKey: "tour.steps.costsPrimary.description",
      },
    },
  },
  {
    id: "tour.schedules.primary",
    chapterId: "schedules",
    routePattern: "/schedules",
    routeKey: "schedules",
    kind: "anchored",
    anchor: "schedules.primary",
    fallbackAnchor: "page.header",
    placement: "bottom",
    autoIncluded: false,
    copy: {
      default: {
        titleKey: "tour.steps.schedulesPrimary.title",
        descriptionKey: "tour.steps.schedulesPrimary.description",
      },
    },
  },
  {
    id: "tour.dlq.primary",
    chapterId: "dlq",
    routePattern: "/dlq",
    routeKey: "dlq",
    kind: "anchored",
    anchor: "dlq.primary",
    fallbackAnchor: "page.header",
    placement: "bottom",
    autoIncluded: false,
    copy: {
      default: {
        titleKey: "tour.steps.dlqPrimary.title",
        descriptionKey: "tour.steps.dlqPrimary.description",
      },
    },
  },
  {
    id: "tour.systemSettings.primary",
    chapterId: "system_settings",
    routePattern: "/control-plane/system",
    routeKey: "system-settings",
    kind: "anchored",
    anchor: "system-settings.primary",
    fallbackAnchor: "page.header",
    placement: "bottom",
    autoIncluded: false,
    copy: {
      default: {
        titleKey: "tour.steps.systemSettingsPrimary.title",
        descriptionKey: "tour.steps.systemSettingsPrimary.description",
      },
    },
  },
  {
    id: "tour.complete",
    chapterId: "executions",
    routePattern: "/executions",
    routeKey: "executions",
    kind: "modal",
    placement: "center",
    autoIncluded: true,
    copy: {
      default: {
        titleKey: "tour.complete.title",
        descriptionKey: "tour.complete.description",
        continueLabelKey: "tour.actions.finish",
      },
    },
  },
] as const;

export const AUTO_TOUR_STEP_IDS = TOUR_STEPS.filter((step) => step.autoIncluded).map(
  (step) => step.id,
);

export const MANUAL_TOUR_STEP_IDS = TOUR_STEPS.map((step) => step.id);

export function isTourChapterId(value: string): value is TourChapterId {
  return (TOUR_CHAPTER_IDS as readonly string[]).includes(value);
}

export function isTourStepId(value: string): value is TourStepId {
  return (TOUR_STEP_IDS as readonly string[]).includes(value);
}

export function getTourStepById(stepId: TourStepId) {
  return TOUR_STEPS.find((step) => step.id === stepId) ?? null;
}

export function getTourStepsForMode(mode: TourMode) {
  const includedIds = mode === "manual" ? MANUAL_TOUR_STEP_IDS : AUTO_TOUR_STEP_IDS;
  return TOUR_STEPS.filter((step) => includedIds.includes(step.id));
}

export function getTourStepIndex(stepId: TourStepId, mode: TourMode) {
  return getTourStepsForMode(mode).findIndex((step) => step.id === stepId);
}

export function getNextTourStepId(stepId: TourStepId, mode: TourMode) {
  const steps = getTourStepsForMode(mode);
  const index = steps.findIndex((step) => step.id === stepId);
  if (index === -1) return null;
  return steps[index + 1]?.id ?? null;
}

export function getPreviousTourStepId(stepId: TourStepId, mode: TourMode) {
  const steps = getTourStepsForMode(mode);
  const index = steps.findIndex((step) => step.id === stepId);
  if (index <= 0) return null;
  return steps[index - 1]?.id ?? null;
}

export function getOptionalTourRecoveryAction(
  stepId: TourStepId,
  mode: TourMode,
  pathname: string,
) {
  const routeChapter = getTourChapterForPathname(pathname);
  if (!routeChapter) {
    return "next" as const;
  }

  const routeChapterFirstStepId = getFirstTourStepIdForChapter(routeChapter, mode);
  if (!routeChapterFirstStepId) {
    return "next" as const;
  }

  const currentIndex = getTourStepIndex(stepId, mode);
  const routeChapterIndex = getTourStepIndex(routeChapterFirstStepId, mode);
  if (currentIndex === -1 || routeChapterIndex === -1) {
    return "next" as const;
  }

  return currentIndex < routeChapterIndex ? ("back" as const) : ("next" as const);
}

export function getTourChapterStepIds(chapterId: TourChapterId, mode: TourMode) {
  return getTourStepsForMode(mode)
    .filter((step) => step.chapterId === chapterId)
    .map((step) => step.id);
}

export function getFirstTourStepIdForChapter(chapterId: TourChapterId, mode: TourMode) {
  return getTourStepsForMode(mode).find((step) => step.chapterId === chapterId)?.id ?? null;
}

export function normalizeTourPathname(pathname: string) {
  if (pathname === "") return "/";
  if (pathname.length > 1 && pathname.endsWith("/")) {
    return pathname.slice(0, -1);
  }
  return pathname;
}

export function matchesTourRoutePattern(pathname: string, pattern?: TourRoutePattern) {
  if (!pattern) return true;

  const normalizedPathname = normalizeTourPathname(pathname);
  if (!pattern.includes(":")) {
    return normalizedPathname === pattern;
  }

  if (pattern === "/control-plane/agents/:agentId") {
    return /^\/control-plane\/agents\/[^/]+$/.test(normalizedPathname);
  }

  return false;
}

export function getTourChapterForPathname(pathname: string): TourChapterId | null {
  const normalizedPathname = normalizeTourPathname(pathname);

  if (normalizedPathname.startsWith("/control-plane/system")) {
    return "system_settings";
  }
  if (/^\/control-plane\/agents\/[^/]+$/.test(normalizedPathname)) {
    return "control_plane_editor";
  }
  if (normalizedPathname === "/control-plane") {
    return "control_plane_catalog";
  }
  if (normalizedPathname.startsWith("/runtime")) {
    return "runtime";
  }
  if (normalizedPathname.startsWith("/sessions")) {
    return "sessions";
  }
  if (normalizedPathname.startsWith("/executions")) {
    return "executions";
  }
  if (normalizedPathname.startsWith("/memory")) {
    return "memory";
  }
  if (normalizedPathname.startsWith("/costs")) {
    return "costs";
  }
  if (normalizedPathname.startsWith("/schedules")) {
    return "schedules";
  }
  if (normalizedPathname.startsWith("/dlq")) {
    return "dlq";
  }
  if (normalizedPathname === "/") {
    return "overview";
  }

  return null;
}

export function isAutoEligibleTourPath(pathname: string) {
  const chapterId = getTourChapterForPathname(pathname);
  if (!chapterId) return false;

  return [
    "overview",
    "control_plane_catalog",
    "control_plane_editor",
    "runtime",
    "sessions",
    "executions",
  ].includes(chapterId);
}

export function resolveTourPersistenceState(
  persisted: Partial<TourPersistenceState> | null | undefined,
): TourPersistenceState {
  if (!persisted || persisted.version !== APP_TOUR_VERSION) {
    return TOUR_DEFAULT_PERSISTENCE_STATE;
  }

  const currentStepId =
    typeof persisted.currentStepId === "string" && isTourStepId(persisted.currentStepId)
      ? persisted.currentStepId
      : null;

  return {
    version: APP_TOUR_VERSION,
    status:
      persisted.status === "running" ||
      persisted.status === "skipped" ||
      persisted.status === "completed"
        ? persisted.status
        : "pending",
    currentStepId,
    completedChapters: Array.isArray(persisted.completedChapters)
      ? persisted.completedChapters.filter(isTourChapterId)
      : [],
    updatedAt: typeof persisted.updatedAt === "number" ? persisted.updatedAt : 0,
    completedAt: typeof persisted.completedAt === "number" ? persisted.completedAt : null,
    skippedAt: typeof persisted.skippedAt === "number" ? persisted.skippedAt : null,
  };
}

export function resolveTourCopy(step: TourStepDefinition, variant: TourVariant) {
  return step.copy[variant] ?? step.copy.default;
}
