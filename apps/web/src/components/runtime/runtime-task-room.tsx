"use client";

import Link from "next/link";
import type { ComponentType, ReactNode } from "react";
import { useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Globe,
  MoreHorizontal,
  Pause,
  Pin,
  Play,
  RefreshCcw,
  RotateCcw,
  Save,
  SquareSlash,
  Trash2,
  Waypoints,
} from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { RuntimeBrowserPanel } from "@/components/runtime/runtime-browser-panel";
import { RuntimeFilesPanel } from "@/components/runtime/runtime-files-panel";
import { RuntimeTerminalPanel } from "@/components/runtime/runtime-terminal-panel";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import { Drawer } from "@/components/ui/drawer";
import {
  DetailBlock as SharedDetailBlock,
  DetailDatum as SharedDetailDatum,
  DetailGrid as SharedDetailGrid,
} from "@/components/ui/detail-group";
import { InlineAlert } from "@/components/ui/inline-alert";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { SoftTabs } from "@/components/ui/soft-tabs";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import { useRuntimeTask } from "@/hooks/use-runtime-task";
import { translate } from "@/lib/i18n";
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
type DetailTab = "details" | "logs" | "diagnostics";

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

export function RuntimeTaskRoom({ agentId, taskId }: RuntimeTaskRoomProps) {
  const { t, tl } = useAppI18n();
  const { bundle, loading, error, connected, mutate, fetchResource, refresh } =
    useRuntimeTask(agentId, taskId);
  const [activeTab, setActiveTab] = useState<RoomTab>("terminal");
  const [detailTab, setDetailTab] = useState<DetailTab>("details");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [actionsOpen, setActionsOpen] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);

  const latestResource = bundle?.resources.at(-1) ?? null;
  const latestCheckpoint = bundle?.checkpoints.at(-1) ?? null;
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
    setActionFeedback(null);
    setActionsOpen(false);

    try {
      await mutate(action, { searchParams: options?.searchParams });
      setActionFeedback(t("runtime.room.completed", { label }));
    } catch (actionError) {
      setActionFeedback(
        actionError instanceof Error ? actionError.message : `${t("common.failed")} ${label}`,
      );
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
    <div className="runtime-shell space-y-6" data-testid="runtime-task-room">
      {/* Hero */}
      <header className="flex flex-col gap-5">
        <div className="min-w-0 space-y-3">
          <div className="flex items-center gap-2.5">
            <Link
              href={`/runtime?agent=${agentId}`}
              className="inline-flex h-7 w-7 items-center justify-center rounded-[var(--radius-panel-sm)] text-[var(--text-tertiary)] transition-[background-color,color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]"
              aria-label={t("common.back")}
            >
              <ArrowLeft className="h-3.5 w-3.5" />
            </Link>
            <span className="font-mono text-[0.8125rem] font-medium text-[var(--text-primary)]">
              Task #{taskId}
            </span>
            <span className="text-[var(--text-quaternary)]">·</span>
            <StatusDot tone={phaseTone} pulse={isLivePhase} />
            <span className="text-[0.8125rem] text-[var(--text-secondary)]">
              {currentPhase}
            </span>
            {connected ? (
              <>
                <span className="text-[var(--text-quaternary)]">·</span>
                <StatusDot tone="success" pulse />
                <span className="text-[0.75rem] text-[var(--text-tertiary)]">
                  {t("runtime.overview.live")}
                </span>
              </>
            ) : null}
          </div>
          <h1 className="m-0 text-[1.75rem] font-medium leading-[1.2] tracking-[var(--tracking-tight)] text-[var(--text-primary)] [text-wrap:balance]">
            {heroTitle}
          </h1>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <ActionButton
            onClick={() =>
              void runAction(
                isPaused ? "resume" : "pause",
                isPaused ? t("runtime.room.resume") : t("runtime.room.pause"),
              )
            }
            busy={busyAction === "pause" || busyAction === "resume"}
            icon={isPaused ? Play : Pause}
            label={isPaused ? t("runtime.room.resume") : t("runtime.room.pause")}
          />
          <ActionButton
            onClick={() => void runAction("save", t("runtime.room.saveSnapshot"))}
            busy={busyAction === "save"}
            icon={Save}
            label={t("common.save")}
          />
          <ActionButton
            onClick={() =>
              void runAction("cancel", t("runtime.room.cancelExecution"), {
                confirmMessage: t("runtime.room.cancelExecutionConfirm"),
              })
            }
            busy={busyAction === "cancel"}
            icon={SquareSlash}
            label={t("common.cancel")}
            tone="danger"
          />

          <span className="mx-1 h-5 w-px bg-[var(--divider-hair)]" aria-hidden="true" />

          <Popover open={actionsOpen} onOpenChange={setActionsOpen}>
            <PopoverTrigger asChild>
              <button
                type="button"
                className="inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 text-[0.8125rem] text-[var(--text-secondary)] transition-[background-color,border-color,color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-[var(--border-strong)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)] data-[state=open]:border-[var(--border-strong)] data-[state=open]:bg-[var(--hover-tint)]"
                aria-label={t("runtime.room.more")}
              >
                <MoreHorizontal className="h-3.5 w-3.5" />
                <span>{t("runtime.room.more")}</span>
              </button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-52">
              <MenuAction
                icon={RefreshCcw}
                label={t("runtime.room.refresh")}
                onClick={() => {
                  void refresh();
                  setActionsOpen(false);
                }}
              />
              <MenuAction
                icon={RotateCcw}
                label={t("runtime.room.retry")}
                busy={busyAction === "retry"}
                onClick={() => void runAction("retry", t("runtime.room.retry"))}
              />
              <MenuAction
                icon={RefreshCcw}
                label={t("runtime.room.recover")}
                busy={busyAction === "recover"}
                onClick={() => void runAction("recover", t("runtime.room.recover"))}
              />
              <MenuAction
                icon={Pin}
                label={isPinned ? t("runtime.room.unpin") : t("runtime.room.pin")}
                busy={busyAction === "pin" || busyAction === "unpin"}
                onClick={() =>
                  void runAction(
                    isPinned ? "unpin" : "pin",
                    isPinned ? t("runtime.room.unpin") : t("runtime.room.pin"),
                  )
                }
              />
              <MenuAction
                icon={Trash2}
                label={t("runtime.room.requestCleanup")}
                busy={busyAction === "cleanup"}
                onClick={() =>
                  void runAction("cleanup", t("runtime.room.requestCleanup"), {
                    confirmMessage: t("runtime.room.requestCleanupConfirm"),
                  })
                }
                tone="warning"
              />
              <MenuAction
                icon={Trash2}
                label={t("runtime.room.forceCleanup")}
                busy={busyAction === "cleanup/force"}
                onClick={() =>
                  void runAction("cleanup/force", t("runtime.room.forceCleanup"), {
                    confirmMessage: t("runtime.room.forceCleanupConfirm"),
                  })
                }
                tone="danger"
              />
            </PopoverContent>
          </Popover>

          <span className="mx-1 h-5 w-px bg-[var(--divider-hair)]" aria-hidden="true" />

          <button
            type="button"
            className="inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-transparent px-3 text-[0.8125rem] text-[var(--text-secondary)] transition-[background-color,border-color,color] duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)] hover:border-[var(--border-strong)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]"
            onClick={() => {
              setDetailTab("details");
              setDetailsOpen(true);
            }}
          >
            {t("runtime.room.details")}
          </button>
          <Link
            href="/executions"
            className="inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-panel-sm)] px-3 text-[0.8125rem] text-[var(--text-tertiary)] transition-colors hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]"
          >
            {t("runtime.room.history")}
          </Link>
        </div>
      </header>

      {actionFeedback ? (
        <InlineAlert tone="info" icon={Activity}>
          {actionFeedback}
        </InlineAlert>
      ) : null}

      {/* Stage */}
      <section
        className="flex flex-col gap-4 rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel)] p-4"
        aria-label={t("runtime.room.trackingLabel")}
      >
        <div className="flex items-center justify-between gap-3">
          <SoftTabs
            items={roomTabs}
            value={activeTab}
            onChange={(id) => setActiveTab(id as RoomTab)}
            ariaLabel={t("runtime.room.switchSurface")}
          />
          {connected ? (
            <span className="inline-flex items-center gap-1.5 text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
              <StatusDot tone="success" pulse />
              {t("runtime.overview.live")}
            </span>
          ) : null}
        </div>

        <div className="min-h-[420px]">
          {activeTab === "terminal" ? (
            <RuntimeTerminalPanel
              taskId={taskId}
              terminals={bundle.terminals}
              mutate={mutate}
              fetchResource={fetchResource}
            />
          ) : null}

          {activeTab === "browser" ? (
            <RuntimeBrowserPanel
              agentId={agentId}
              taskId={taskId}
              browser={bundle.browser}
              mutate={mutate}
              fetchResource={fetchResource}
            />
          ) : null}

          {activeTab === "files" ? (
            <RuntimeFilesPanel
              taskId={taskId}
              workspaceTree={bundle.workspaceTree}
              mutate={mutate}
              fetchResource={fetchResource}
            />
          ) : null}

          {activeTab === "activity" ? (
            <div className="space-y-3">
              {bundle.warnings.length > 0 ? (
                <div className="space-y-2">
                  {bundle.warnings.slice(-3).reverse().map((warning) => (
                    <InlineAlert key={warning.id} tone="warning">
                      <p className="m-0 font-medium text-[var(--text-primary)]">
                        {warning.message || warning.warning_type}
                      </p>
                      <p className="m-0 mt-0.5 text-[0.6875rem] text-[var(--text-quaternary)]">
                        {warning.created_at
                          ? formatDateTime(warning.created_at)
                          : t("runtime.room.eventRecordedNow")}
                      </p>
                    </InlineAlert>
                  ))}
                </div>
              ) : null}

              {bundle.events.length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-10 text-center text-[0.8125rem] text-[var(--text-tertiary)]">
                  <Activity className="h-4 w-4 text-[var(--text-quaternary)]" />
                  <p className="m-0">{t("runtime.room.noMovementYet")}</p>
                </div>
              ) : (
                <div className="rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] p-3">
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
        </div>

        <ProgressBar
          percent={
            typeof bundle.environment?.progress_percent === "number"
              ? bundle.environment.progress_percent
              : null
          }
        />

        <footer className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-[color:var(--divider-hair)] pt-3">
          {essentialStats.map((item, index) => (
            <span
              key={item.label}
              className="inline-flex items-center gap-1.5 font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]"
            >
              {index > 0 ? (
                <span className="text-[var(--text-quaternary)]" aria-hidden="true">
                  ·
                </span>
              ) : null}
              <span>{item.label}</span>
              <span className="text-[var(--text-secondary)]">{item.value}</span>
            </span>
          ))}
        </footer>
      </section>

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

              <SharedDetailBlock title={t("runtime.room.workspace")} monospace>
                {bundle.environment?.workspace_path || "—"}
              </SharedDetailBlock>

              <SharedDetailBlock title={t("runtime.room.runtimeDir")} monospace>
                {bundle.environment?.runtime_dir || "—"}
              </SharedDetailBlock>

              <SharedDetailBlock title={t("runtime.room.gitStatus")} monospace>
                <SyntaxHighlight lang="diff">
                  {bundle.workspaceStatus.text || t("runtime.room.noStatus")}
                </SyntaxHighlight>
              </SharedDetailBlock>

              <SharedDetailBlock title={t("runtime.room.diff")} monospace>
                <SyntaxHighlight lang="diff">
                  {bundle.workspaceDiff.text || t("runtime.room.noDiff")}
                </SyntaxHighlight>
              </SharedDetailBlock>
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
  icon: ComponentType<{ className?: string }>;
  label: string;
  tone?: "neutral" | "danger";
}) {
  return (
    <AsyncActionButton
      type="button"
      onClick={onClick}
      loading={busy}
      loadingLabel={label}
      variant={tone === "danger" ? "danger" : "secondary"}
      size="sm"
      icon={Icon as never}
    >
      {label}
    </AsyncActionButton>
  );
}

function MenuAction({
  icon: Icon,
  label,
  onClick,
  busy = false,
  tone = "neutral",
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  onClick: () => void;
  busy?: boolean;
  tone?: "neutral" | "warning" | "danger";
}) {
  const toneClass =
    tone === "danger"
      ? "text-[var(--tone-danger-dot)] hover:bg-[var(--tone-danger-bg)]"
      : tone === "warning"
        ? "text-[var(--tone-warning-dot)] hover:bg-[var(--tone-warning-bg)]"
        : "text-[var(--text-secondary)] hover:bg-[var(--hover-tint)] hover:text-[var(--text-primary)]";

  return (
    <AsyncActionButton
      type="button"
      className={cn(
        "w-full justify-start gap-2 rounded-[var(--radius-panel-sm)] border-0 bg-transparent px-2 py-1.5 text-left text-[0.8125rem] font-normal",
        toneClass,
      )}
      onClick={onClick}
      loading={busy}
      loadingLabel={label}
      variant="quiet"
      size="sm"
      icon={Icon as never}
      role="menuitem"
    >
      {label}
    </AsyncActionButton>
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
      className="relative h-[2px] w-full overflow-hidden rounded-full bg-[var(--panel-soft)]"
    >
      <div
        className={cn(
          "h-full bg-[var(--accent)] transition-[width] duration-300 ease-out",
          isIndeterminate && "w-1/3 animate-[roster-shimmer_1.8s_cubic-bezier(0.4,0,0.2,1)_infinite]",
        )}
        style={isIndeterminate ? undefined : { width: `${Math.min(100, Math.max(0, percent))}%` }}
      />
    </div>
  );
}

function RuntimeEventFeedRow({ event }: { event: RuntimeEvent }) {
  const { t } = useAppI18n();
  const toneDot = toneToDot(getRuntimeSeverityTone(event.severity));
  return (
    <article className="grid w-full grid-cols-[auto_1fr_auto] items-start gap-3 border-b border-[color:var(--divider-hair)] py-2 last:border-b-0">
      <StatusDot tone={toneDot} className="mt-[6px]" />
      <div className="min-w-0">
        <p className="m-0 truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
          {getRuntimeLabel(event.type || t("runtime.room.eventFallback"))}
        </p>
        <p className="m-0 mt-0.5 text-[0.75rem] leading-[1.5] text-[var(--text-secondary)]">
          {getEventPreview(event)}
        </p>
      </div>
      <span className="whitespace-nowrap text-[0.6875rem] tabular-nums text-[var(--text-quaternary)]">
        {event.ts ? formatRelativeTime(event.ts) : t("runtime.room.eventRecordedNow")}
      </span>
    </article>
  );
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
