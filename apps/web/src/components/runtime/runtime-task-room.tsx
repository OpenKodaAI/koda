"use client";

import Link from "next/link";
import type { ComponentType, ReactNode } from "react";
import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
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
  X,
} from "lucide-react";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { RuntimeBrowserPanel } from "@/components/runtime/runtime-browser-panel";
import { RuntimeFilesPanel } from "@/components/runtime/runtime-files-panel";
import { RuntimeTerminalPanel } from "@/components/runtime/runtime-terminal-panel";
import { AsyncActionButton } from "@/components/ui/async-feedback";
import { useRuntimeTask } from "@/hooks/use-runtime-task";
import { translate } from "@/lib/i18n";
import { getSemanticStyle, getSemanticTextStyle } from "@/lib/theme-semantic";
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
  botId: string;
  taskId: number;
}

export function RuntimeTaskRoom({ botId, taskId }: RuntimeTaskRoomProps) {
  const { t, tl } = useAppI18n();
  const { bundle, loading, error, connected, mutate, fetchResource, refresh } =
    useRuntimeTask(botId, taskId);
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

  const tabs = [
    { id: "terminal", label: t("runtime.room.tabs.terminal") },
    { id: "browser", label: t("runtime.room.tabs.browser") },
    { id: "files", label: t("runtime.room.tabs.files") },
    { id: "activity", label: t("runtime.room.tabs.activity") },
  ] satisfies Array<{ id: RoomTab; label: string }>;

  const heroTitle = truncateText(
      bundle?.task?.query_text ||
      bundle?.events.at(-1)?.type ||
      t("runtime.room.executionLive"),
    116
  );
  const currentPhase = getRuntimeLabel(
    bundle?.task?.current_phase || bundle?.environment?.current_phase || bundle?.task?.status
  );
  const currentStatus = String(bundle?.task?.status || bundle?.environment?.status || "queued");
  const heartbeatAt =
    bundle?.environment?.last_heartbeat_at ||
    bundle?.task?.last_heartbeat_at ||
    bundle?.environment?.updated_at ||
    bundle?.task?.started_at ||
    null;

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
          latestResource?.rss_kb != null ? latestResource.rss_kb * 1024 : null
        ),
      },
      {
        label: t("runtime.room.stats.now"),
        value: heartbeatAt ? formatRelativeTime(heartbeatAt) : t("runtime.room.stats.noHeartbeat"),
      },
    ],
    [bundle?.environment?.status, bundle?.task?.status, currentPhase, latestResource, heartbeatAt, t]
  );

  const detailTabs = [
    { id: "details", label: t("runtime.room.detailTabs.details") },
    { id: "logs", label: "Logs" },
    { id: "diagnostics", label: t("runtime.room.detailTabs.diagnostics") },
  ] satisfies Array<{ id: DetailTab; label: string }>;

  const runAction = async (
    action: string,
    label: string,
    options?: {
      confirmMessage?: string;
      searchParams?: URLSearchParams;
    }
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
        actionError instanceof Error ? actionError.message : `${t("common.failed")} ${label}`
      );
    } finally {
      setBusyAction(null);
    }
  };

  if (loading && !bundle) {
    return (
      <div className="runtime-shell runtime-shell--wide space-y-5">
        <div className="runtime-hero">
          <div className="space-y-3">
            <div className="h-5 w-24 rounded-lg bg-[rgba(255,255,255,0.06)]" />
            <div className="h-14 w-72 rounded-lg bg-[rgba(255,255,255,0.05)]" />
          </div>
          <div className="h-10 w-52 rounded-lg bg-[rgba(255,255,255,0.05)]" />
        </div>
        <div className="runtime-stage min-h-[620px] animate-pulse" />
      </div>
    );
  }

  if (!bundle || error) {
    return (
      <div className="runtime-shell runtime-shell--wide">
        <div className="runtime-empty runtime-empty--danger min-h-[320px]">
          <AlertTriangle className="h-6 w-6" />
          <p className="text-base font-semibold text-[var(--text-primary)]">
            {t("runtime.room.openErrorTitle")}
          </p>
          <p className="max-w-xl text-center text-sm leading-6 text-[var(--text-tertiary)]">
            {error || t("runtime.room.openErrorDescription")}
          </p>
          <Link href="/runtime" className="runtime-ghost-button">
            {t("common.back")}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="runtime-shell runtime-shell--wide runtime-task-room" data-testid="runtime-task-room">
      <header className="runtime-hero">
        <div className="runtime-hero__main">
          <div className="runtime-hero__title-row">
            <Link href={`/runtime?bot=${botId}`} className="runtime-back-link">
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <span className="runtime-inline-id runtime-inline-id--lg">Task #{taskId}</span>
            <span
              className="runtime-inline-tone"
              style={getSemanticStyle(
                getRuntimeTone(bundle.environment?.current_phase || bundle.task?.current_phase)
              )}
            >
              {currentPhase}
            </span>
            <span className={cn("runtime-inline-dot", connected && "runtime-inline-dot--live")} />
          </div>
          <h1 className="runtime-hero__title">{heroTitle}</h1>
        </div>
        <div className="runtime-hero__actions">
          <ActionButton
            onClick={() =>
              void runAction(
                isPaused ? "resume" : "pause",
                isPaused ? t("runtime.room.resume") : t("runtime.room.pause")
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

          <div className="relative">
            <button
              type="button"
              className={cn("runtime-ghost-button", actionsOpen && "is-active")}
              onClick={() => setActionsOpen((current) => !current)}
              aria-expanded={actionsOpen}
              aria-haspopup="menu"
            >
              <MoreHorizontal className="h-4 w-4" />
              {t("runtime.room.more")}
            </button>

            <AnimatePresence>
              {actionsOpen ? (
                <motion.div
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 4 }}
                  className="runtime-actions-menu"
                  role="menu"
                >
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
                        isPinned ? t("runtime.room.unpin") : t("runtime.room.pin")
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
                </motion.div>
              ) : null}
            </AnimatePresence>
          </div>

          <button
            type="button"
            className="runtime-ghost-button"
            onClick={() => {
              setDetailTab("details");
              setDetailsOpen(true);
            }}
          >
            {t("runtime.room.details")}
          </button>
          <Link href="/executions" className="runtime-ghost-button">
            {t("runtime.room.history")}
          </Link>
        </div>
      </header>

      {actionFeedback ? (
        <div className="runtime-inline-alert">
          <Activity className="h-4 w-4 shrink-0" />
          <span>{actionFeedback}</span>
        </div>
      ) : null}

      <section className="runtime-stage" aria-label={t("runtime.room.trackingLabel")}>
        <div className="runtime-stage__header">
          <div className="runtime-tabs" role="tablist" aria-label={t("runtime.room.switchSurface")}>
            {tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={activeTab === tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn("runtime-tab", activeTab === tab.id && "is-active")}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <span className={cn("runtime-inline-dot", connected && "runtime-inline-dot--live")} />
        </div>

        <div className="runtime-stage__body">
          <AnimatePresence mode="wait">
            {activeTab === "terminal" ? (
              <motion.div
                key="terminal"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
              >
                <RuntimeTerminalPanel
                  taskId={taskId}
                  terminals={bundle.terminals}
                  mutate={mutate}
                  fetchResource={fetchResource}
                />
              </motion.div>
            ) : null}

            {activeTab === "browser" ? (
              <motion.div
                key="browser"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
              >
                <RuntimeBrowserPanel
                  botId={botId}
                  taskId={taskId}
                  browser={bundle.browser}
                  mutate={mutate}
                  fetchResource={fetchResource}
                />
              </motion.div>
            ) : null}

            {activeTab === "files" ? (
              <motion.div
                key="files"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
              >
                <RuntimeFilesPanel
                  taskId={taskId}
                  workspaceTree={bundle.workspaceTree}
                  mutate={mutate}
                  fetchResource={fetchResource}
                />
              </motion.div>
            ) : null}

            {activeTab === "activity" ? (
              <motion.div
                key="activity"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                className="space-y-4"
              >
                {bundle.warnings.length > 0 ? (
                  <div className="space-y-2">
                    {bundle.warnings.slice(-3).reverse().map((warning) => (
                      <div key={warning.id} className="runtime-inline-alert">
                        <AlertTriangle className="h-4 w-4 shrink-0" />
                        <div className="min-w-0">
                          <p className="text-sm text-[var(--text-primary)]">
                            {warning.message || warning.warning_type}
                          </p>
                          <p className="text-xs text-[var(--text-quaternary)]">
                                  {warning.created_at
                              ? formatDateTime(warning.created_at)
                              : t("runtime.room.eventRecordedNow")}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}

                {bundle.events.length === 0 ? (
                  <div className="runtime-empty">
                    <Activity className="h-5 w-5" />
                    <p>{t("runtime.room.noMovementYet")}</p>
                  </div>
                ) : (
                  <div className="runtime-activity-feed">
                    {bundle.events
                      .slice()
                      .reverse()
                      .slice(0, 14)
                      .map((event) => (
                        <RuntimeEventFeedRow key={event.seq} event={event} />
                      ))}
                  </div>
                )}
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>

        <div className="progress-bar">
          <div className={cn(
            "progress-bar__fill",
            !bundle.environment?.progress_percent && "progress-bar__fill--indeterminate"
          )}
            style={bundle.environment?.progress_percent ? { width: `${bundle.environment.progress_percent}%` } : undefined}
          />
        </div>

        <div className="runtime-stage__footer">
          <div className="runtime-stat-strip">
            {essentialStats.map((item) => (
              <div key={item.label} className="runtime-stat-strip__item">
                <span className="runtime-stat-strip__label">{item.label}</span>
                <span className="runtime-stat-strip__value">{item.value}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <AnimatePresence>
        {detailsOpen ? (
          <>
            <motion.button
              type="button"
              aria-label={t("runtime.room.closeDetails")}
              className="runtime-detail-sheet__scrim"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setDetailsOpen(false)}
            />
            <motion.aside
              initial={{ opacity: 0, x: 14 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 10 }}
              className="runtime-detail-sheet"
            >
              <div className="runtime-detail-sheet__header">
                <p className="runtime-panel__title">{t("runtime.room.details")}</p>
                <button
                  type="button"
                  className="runtime-ghost-button runtime-ghost-button--icon"
                  onClick={() => setDetailsOpen(false)}
                  aria-label={t("runtime.room.closeDetailsPanel")}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="runtime-detail-tabs" role="tablist" aria-label={t("runtime.room.detailTabsAria")}>
                {detailTabs.map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={detailTab === tab.id}
                    onClick={() => setDetailTab(tab.id)}
                    className={cn("runtime-detail-tab", detailTab === tab.id && "is-active")}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              <div className="runtime-detail-sheet__body">
                {detailTab === "details" ? (
                  <div className="space-y-5">
                    <DetailGrid>
                      <DetailDatum label={t("common.bot")}>{botId}</DetailDatum>
                      <DetailDatum label={t("common.task")}>#{taskId}</DetailDatum>
                      <DetailDatum label={t("common.status")}>
                        <span
                          className="runtime-inline-tone"
                          style={getSemanticStyle(getRuntimeTone(currentStatus))}
                        >
                          {getRuntimeLabel(currentStatus)}
                        </span>
                      </DetailDatum>
                      <DetailDatum label={t("common.phase")}>{currentPhase}</DetailDatum>
                      <DetailDatum label={t("runtime.room.branch")}>
                        <span className="font-mono text-[12px]">
                          {bundle.environment?.branch_name || "—"}
                        </span>
                      </DetailDatum>
                      <DetailDatum label={t("runtime.room.retention")}>
                        {bundle.environment?.retention_expires_at
                          ? formatDateTime(bundle.environment.retention_expires_at)
                          : "—"}
                      </DetailDatum>
                    </DetailGrid>

                    <DetailBlock title={t("runtime.room.workspace")}>
                      <p className="runtime-code-inline">
                        {bundle.environment?.workspace_path || "—"}
                      </p>
                    </DetailBlock>

                    <DetailBlock title={t("runtime.room.runtimeDir")}>
                      <p className="runtime-code-inline">
                        {bundle.environment?.runtime_dir || "—"}
                      </p>
                    </DetailBlock>

                    <DetailBlock title={t("runtime.room.gitStatus")}>
                      <SyntaxHighlight lang="diff" className="runtime-code-block">
                        {bundle.workspaceStatus.text || t("runtime.room.noStatus")}
                      </SyntaxHighlight>
                    </DetailBlock>

                    <DetailBlock title={t("runtime.room.diff")}>
                      <SyntaxHighlight lang="diff" className="runtime-code-block">
                        {bundle.workspaceDiff.text || t("runtime.room.noDiff")}
                      </SyntaxHighlight>
                    </DetailBlock>
                  </div>
                ) : null}

                {detailTab === "logs" ? (
                  <div className="space-y-5">
                    {bundle.warnings.length > 0 ? (
                      <DetailBlock title={t("runtime.room.warnings")}>
                        <div className="space-y-2">
                          {bundle.warnings.slice().reverse().map((warning) => (
                            <div key={warning.id} className="runtime-log-row">
                              <div>
                                <p className="text-sm text-[var(--text-primary)]">
                                  {warning.message || warning.warning_type}
                                </p>
                                <p className="text-xs text-[var(--text-quaternary)]">
                                  {warning.created_at
                                    ? formatDateTime(warning.created_at)
                                    : t("runtime.room.eventRecordedNow")}
                                </p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </DetailBlock>
                    ) : null}

                    <DetailBlock title={t("runtime.room.events")}>
                      <div className="space-y-2">
                        {bundle.events.length === 0 ? (
                          <div className="runtime-empty">
                            <Activity className="h-5 w-5" />
                            <p>{t("runtime.room.noEvents")}</p>
                          </div>
                        ) : (
                          bundle.events
                            .slice()
                            .reverse()
                            .map((event) => <RuntimeEventLogRow key={event.seq} event={event} />)
                        )}
                      </div>
                    </DetailBlock>
                  </div>
                ) : null}

                {detailTab === "diagnostics" ? (
                  <div className="space-y-5">
                    <DetailGrid>
                      <DetailDatum label={t("runtime.room.stats.cpu")}>
                        {formatPercent(latestResource?.cpu_percent)}
                      </DetailDatum>
                      <DetailDatum label={tl("RSS")}>
                        {formatBytes(
                          latestResource?.rss_kb != null
                            ? latestResource.rss_kb * 1024
                            : null
                        )}
                      </DetailDatum>
                      <DetailDatum label={t("runtime.room.processes")}>
                        {String(latestResource?.process_count ?? "—")}
                      </DetailDatum>
                      <DetailDatum label={t("runtime.room.disk")}>
                        {formatBytes(latestResource?.workspace_disk_bytes)}
                      </DetailDatum>
                      <DetailDatum label={t("runtime.room.loops")}>
                        {String(bundle.loopCycles.length)}
                      </DetailDatum>
                      <DetailDatum label={t("runtime.room.guardrails")}>
                        {String(bundle.guardrails.length)}
                      </DetailDatum>
                    </DetailGrid>

                    <DetailBlock title={t("runtime.room.services")}>
                      {bundle.services.length === 0 ? (
                        <div className="runtime-empty">
                          <Globe className="h-5 w-5" />
                          <p>{t("runtime.room.noActiveServices")}</p>
                        </div>
                      ) : (
                        <div className="space-y-2">
                          {bundle.services.map((service) => (
                            <div key={service.id} className="runtime-log-row">
                              <div>
                                <p className="text-sm text-[var(--text-primary)]">
                                  {service.label || service.service_kind}
                                </p>
                                <p className="runtime-code-inline">
                                  {service.url ||
                                    `${service.protocol}://${service.host}:${service.port}`}
                                </p>
                              </div>
                              <span
                                className="text-xs font-semibold"
                                style={getSemanticTextStyle(getRuntimeTone(service.status))}
                              >
                                {getRuntimeLabel(service.status)}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </DetailBlock>

                    <DetailBlock title={t("runtime.room.checkpointsAndArtifacts")}>
                      <div className="space-y-2">
                        {latestCheckpoint ? (
                          <div className="runtime-log-row">
                            <div>
                              <p className="text-sm text-[var(--text-primary)]">
                                {t("runtime.room.latestCheckpoint")}
                              </p>
                              <p className="runtime-code-inline">
                                {latestCheckpoint.checkpoint_dir}
                              </p>
                            </div>
                            <span className="text-xs text-[var(--text-quaternary)]">
                              {formatRelativeTime(latestCheckpoint.created_at)}
                            </span>
                          </div>
                        ) : null}

                        {bundle.artifacts.slice(-5).map((artifact) => (
                          <div key={artifact.id} className="runtime-log-row">
                            <div>
                              <p className="text-sm text-[var(--text-primary)]">
                                {artifact.label || artifact.artifact_kind}
                              </p>
                              <p className="runtime-code-inline">{artifact.path}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </DetailBlock>

                    <DetailBlock title={t("runtime.room.sessions")}>
                      <DetailGrid>
                        <DetailDatum label={t("runtime.room.attach")}>
                          {String(bundle.sessions.attach_sessions.length)}
                        </DetailDatum>
                        <DetailDatum label={t("runtime.room.tabs.browser")}>
                          {String(bundle.sessions.browser_sessions.length)}
                        </DetailDatum>
                        <DetailDatum label={t("runtime.room.terminals")}>
                          {String(bundle.sessions.terminals.length)}
                        </DetailDatum>
                      </DetailGrid>
                    </DetailBlock>

                    <DetailBlock title={t("runtime.room.recentGuardrails")}>
                      {bundle.guardrails.length === 0 ? (
                        <div className="runtime-empty">
                          <Waypoints className="h-5 w-5" />
                          <p>{t("runtime.room.noRecentGuardrails")}</p>
                        </div>
                      ) : (
                        <div className="space-y-2">
                          {bundle.guardrails.slice(-5).reverse().map((guardrail) => (
                            <div key={guardrail.id} className="runtime-log-row">
                              <div>
                                <p className="text-sm text-[var(--text-primary)]">
                                  {guardrail.guardrail_type}
                                </p>
                                <p className="text-xs text-[var(--text-quaternary)]">
                                  {formatRelativeTime(guardrail.created_at)}
                                </p>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </DetailBlock>
                  </div>
                ) : null}
              </div>
            </motion.aside>
          </>
        ) : null}
      </AnimatePresence>
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
      className={cn(
        "runtime-action-button",
        tone === "danger" && "runtime-action-button--danger"
      )}
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
  return (
    <AsyncActionButton
      type="button"
      className={cn(
        "runtime-menu-action",
        tone === "warning" && "runtime-menu-action--warning",
        tone === "danger" && "runtime-menu-action--danger"
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

function DetailBlock({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="runtime-detail-block">
      <div className="runtime-detail-block__header">
        <p className="runtime-panel__title">{title}</p>
      </div>
      <div className="runtime-detail-block__body">{children}</div>
    </section>
  );
}

function DetailGrid({ children }: { children: ReactNode }) {
  return <div className="runtime-detail-grid">{children}</div>;
}

function DetailDatum({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="runtime-detail-datum">
      <p className="runtime-detail-datum__label">{label}</p>
      <div className="runtime-detail-datum__value">{children}</div>
    </div>
  );
}

function RuntimeEventFeedRow({ event }: { event: RuntimeEvent }) {
  const { t } = useAppI18n();
  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -4 }}
      animate={{ opacity: 1, x: 0 }}
      className="runtime-feed-row"
    >
      <span
        className="runtime-feed-row__dot"
        style={{
          backgroundColor: `var(--tone-${getRuntimeSeverityTone(event.severity)}-dot)`,
        }}
      />

      <div className="min-w-0 flex-1">
        <div className="runtime-feed-row__top">
          <p className="truncate text-sm font-medium text-[var(--text-primary)]">
            {getRuntimeLabel(event.type || t("runtime.room.eventFallback"))}
          </p>
          <span className="text-xs text-[var(--text-quaternary)]">
            {event.ts ? formatRelativeTime(event.ts) : t("runtime.room.eventRecordedNow")}
          </span>
        </div>
        <p className="text-sm leading-6 text-[var(--text-secondary)]">
          {getEventPreview(event)}
        </p>
      </div>
    </motion.div>
  );
}

function RuntimeEventLogRow({ event }: { event: RuntimeEvent }) {
  const { t } = useAppI18n();
  return (
    <div className="runtime-log-row">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className="runtime-inline-tone"
            style={getSemanticStyle(getRuntimeSeverityTone(event.severity))}
          >
            {getRuntimeLabel(event.severity || "info")}
          </span>
          <span className="runtime-inline-id">seq {event.seq}</span>
          {event.phase ? (
            <span className="text-xs text-[var(--text-quaternary)]">
              {getRuntimeLabel(event.phase)}
            </span>
          ) : null}
        </div>
        <p className="mt-2 text-sm font-medium text-[var(--text-primary)]">
          {getRuntimeLabel(event.type || t("runtime.room.eventFallback"))}
        </p>
        <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
          {getEventPreview(event)}
        </p>
        {event.payload && Object.keys(event.payload).length > 0 ? (
          <SyntaxHighlight lang="json" className="runtime-code-block mt-3">
            {JSON.stringify(event.payload, null, 2)}
          </SyntaxHighlight>
        ) : null}
      </div>

      <div className="shrink-0 text-right">
        <p className="text-xs text-[var(--text-secondary)]">
          {event.ts ? formatRelativeTime(event.ts) : t("runtime.room.eventRecordedNow")}
        </p>
        <p className="text-xs text-[var(--text-quaternary)]">
          {event.ts ? formatDateTime(event.ts) : "—"}
        </p>
      </div>
    </div>
  );
}

function getEventPreview(event: RuntimeEvent) {
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
