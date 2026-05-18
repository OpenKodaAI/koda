"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Globe,
  LoaderCircle,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  Save,
  type LucideIcon,
  Waypoints,
} from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { RuntimeActionMenu } from "@/components/runtime/runtime-action-menu";
import { RuntimeBrowserPanel } from "@/components/runtime/runtime-browser-panel";
import { RuntimeFilesPanel } from "@/components/runtime/runtime-files-panel";
import {
  ChildRunsPanel,
  ContextGovernancePanel,
  RunGraphSummaryPanel,
  RunGraphViewer,
  RunReplayPanel,
} from "@/components/runtime/run-graph-panels";
import { SandboxDoctorPanel } from "@/components/runtime/sandbox-doctor-panel";
import { EventRow, type EventLevel } from "@/components/runtime/shared/event-row";
import { Button } from "@/components/ui/button";
import { Drawer } from "@/components/ui/drawer";
import {
  DetailBlock as SharedDetailBlock,
  DetailDatum as SharedDetailDatum,
  DetailGrid as SharedDetailGrid,
} from "@/components/ui/detail-group";
import { SoftTabs } from "@/components/ui/soft-tabs";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import { useRuntimeTask } from "@/hooks/use-runtime-task";
import { useToast } from "@/hooks/use-toast";
import { translate } from "@/lib/i18n";
import { getAgentLabel } from "@/lib/agent-constants";
import { parseRunGraphSnapshot, parseRunReplayPlan } from "@/lib/contracts/run-graph";
import { parseContextGovernancePayload } from "@/lib/contracts/phase3-runtime";
import { parseSandboxDoctorResult } from "@/lib/contracts/sandbox-doctor";
import type { SemanticTone } from "@/lib/theme-semantic";
import type { RuntimeEvent } from "@/lib/runtime-types";
import {
  formatBytes,
  formatPercent,
  getRuntimeLabel,
  getRuntimeSeverityTone,
  getRuntimeTone,
} from "@/lib/runtime-ui";
import { cn, formatDateTime, formatRelativeTime, truncateText } from "@/lib/utils";
import { SyntaxHighlight } from "@/components/shared/syntax-highlight";

type RoomTab = "activity" | "terminal" | "browser" | "files";
type DetailTab = "details" | "runGraph" | "logs" | "diagnostics";

interface RuntimeStageStat {
  label: string;
  value: ReactNode;
}

const RuntimeTerminalPanel = dynamic(
  () =>
    import("@/components/runtime/runtime-terminal-panel").then((module) => ({
      default: module.RuntimeTerminalPanel,
    })),
  {
    ssr: false,
    loading: () => <TerminalPanelLoading />,
  },
);

interface RuntimeTaskRoomProps {
  agentId: string;
  taskId: number;
}

function toneToDot(tone: SemanticTone): StatusDotTone {
  if (
    tone === "success" ||
    tone === "info" ||
    tone === "warning" ||
    tone === "danger" ||
    tone === "retry" ||
    tone === "neutral"
  ) {
    return tone;
  }
  return "neutral";
}

function TerminalPanelLoading() {
  const { tl } = useAppI18n();
  return (
    <div className="flex min-h-[360px] items-center justify-center bg-[var(--terminal-background)] text-[0.8125rem] text-[var(--text-tertiary)]">
      {tl("Preparando terminal...")}
    </div>
  );
}

function RuntimeGitSyntax({
  text,
  fallback,
  lineNumbers = false,
}: {
  text: string | null | undefined;
  fallback: string;
  lineNumbers?: boolean;
}) {
  const value = text?.trimEnd() || fallback;

  return (
    <SyntaxHighlight
      lang="diff"
      lineNumbers={lineNumbers && Boolean(text?.trim())}
      className="runtime-git-syntax"
    >
      {value}
    </SyntaxHighlight>
  );
}

function LiveRuntimeBadge() {
  const { t } = useAppI18n();
  return (
    <span
      className="inline-flex h-5 items-center gap-1.5 rounded-[var(--radius-chip)] px-1.5 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-tertiary)]"
    >
      <StatusDot tone="success" pulse />
      {t("runtime.room.liveSample")}
    </span>
  );
}

function RuntimeTaskHeader({
  agentId,
  taskId,
  title,
  currentPhase,
  phaseTone,
  isLivePhase,
  connected,
  branchName,
  heartbeatLabel,
  actionRail,
}: {
  agentId: string;
  taskId: number;
  title: string;
  currentPhase: string;
  phaseTone: StatusDotTone;
  isLivePhase: boolean;
  connected: boolean;
  branchName: string | null;
  heartbeatLabel: string;
  actionRail: ReactNode;
}) {
  const { t } = useAppI18n();

  return (
    <header className="border-b border-[color:var(--divider-hair)] pb-4">
      <div className="flex min-w-0 flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2 font-mono text-[0.72rem] text-[var(--text-tertiary)]">
            <Link
              href={`/runtime?agent=${agentId}`}
              className="inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-panel-sm)] text-[var(--text-tertiary)] transition-[background-color,color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--focus-ring)]"
              aria-label={t("common.back")}
            >
              <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} />
            </Link>
            <span className="font-medium text-[var(--text-secondary)]">Task #{taskId}</span>
            <span className="text-[var(--text-quaternary)]">/</span>
            <span className="truncate">{getAgentLabel(agentId)}</span>
            <span className="text-[var(--text-quaternary)]">/</span>
            <span className="inline-flex items-center gap-1.5">
              <StatusDot tone={phaseTone} pulse={isLivePhase} />
              {currentPhase}
            </span>
            {connected ? (
              <>
                <span className="text-[var(--text-quaternary)]">/</span>
                <span className="inline-flex items-center gap-1.5">
                  <StatusDot tone="success" pulse />
                  {t("runtime.overview.live")}
                </span>
              </>
            ) : null}
            <span className="text-[var(--text-quaternary)]">/</span>
            <span>{heartbeatLabel}</span>
            <LiveRuntimeBadge />
          </div>

          <h1 className="m-0 mt-2 max-w-[860px] text-[1.125rem] font-medium leading-[1.24] tracking-[var(--tracking-tight)] text-[var(--text-primary)] [text-wrap:balance] sm:text-[1.25rem]">
            {title}
          </h1>

          {branchName ? (
            <div className="mt-2 flex min-w-0 flex-wrap items-center gap-2 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
              <span className="truncate">{branchName}</span>
            </div>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center lg:justify-end lg:pt-0.5">
          {actionRail}
        </div>
      </div>
    </header>
  );
}

function RuntimeActionRail({
  isPaused,
  isPinned,
  busyAction,
  actionsOpen,
  setActionsOpen,
  runAction,
  refresh,
  openDetails,
}: {
  isPaused: boolean;
  isPinned: boolean;
  busyAction: string | null;
  actionsOpen: boolean;
  setActionsOpen: (open: boolean) => void;
  runAction: (
    action: string,
    label: string,
    options?: { confirmMessage?: string; searchParams?: URLSearchParams },
  ) => void;
  refresh: () => Promise<void>;
  openDetails: () => void;
}) {
  const { t } = useAppI18n();

  return (
    <div
      className="inline-flex max-w-full flex-wrap items-center gap-1 rounded-[var(--radius-panel)] border border-[color:var(--divider-hair)] bg-[var(--panel-soft)] p-1"
      aria-label={t("runtime.room.executionActions")}
    >
      <ActionButton
        onClick={() =>
          runAction(
            isPaused ? "resume" : "pause",
            isPaused ? t("runtime.room.resume") : t("runtime.room.pause"),
          )
        }
        busy={busyAction === "pause" || busyAction === "resume"}
        icon={isPaused ? Play : Pause}
        label={isPaused ? t("runtime.room.resume") : t("runtime.room.pause")}
        tone="primary"
      />
      <ActionButton
        onClick={() => runAction("save", t("runtime.room.saveSnapshot"))}
        busy={busyAction === "save"}
        icon={Save}
        label={t("common.save")}
      />

      <RuntimeActionMenu
        open={actionsOpen}
        onOpenChange={setActionsOpen}
        isPinned={isPinned}
        busyAction={busyAction}
        onRefresh={() => void refresh()}
        runAction={runAction}
      />

      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-8 rounded-[var(--radius-chip)] border-transparent px-2.5 text-[0.8125rem] font-medium text-[var(--text-secondary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]"
        onClick={openDetails}
      >
        {t("runtime.room.details")}
      </Button>
      <Button
        asChild
        variant="ghost"
        size="sm"
        className="h-8 rounded-[var(--radius-chip)] border-transparent px-2.5 text-[0.8125rem] font-medium text-[var(--text-secondary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]"
      >
        <Link href="/executions">{t("runtime.room.history")}</Link>
      </Button>
    </div>
  );
}

function RuntimeStageShell({
  tabs,
  activeTab,
  onTabChange,
  fullscreen,
  onToggleFullscreen,
  progressPercent,
  stats,
  children,
}: {
  tabs: Array<{ id: RoomTab; label: string }>;
  activeTab: RoomTab;
  onTabChange: (tab: RoomTab) => void;
  fullscreen: boolean;
  onToggleFullscreen: () => void;
  progressPercent: number | null;
  stats: RuntimeStageStat[];
  children: ReactNode;
}) {
  const { t } = useAppI18n();
  const fullscreenLabel = fullscreen
    ? t("runtime.room.exitFullscreen")
    : t("runtime.room.expandSurface");

  return (
    <section
      className={cn(
        "runtime-stage-shell flex min-h-[clamp(440px,calc(100dvh-230px),780px)] flex-col overflow-hidden rounded-[var(--radius-shell)] border border-[color:var(--divider-hair)] bg-[var(--panel)] shadow-[var(--shadow-xs)]",
        fullscreen && "runtime-stage-shell--fullscreen",
      )}
      aria-label={t("runtime.room.trackingLabel")}
      data-testid="runtime-stage-shell"
    >
      <div className="runtime-stage-shell__header flex flex-col gap-2 border-b border-[color:var(--divider-hair)] px-2.5 py-2 sm:flex-row sm:items-center sm:justify-between sm:px-3">
        <div className="-mx-1 overflow-x-auto px-1">
          <SoftTabs
            items={tabs}
            value={activeTab}
            onChange={(id) => onTabChange(id as RoomTab)}
            ariaLabel={t("runtime.room.switchSurface")}
          />
        </div>
        <button
          type="button"
          className="runtime-stage-shell__expand"
          onClick={onToggleFullscreen}
          aria-label={fullscreenLabel}
          title={fullscreenLabel}
        >
          {fullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
        </button>
      </div>

      <div className="runtime-stage-shell__body min-h-0 flex-1 overflow-auto">{children}</div>

      <ProgressBar percent={progressPercent} />
      <RuntimeStatFooter stats={stats} />
    </section>
  );
}

function RuntimeStatFooter({ stats }: { stats: RuntimeStageStat[] }) {
  return (
    <footer className="border-t border-[color:var(--divider-hair)] bg-[var(--panel)] px-3 py-2">
      <dl className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1">
        {stats.map((item) => (
          <div
            key={item.label}
            className="flex min-w-0 items-baseline gap-1.5 font-mono"
          >
            <dt className="m-0 truncate text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
              {item.label}
            </dt>
            <dd className="m-0 truncate text-[0.75rem] text-[var(--text-secondary)]">
              {item.value}
            </dd>
          </div>
        ))}
      </dl>
    </footer>
  );
}

export function RuntimeTaskRoom({ agentId, taskId }: RuntimeTaskRoomProps) {
  const { t, tl } = useAppI18n();
  const { showToast } = useToast();
  const warningToastKeysRef = useRef<Set<string>>(new Set());
  const { bundle, loading, error, connected, mutate, fetchResource, refresh } =
    useRuntimeTask(agentId, taskId);
  const [activeTab, setActiveTab] = useState<RoomTab>("terminal");
  const [detailTab, setDetailTab] = useState<DetailTab>("details");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [actionsOpen, setActionsOpen] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [stageFullscreen, setStageFullscreen] = useState(false);

  const latestResource = bundle?.resources.at(-1) ?? null;
  const latestCheckpoint = bundle?.checkpoints.at(-1) ?? null;
  const runGraph = useMemo(
    () => parseRunGraphSnapshot(bundle?.run_graph ?? null),
    [bundle?.run_graph],
  );
  const runReplay = useMemo(
    () => parseRunReplayPlan(bundle?.run_replay ?? null) ?? runGraph?.replay ?? null,
    [bundle?.run_replay, runGraph],
  );
  const sandboxDoctor = useMemo(
    () => parseSandboxDoctorResult(bundle?.sandbox_doctor ?? null),
    [bundle?.sandbox_doctor],
  );
  const childRuns = bundle?.child_runs ?? [];
  const contextGovernance = useMemo(
    () => parseContextGovernancePayload(bundle?.context_governance ?? null),
    [bundle?.context_governance],
  );
  const isPaused = bundle?.environment?.pause_state
    ? String(bundle.environment.pause_state).includes("pause")
    : String(bundle?.environment?.current_phase || "").includes("paused");
  const isPinned = Boolean(bundle?.environment?.is_pinned);

  const roomTabs = [
    { id: "terminal", label: t("runtime.room.tabs.terminal") },
    { id: "browser", label: t("runtime.room.tabs.browser") },
    { id: "files", label: t("runtime.room.tabs.files") },
    { id: "activity", label: t("runtime.room.tabs.activity") },
  ] satisfies Array<{ id: RoomTab; label: string }>;

  const detailTabs = [
    { id: "details", label: t("runtime.room.detailTabs.details") },
    { id: "runGraph", label: "RunGraph" },
    { id: "logs", label: "Logs" },
    { id: "diagnostics", label: t("runtime.room.detailTabs.diagnostics") },
  ] satisfies Array<{ id: DetailTab; label: string }>;

  const heroTitle = truncateText(
    bundle?.task?.query_text ||
      bundle?.events.at(-1)?.type ||
      t("runtime.room.executionLive"),
    160,
  );
  const currentPhase = getRuntimeLabel(
    bundle?.task?.current_phase || bundle?.environment?.current_phase || bundle?.task?.status,
  );
  const currentStatus = String(bundle?.task?.status || bundle?.environment?.status || "queued");
  const sourceRootPath =
    bundle?.environment?.source_root_path || bundle?.environment?.base_work_dir || "";
  const sourceRootMissing =
    Boolean(bundle?.environment?.source_root_path) &&
    bundle?.environment?.source_root_exists === false;
  const heartbeatAt =
    bundle?.environment?.last_heartbeat_at ||
    bundle?.task?.last_heartbeat_at ||
    bundle?.environment?.updated_at ||
    bundle?.task?.started_at ||
    null;

  const phaseTone = toneToDot(
    getRuntimeTone(bundle?.environment?.current_phase || bundle?.task?.current_phase),
  );
  const isLivePhase = phaseTone === "info" || phaseTone === "warning";

  useEffect(() => {
    if (!bundle) return;
    const nextKeys = new Set<string>();
    for (const warning of bundle.warnings.slice(-3)) {
      const key = String(warning.id);
      nextKeys.add(key);
      if (warningToastKeysRef.current.has(key)) continue;
      showToast(warning.message || warning.warning_type || t("runtime.room.warnings"), "warning", {
        id: `runtime-task:${taskId}:warning:${key}`,
      });
    }
    warningToastKeysRef.current = nextKeys;
  }, [bundle, showToast, t, taskId]);

  useEffect(() => {
    if (!stageFullscreen) return;
    document.body.classList.add("runtime-stage-fullscreen-lock");
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setStageFullscreen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.classList.remove("runtime-stage-fullscreen-lock");
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [stageFullscreen]);

  const essentialStats = useMemo(
    () => [
      {
        label: t("runtime.room.stats.state"),
        value: getRuntimeLabel(bundle?.environment?.status || bundle?.task?.status || "queued"),
      },
      {
        label: t("runtime.room.stats.phase"),
        value: currentPhase,
      },
      {
        label: t("runtime.room.stats.cpu"),
        value: formatPercent(latestResource?.cpu_percent),
      },
      {
        label: t("runtime.room.stats.memory"),
        value: formatBytes(
          latestResource?.rss_kb != null ? latestResource.rss_kb * 1024 : null,
        ),
      },
      {
        label: t("runtime.room.stats.now"),
        value: heartbeatAt ? formatRelativeTime(heartbeatAt) : t("runtime.room.stats.noHeartbeat"),
      },
    ],
    [bundle?.environment?.status, bundle?.task?.status, currentPhase, latestResource, heartbeatAt, t],
  );

  const runAction = async (
    action: string,
    label: string,
    options?: {
      confirmMessage?: string;
      searchParams?: URLSearchParams;
    },
  ) => {
    if (options?.confirmMessage && !window.confirm(options.confirmMessage)) {
      return;
    }

    setBusyAction(action);
    setActionsOpen(false);

    try {
      await mutate(action, { searchParams: options?.searchParams });
      showToast(t("runtime.room.completed", { label }), "success", {
        id: `runtime-task:${taskId}:action`,
      });
    } catch (actionError) {
      const message =
        actionError instanceof Error ? actionError.message : `${t("common.failed")} ${label}`;
      showToast(message, "error", { id: `runtime-task:${taskId}:action` });
    } finally {
      setBusyAction(null);
    }
  };

  const runChildAction = async (
    childRun: (typeof childRuns)[number],
    action: "cancel" | "interrupt",
  ) => {
    if (!childRun.child_task_id) return;
    const actionKey = `${childRun.child_run_id}:${action}`;
    setBusyAction(actionKey);
    try {
      const response = await fetch(
        `/api/runtime/agents/${agentId}/tasks/${childRun.child_task_id}/${action}`,
        { method: "POST" },
      );
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(
          typeof payload?.error === "string"
            ? payload.error
            : "Action failed.",
        );
      }
      await refresh();
      showToast(t("runtime.room.completed", { label: action }), "success", {
        id: `runtime-child:${childRun.child_run_id}:action`,
      });
    } catch (actionError) {
      const message =
        actionError instanceof Error ? actionError.message : `${t("common.failed")} ${action}`;
      showToast(message, "error", { id: `runtime-child:${childRun.child_run_id}:action` });
    } finally {
      setBusyAction(null);
    }
  };

  if (loading && !bundle) {
    return (
      <div className="runtime-shell space-y-6">
        <div className="space-y-3">
          <div className="skeleton h-4 w-24 rounded" />
          <div className="skeleton h-10 w-80 rounded" />
        </div>
        <div className="skeleton min-h-[520px] w-full rounded-[var(--radius-panel)]" />
      </div>
    );
  }

  if (!bundle || error) {
    return (
      <div className="runtime-shell">
        <div className="flex min-h-[320px] flex-col items-center justify-center gap-3 rounded-[var(--radius-panel)] border border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] p-8 text-center">
          <AlertTriangle className="h-6 w-6 text-[var(--tone-danger-dot)]" />
          <p className="m-0 text-base font-medium text-[var(--text-primary)]">
            {t("runtime.room.openErrorTitle")}
          </p>
          <p className="m-0 max-w-xl text-[0.8125rem] leading-6 text-[var(--text-tertiary)]">
            {error || t("runtime.room.openErrorDescription")}
          </p>
          <Link
            href="/runtime"
            className="mt-2 inline-flex h-8 items-center gap-2 rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 text-[0.8125rem] text-[var(--text-primary)] transition-colors hover:border-[var(--border-strong)]"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            {t("common.back")}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="runtime-shell runtime-shell--wide runtime-task-room flex flex-col gap-3" data-testid="runtime-task-room">
      <RuntimeTaskHeader
        agentId={agentId}
        taskId={taskId}
        title={heroTitle}
        currentPhase={currentPhase}
        phaseTone={phaseTone}
        isLivePhase={isLivePhase}
        connected={connected}
        branchName={bundle.environment?.branch_name || null}
        heartbeatLabel={heartbeatAt ? formatRelativeTime(heartbeatAt) : t("runtime.room.stats.noHeartbeat")}
        actionRail={
          <RuntimeActionRail
            isPaused={isPaused}
            isPinned={isPinned}
            busyAction={busyAction}
            actionsOpen={actionsOpen}
            setActionsOpen={setActionsOpen}
            refresh={refresh}
            runAction={(action, label, options) => void runAction(action, label, options)}
            openDetails={() => {
              setDetailTab("details");
              setDetailsOpen(true);
            }}
          />
        }
      />

      <RuntimeStageShell
        tabs={roomTabs}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        fullscreen={stageFullscreen}
        onToggleFullscreen={() => setStageFullscreen((current) => !current)}
        progressPercent={
          typeof bundle.environment?.progress_percent === "number"
            ? bundle.environment.progress_percent
            : null
        }
        stats={essentialStats}
      >
          {activeTab === "terminal" ? (
            <RuntimeTerminalPanel
              taskId={taskId}
              terminals={bundle.terminals}
              mutate={mutate}
              fetchResource={fetchResource}
            />
          ) : null}

          {activeTab === "browser" ? (
            <div className="p-3 sm:p-4">
              <RuntimeBrowserPanel
                agentId={agentId}
                taskId={taskId}
                browser={bundle.browser}
                mutate={mutate}
                fetchResource={fetchResource}
              />
            </div>
          ) : null}

          {activeTab === "files" ? (
            <RuntimeFilesPanel
              taskId={taskId}
              workspaceTree={bundle.workspaceTree}
              workspaceStatus={bundle.workspaceStatus}
              mutate={mutate}
              fetchResource={fetchResource}
            />
          ) : null}

          {activeTab === "activity" ? (
            <div className="space-y-3 p-3 sm:p-4">
              {bundle.events.length === 0 ? (
                <div className="flex min-h-[320px] flex-col items-center justify-center gap-2 py-10 text-center text-[0.8125rem] text-[var(--text-tertiary)]">
                  <Activity className="h-4 w-4 text-[var(--text-quaternary)]" />
                  <p className="m-0">{t("runtime.room.noMovementYet")}</p>
                </div>
              ) : (
                <div className="px-1">
                  {bundle.events
                    .slice()
                    .reverse()
                    .slice(0, 14)
                    .map((event) => (
                      <RuntimeEventFeedRow key={event.seq} event={event} />
                    ))}
                </div>
              )}
            </div>
          ) : null}
      </RuntimeStageShell>

      {/* Detail Drawer */}
      <Drawer
        open={detailsOpen}
        onOpenChange={setDetailsOpen}
        title={t("runtime.room.details")}
        closeLabel={t("runtime.room.closeDetailsPanel")}
        width="min(560px, 92vw)"
      >
        <div className="flex flex-col gap-4 p-5">
          <SoftTabs
            items={detailTabs}
            value={detailTab}
            onChange={(id) => setDetailTab(id as DetailTab)}
            ariaLabel={t("runtime.room.detailTabsAria")}
            className="self-start"
          />

          {detailTab === "details" ? (
            <div className="space-y-5">
              <SharedDetailGrid>
                <SharedDetailDatum label={t("common.agent")} value={agentId} />
                <SharedDetailDatum label={t("common.task")} value={`#${taskId}`} />
                <SharedDetailDatum
                  label={t("common.status")}
                  value={
                    <span className="inline-flex items-center gap-1.5">
                      <StatusDot tone={toneToDot(getRuntimeTone(currentStatus))} />
                      {getRuntimeLabel(currentStatus)}
                    </span>
                  }
                />
                <SharedDetailDatum label={t("common.phase")} value={currentPhase} />
                <SharedDetailDatum
                  label={t("runtime.room.branch")}
                  value={
                    <span className="font-mono text-[0.75rem]">
                      {bundle.environment?.branch_name || "—"}
                    </span>
                  }
                />
                <SharedDetailDatum
                  label={t("runtime.room.retention")}
                  value={
                    bundle.environment?.retention_expires_at
                      ? formatDateTime(bundle.environment.retention_expires_at)
                      : "—"
                  }
                />
              </SharedDetailGrid>

              <SharedDetailBlock title="Source root" monospace>
                {sourceRootPath || "—"}
              </SharedDetailBlock>

              {sourceRootMissing ? (
                <div
                  className="flex items-start gap-2 rounded-[var(--radius-panel-sm)] border border-[color:var(--tone-warning-border)] bg-[var(--tone-warning-bg)] px-3 py-2 text-xs leading-relaxed text-[var(--tone-warning-text)]"
                  role="status"
                >
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  <span>
                    {t("runtime.room.sourceRootMissing", {
                      defaultValue:
                        "Source root is unavailable. The task workspace remains available.",
                    })}
                  </span>
                </div>
              ) : null}

              <SharedDetailBlock title={t("runtime.room.workspace")} monospace>
                {bundle.environment?.workspace_path || "—"}
              </SharedDetailBlock>

              <SharedDetailBlock title={t("runtime.room.runtimeDir")} monospace>
                {bundle.environment?.runtime_dir || "—"}
              </SharedDetailBlock>

              <SharedDetailBlock title={t("runtime.room.gitStatus")} monospace>
                <RuntimeGitSyntax
                  text={bundle.workspaceStatus.text}
                  fallback={t("runtime.room.noStatus")}
                />
              </SharedDetailBlock>

              <SharedDetailBlock title={t("runtime.room.diff")} monospace>
                <RuntimeGitSyntax
                  text={bundle.workspaceDiff.text}
                  fallback={t("runtime.room.noDiff")}
                  lineNumbers
                />
              </SharedDetailBlock>
            </div>
          ) : null}

          {detailTab === "runGraph" ? (
            <div className="space-y-4">
              <RunGraphSummaryPanel
                graph={runGraph}
                replay={runReplay}
                runtimeHref={`/runtime/${agentId}/tasks/${taskId}`}
              />
              <RunGraphViewer graph={runGraph} />
              <ChildRunsPanel
                agentId={agentId}
                childRuns={childRuns}
                onAction={(childRun, action) => void runChildAction(childRun, action)}
                busyAction={busyAction}
              />
              <ContextGovernancePanel context={contextGovernance} />
              <RunReplayPanel replay={runReplay} />
            </div>
          ) : null}

          {detailTab === "logs" ? (
            <div className="space-y-5">
              {bundle.warnings.length > 0 ? (
                <SharedDetailBlock title={t("runtime.room.warnings")}>
                  <div className="space-y-2">
                    {bundle.warnings.slice().reverse().map((warning) => (
                      <div
                        key={warning.id}
                        className="rounded-[var(--radius-panel-sm)] bg-[var(--panel)] p-2.5"
                      >
                        <p className="m-0 text-[0.8125rem] text-[var(--text-primary)]">
                          {warning.message || warning.warning_type}
                        </p>
                        <p className="m-0 mt-1 text-[0.6875rem] text-[var(--text-quaternary)]">
                          {warning.created_at
                            ? formatDateTime(warning.created_at)
                            : t("runtime.room.eventRecordedNow")}
                        </p>
                      </div>
                    ))}
                  </div>
                </SharedDetailBlock>
              ) : null}

              <SharedDetailBlock title={t("runtime.room.events")}>
                {bundle.events.length === 0 ? (
                  <div className="flex flex-col items-center gap-2 py-6 text-center text-[0.8125rem] text-[var(--text-tertiary)]">
                    <Activity className="h-4 w-4 text-[var(--text-quaternary)]" />
                    <p className="m-0">{t("runtime.room.noEvents")}</p>
                  </div>
                ) : (
                  <div className="space-y-1">
                    {bundle.events
                      .slice()
                      .reverse()
                      .map((event) => (
                        <RuntimeEventLogRow key={event.seq} event={event} />
                      ))}
                  </div>
                )}
              </SharedDetailBlock>
            </div>
          ) : null}

          {detailTab === "diagnostics" ? (
            <div className="space-y-5">
              <SandboxDoctorPanel result={sandboxDoctor} />

              <SharedDetailGrid columns={3}>
                <SharedDetailDatum
                  label={t("runtime.room.stats.cpu")}
                  value={formatPercent(latestResource?.cpu_percent)}
                />
                <SharedDetailDatum
                  label={tl("RSS")}
                  value={formatBytes(
                    latestResource?.rss_kb != null
                      ? latestResource.rss_kb * 1024
                      : null,
                  )}
                />
                <SharedDetailDatum
                  label={t("runtime.room.processes")}
                  value={String(latestResource?.process_count ?? "—")}
                />
                <SharedDetailDatum
                  label={t("runtime.room.disk")}
                  value={formatBytes(latestResource?.workspace_disk_bytes)}
                />
                <SharedDetailDatum
                  label={t("runtime.room.loops")}
                  value={String(bundle.loopCycles.length)}
                />
                <SharedDetailDatum
                  label={t("runtime.room.guardrails")}
                  value={String(bundle.guardrails.length)}
                />
              </SharedDetailGrid>

              <SharedDetailBlock title={t("runtime.room.services")}>
                {bundle.services.length === 0 ? (
                  <div className="flex flex-col items-center gap-2 py-6 text-center text-[0.8125rem] text-[var(--text-tertiary)]">
                    <Globe className="h-4 w-4 text-[var(--text-quaternary)]" />
                    <p className="m-0">{t("runtime.room.noActiveServices")}</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {bundle.services.map((service) => (
                      <div
                        key={service.id}
                        className="flex items-start justify-between gap-3"
                      >
                        <div className="min-w-0">
                          <p className="m-0 text-[0.8125rem] text-[var(--text-primary)]">
                            {service.label || service.service_kind}
                          </p>
                          <p className="m-0 mt-0.5 font-mono text-[0.6875rem] text-[var(--text-tertiary)]">
                            {service.url ||
                              `${service.protocol}://${service.host}:${service.port}`}
                          </p>
                        </div>
                        <span className="inline-flex items-center gap-1.5 text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-secondary)]">
                          <StatusDot tone={toneToDot(getRuntimeTone(service.status))} />
                          {getRuntimeLabel(service.status)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </SharedDetailBlock>

              <SharedDetailBlock title={t("runtime.room.checkpointsAndArtifacts")}>
                <div className="space-y-2">
                  {latestCheckpoint ? (
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="m-0 text-[0.8125rem] text-[var(--text-primary)]">
                          {t("runtime.room.latestCheckpoint")}
                        </p>
                        <p className="m-0 mt-0.5 font-mono text-[0.6875rem] text-[var(--text-tertiary)]">
                          {latestCheckpoint.checkpoint_dir}
                        </p>
                      </div>
                      <span className="text-[0.6875rem] text-[var(--text-quaternary)]">
                        {formatRelativeTime(latestCheckpoint.created_at)}
                      </span>
                    </div>
                  ) : null}

                  {bundle.artifacts.slice(-5).map((artifact) => (
                    <div
                      key={artifact.id}
                      className="flex items-start justify-between gap-3"
                    >
                      <div className="min-w-0">
                        <p className="m-0 text-[0.8125rem] text-[var(--text-primary)]">
                          {artifact.label || artifact.artifact_kind}
                        </p>
                        <p className="m-0 mt-0.5 font-mono text-[0.6875rem] text-[var(--text-tertiary)]">
                          {artifact.path}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </SharedDetailBlock>

              <SharedDetailBlock title={t("runtime.room.sessions")}>
                <SharedDetailGrid columns={3}>
                  <SharedDetailDatum
                    label={t("runtime.room.attach")}
                    value={String(bundle.sessions.attach_sessions.length)}
                  />
                  <SharedDetailDatum
                    label={t("runtime.room.tabs.browser")}
                    value={String(bundle.sessions.browser_sessions.length)}
                  />
                  <SharedDetailDatum
                    label={t("runtime.room.terminals")}
                    value={String(bundle.sessions.terminals.length)}
                  />
                </SharedDetailGrid>
              </SharedDetailBlock>

              <SharedDetailBlock title={t("runtime.room.recentGuardrails")}>
                {bundle.guardrails.length === 0 ? (
                  <div className="flex flex-col items-center gap-2 py-6 text-center text-[0.8125rem] text-[var(--text-tertiary)]">
                    <Waypoints className="h-4 w-4 text-[var(--text-quaternary)]" />
                    <p className="m-0">{t("runtime.room.noRecentGuardrails")}</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {bundle.guardrails.slice(-5).reverse().map((guardrail) => (
                      <div
                        key={guardrail.id}
                        className="flex items-start justify-between gap-3"
                      >
                        <div className="min-w-0">
                          <p className="m-0 text-[0.8125rem] text-[var(--text-primary)]">
                            {guardrail.guardrail_type}
                          </p>
                          <p className="m-0 mt-0.5 text-[0.6875rem] text-[var(--text-quaternary)]">
                            {formatRelativeTime(guardrail.created_at)}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </SharedDetailBlock>
            </div>
          ) : null}
        </div>
      </Drawer>
    </div>
  );
}

function ActionButton({
  onClick,
  busy,
  icon: Icon,
  label,
  tone = "neutral",
}: {
  onClick: () => void;
  busy: boolean;
  icon: LucideIcon;
  label: string;
  tone?: "neutral" | "danger" | "primary";
}) {
  const isPrimary = tone === "primary";
  const isDanger = tone === "danger";

  return (
    <Button
      type="button"
      onClick={onClick}
      disabled={busy}
      variant="ghost"
      size="sm"
      className={cn(
        "h-8 rounded-[var(--radius-chip)] border-transparent px-2.5 text-[0.8125rem] font-medium",
        "transition-[background-color,color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        isPrimary &&
          "bg-[var(--panel-strong)] text-[var(--text-primary)] hover:bg-[var(--surface-hover)]",
        isDanger &&
          "text-[var(--tone-danger-text)] hover:bg-[var(--tone-danger-bg)]",
        !isPrimary &&
          !isDanger &&
          "text-[var(--text-secondary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]",
      )}
      aria-busy={busy || undefined}
    >
      {busy ? (
        <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
      ) : (
        <Icon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
      )}
      {label}
    </Button>
  );
}

function ProgressBar({ percent }: { percent: number | null }) {
  const isIndeterminate = percent == null;
  return (
    <div
      role="progressbar"
      aria-valuenow={isIndeterminate ? undefined : percent ?? 0}
      aria-valuemin={0}
      aria-valuemax={100}
      className="relative h-1 w-full overflow-hidden bg-[var(--panel-strong)]"
    >
      <div
        className={cn(
          "h-full bg-[var(--tone-success-dot)] transition-[width] duration-300 ease-out",
          isIndeterminate && "w-1/3 animate-[roster-shimmer_1.8s_cubic-bezier(0.4,0,0.2,1)_infinite]",
        )}
        style={isIndeterminate ? undefined : { width: `${Math.min(100, Math.max(0, percent))}%` }}
      />
    </div>
  );
}

function RuntimeEventFeedRow({ event }: { event: RuntimeEvent }) {
  const { t } = useAppI18n();
  return (
    <EventRow
      level={runtimeEventLevel(event.severity)}
      timestamp={event.ts ?? undefined}
      message={getRuntimeLabel(event.type || t("runtime.room.eventFallback"))}
      source={getEventPreview(event)}
      payload={event.payload && Object.keys(event.payload).length > 0 ? event.payload : undefined}
      className="py-2.5"
    />
  );
}

function runtimeEventLevel(severity: string | null | undefined): EventLevel {
  const tone = getRuntimeSeverityTone(severity);
  if (tone === "danger") return "error";
  if (tone === "warning") return "warn";
  if (tone === "success") return "success";
  if (tone === "neutral") return "debug";
  return "info";
}

function RuntimeEventLogRow({ event }: { event: RuntimeEvent }) {
  const { t } = useAppI18n();
  const toneDot = toneToDot(getRuntimeSeverityTone(event.severity));
  return (
    <article className="flex flex-col gap-1.5 border-b border-[color:var(--divider-hair)] py-2.5 last:border-b-0">
      <div className="flex flex-wrap items-center gap-2">
        <StatusDot tone={toneDot} />
        <span className="text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-tertiary)]">
          {getRuntimeLabel(event.severity || "info")}
        </span>
        <span className="font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
          seq {event.seq}
        </span>
        {event.phase ? (
          <span className="text-[0.6875rem] text-[var(--text-quaternary)]">
            · {getRuntimeLabel(event.phase)}
          </span>
        ) : null}
        <span className="ml-auto text-[0.6875rem] tabular-nums text-[var(--text-quaternary)]">
          {event.ts ? formatRelativeTime(event.ts) : t("runtime.room.eventRecordedNow")}
        </span>
      </div>
      <p className="m-0 text-[0.8125rem] font-medium text-[var(--text-primary)]">
        {getRuntimeLabel(event.type || t("runtime.room.eventFallback"))}
      </p>
      <p className="m-0 text-[0.75rem] leading-[1.5] text-[var(--text-secondary)]">
        {getEventPreview(event)}
      </p>
      {event.payload && Object.keys(event.payload).length > 0 ? (
        <SyntaxHighlight lang="json" className="mt-1 text-[0.6875rem]">
          {JSON.stringify(event.payload, null, 2)}
        </SyntaxHighlight>
      ) : null}
    </article>
  );
}

function getEventPreview(event: RuntimeEvent): ReactNode {
  const payload = event.payload ?? {};

  const directMessage = [
    payload.message,
    payload.summary,
    payload.reason,
    payload.command,
    payload.goal,
    payload.path,
  ].find((value): value is string => typeof value === "string" && value.trim().length > 0);

  if (directMessage) {
    return truncateText(directMessage, 180);
  }

  if (event.phase) {
    return translateRuntimeRoom("phasePreview", {
      value: getRuntimeLabel(event.phase).toLowerCase(),
    });
  }

  return translateRuntimeRoom("environmentUpdateRecorded");
}

function translateRuntimeRoom(key: string, options?: Record<string, unknown>) {
  return translate(`runtime.room.${key}`, options);
}
