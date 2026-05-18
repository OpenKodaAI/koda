"use client";

import { useCallback, useMemo, useState, type ReactNode } from "react";
import { keepPreviousData } from "@tanstack/react-query";
import {
  Archive,
  Download,
  FlaskConical,
  GitCompareArrows,
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { AgentSwitcher } from "@/components/layout/agent-switcher";
import { useAgentCatalog } from "@/components/providers/agent-catalog-provider";
import { ErrorState, InlineSpinner } from "@/components/ui/async-feedback";
import { InlineAlert } from "@/components/ui/inline-alert";
import {
  PageDataTableShell,
  PageEmptyState,
  PageMetricStrip,
  PageMetricStripItem,
  PageSearchField,
  PageSectionHeader,
} from "@/components/ui/page-primitives";
import { AnimatedCardStatusList, type Card as StatusCard } from "@/components/ui/card-status-list";
import { SoftTabs } from "@/components/ui/soft-tabs";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useMinDurationFlag } from "@/hooks/use-min-duration-flag";
import { useStableQueryData } from "@/hooks/use-stable-query-data";
import { useToast, type ToastType } from "@/hooks/use-toast";
import {
  evalErrorMessage,
  parseEvalCases,
  parseEvalRun,
  parseEvalRuns,
  parseReleaseQuality,
  parseTrajectoryExport,
  type EvalCase,
  type EvalRun,
  type ReleaseQuality,
  type TrajectoryExport,
} from "@/lib/contracts/evals";
import { requestJson } from "@/lib/http-client";
import { cn, formatRelativeTime } from "@/lib/utils";

type EvaluationsView = "cases" | "runs" | "release";

function evalsPath(agentId: string, suffix: string) {
  return `/api/control-plane/agents/${encodeURIComponent(agentId)}/evals${suffix}`;
}

function formatPercent(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${Math.round(value * 100)}%`;
}

function statusTone(status: string | null | undefined): StatusDotTone {
  if (status === "passing" || status === "passed" || status === "ready" || status === "completed") {
    return "success";
  }
  if (status === "running" || status === "queued" || status === "info") return "info";
  if (status === "degraded" || status === "blocked" || status === "warning" || status === "draft") return "warning";
  if (
    status === "failed" ||
    status === "failing" ||
    status === "denied" ||
    status === "error" ||
    status === "critical"
  ) {
    return "danger";
  }
  return "neutral";
}

function StatusLabel({ status }: { status: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-[var(--radius-chip)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-2.5 py-1 text-[0.75rem] text-[var(--text-secondary)]">
      <StatusDot tone={statusTone(status)} pulse={status === "running" || status === "queued"} />
      <span className="font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)]">
        {status}
      </span>
    </span>
  );
}

function MetricNumber({ value }: { value: number }) {
  return <span className="font-mono tabular-nums">{value}</span>;
}

export default function EvaluationsPageClient({
  initialAgentId,
}: {
  initialAgentId?: string;
}) {
  const { tl } = useAppI18n();
  const { showToast } = useToast();
  const { agents } = useAgentCatalog();
  const [activeAgentId, setActiveAgentId] = useState<string | undefined>(initialAgentId);
  const [view, setView] = useState<EvaluationsView>("cases");
  const [search, setSearch] = useState("");
  const [selectedCaseKey, setSelectedCaseKey] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [trajectoryExport, setTrajectoryExport] = useState<TrajectoryExport | null>(null);
  const [runningSuite, setRunningSuite] = useState(false);
  const [exportingTrajectory, setExportingTrajectory] = useState(false);
  const [patchingCaseKey, setPatchingCaseKey] = useState<string | null>(null);
  const debouncedSearch = useDebouncedValue(search.trim(), 180);
  const resolvedAgentId = activeAgentId ?? agents[0]?.id;

  const casesQuery = useControlPlaneQuery<EvalCase[]>({
    tier: "live",
    enabled: Boolean(resolvedAgentId),
    queryKey: ["evals", resolvedAgentId, "cases"],
    refetchInterval: 45_000,
    placeholderData: keepPreviousData,
    notifyOnChangeProps: ["data", "error"],
    queryFn: async ({ signal }) => {
      const raw = await requestJson<unknown>(
        `${evalsPath(resolvedAgentId!, "/cases")}?limit=200`,
        { signal },
      );
      return parseEvalCases(raw);
    },
  });

  const runsQuery = useControlPlaneQuery<EvalRun[]>({
    tier: "live",
    enabled: Boolean(resolvedAgentId),
    queryKey: ["evals", resolvedAgentId, "runs"],
    refetchInterval: 45_000,
    placeholderData: keepPreviousData,
    notifyOnChangeProps: ["data", "error"],
    queryFn: async ({ signal }) => {
      const raw = await requestJson<unknown>(
        `${evalsPath(resolvedAgentId!, "/runs")}?limit=60`,
        { signal },
      );
      return parseEvalRuns(raw);
    },
  });

  const releaseQuery = useControlPlaneQuery<ReleaseQuality | null>({
    tier: "live",
    enabled: Boolean(resolvedAgentId),
    queryKey: ["evals", resolvedAgentId, "release-quality"],
    refetchInterval: 60_000,
    placeholderData: keepPreviousData,
    notifyOnChangeProps: ["data", "error"],
    queryFn: async ({ signal }) => {
      const raw = await requestJson<unknown>(
        evalsPath(resolvedAgentId!, "/release-quality/latest"),
        { signal },
      );
      return parseReleaseQuality(raw);
    },
  });

  const stableCases = useStableQueryData({
    data: casesQuery.data,
    resetKey: ["evals", resolvedAgentId, "cases"],
    isPending: casesQuery.isPending,
    isFetching: casesQuery.isFetching,
    error: casesQuery.error,
  });
  const stableRuns = useStableQueryData({
    data: runsQuery.data,
    resetKey: ["evals", resolvedAgentId, "runs"],
    isPending: runsQuery.isPending,
    isFetching: runsQuery.isFetching,
    error: runsQuery.error,
  });
  const stableRelease = useStableQueryData({
    data: releaseQuery.data,
    resetKey: ["evals", resolvedAgentId, "release"],
    isPending: releaseQuery.isPending,
    isFetching: releaseQuery.isFetching,
    error: releaseQuery.error,
  });

  const cases = useMemo(() => stableCases.data ?? [], [stableCases.data]);
  const runs = useMemo(() => stableRuns.data ?? [], [stableRuns.data]);
  const releaseQuality = stableRelease.data ?? null;
  const selectedCase = useMemo(
    () => cases.find((item) => item.case_key === selectedCaseKey) ?? cases[0] ?? null,
    [cases, selectedCaseKey],
  );
  const selectedRun = useMemo(
    () => runs.find((item) => item.run_id === selectedRunId) ?? runs[0] ?? releaseQuality?.latest_eval_run ?? null,
    [releaseQuality?.latest_eval_run, runs, selectedRunId],
  );

  const filteredCases = useMemo(() => {
    const query = debouncedSearch.toLowerCase();
    if (!query) return cases;
    return cases.filter((item) =>
      `${item.case_key} ${item.title} ${item.input_preview} ${item.status}`
        .toLowerCase()
        .includes(query),
    );
  }, [cases, debouncedSearch]);

  const readyCases = useMemo(
    () => cases.filter((item) => item.status === "ready" || item.status === "active"),
    [cases],
  );
  const latestRun = runs[0] ?? releaseQuality?.latest_eval_run ?? null;
  const latestScore = latestRun?.summary.score ?? null;
  const latestExport = trajectoryExport ?? releaseQuality?.latest_trajectory_export ?? null;
  const evalStatusCards = useMemo<StatusCard[]>(() => {
    const hasRunningEval =
      runningSuite ||
      runs.some((run) => run.status === "running" || run.status === "queued");
    const latestRunHasFailures = (latestRun?.summary.failed ?? 0) > 0;
    const releaseStatus = releaseQuality?.status ?? "unknown";
    return [
      {
        id: "case-readiness",
        title: `${readyCases.length}/${cases.length} cases ready`,
        status: cases.length === 0 || readyCases.length === 0 ? "updates-found" : "completed",
      },
      {
        id: "suite-run",
        title: latestRun
          ? `Latest suite ${latestRun.status}`
          : "No deterministic suite yet",
        status: hasRunningEval
          ? "syncing"
          : latestRun && !latestRunHasFailures
            ? "completed"
            : "updates-found",
      },
      {
        id: "trajectory-export",
        title: latestExport?.redaction_applied
          ? "Trajectory export redacted"
          : "Trajectory export missing",
        status: exportingTrajectory
          ? "syncing"
          : latestExport?.redaction_applied
            ? "completed"
            : "updates-found",
      },
      {
        id: "release-quality",
        title: releaseQuality
          ? `Release quality ${releaseStatus}`
          : "Release quality unpublished",
        status:
          releaseStatus === "passing" || releaseStatus === "passed"
            ? "completed"
            : "updates-found",
      },
      {
        id: "failure-drilldown",
        title: `${latestRun?.top_failures.length ?? releaseQuality?.top_failures.length ?? 0} top failure groups`,
        status:
          (latestRun?.top_failures.length ?? releaseQuality?.top_failures.length ?? 0) > 0
            ? "updates-found"
            : "completed",
      },
    ];
  }, [
    cases.length,
    exportingTrajectory,
    latestExport?.redaction_applied,
    latestRun,
    readyCases.length,
    releaseQuality,
    runningSuite,
    runs,
  ]);

  const initialLoading = stableCases.initialLoading || stableRuns.initialLoading || stableRelease.initialLoading;
  const showSkeleton = useMinDurationFlag(Boolean(resolvedAgentId) && initialLoading, 300);
  const blockingError =
    stableCases.showBlockingError || stableRuns.showBlockingError || stableRelease.showBlockingError;
  const errorMessage =
    casesQuery.error?.message ??
    runsQuery.error?.message ??
    releaseQuery.error?.message ??
    null;

  const refreshAll = useCallback(async () => {
    await Promise.all([
      casesQuery.refetch(),
      runsQuery.refetch(),
      releaseQuery.refetch(),
    ]);
  }, [casesQuery, releaseQuery, runsQuery]);

  const notify = useCallback(
    (message: string, type: ToastType) => {
      showToast(message, type);
    },
    [showToast],
  );

  const runSuite = useCallback(async () => {
    if (!resolvedAgentId) return;
    setRunningSuite(true);
    try {
      const raw = await requestJson<unknown>(evalsPath(resolvedAgentId, "/runs"), {
        method: "POST",
        body: JSON.stringify({
          mode: "offline",
          case_keys: readyCases.length > 0 ? readyCases.map((item) => item.case_key) : cases.map((item) => item.case_key),
        }),
      });
      const run = parseEvalRun(raw);
      if (run) setSelectedRunId(run.run_id);
      setView("runs");
      notify(tl("Offline eval suite started."), "success");
      await refreshAll();
    } catch (error) {
      notify(evalErrorMessage(error, tl("Could not run eval suite.")), "error");
    } finally {
      setRunningSuite(false);
    }
  }, [cases, notify, readyCases, refreshAll, resolvedAgentId, tl]);

  const exportTrajectory = useCallback(async () => {
    if (!resolvedAgentId) return;
    const runId = selectedRun?.run_id ?? latestRun?.run_id;
    if (!runId) {
      notify(tl("Run an eval suite before exporting a trajectory."), "warning");
      return;
    }
    setExportingTrajectory(true);
    try {
      const raw = await requestJson<unknown>(evalsPath(resolvedAgentId, "/trajectory-exports"), {
        method: "POST",
        body: JSON.stringify({
          run_id: runId,
          replay_mode: "offline",
          format: "jsonl",
        }),
      });
      const exported = parseTrajectoryExport(raw);
      setTrajectoryExport(exported);
      setView("release");
      notify(tl("Redacted trajectory export requested."), "success");
      await releaseQuery.refetch();
    } catch (error) {
      notify(evalErrorMessage(error, tl("Could not export trajectory.")), "error");
    } finally {
      setExportingTrajectory(false);
    }
  }, [latestRun?.run_id, notify, releaseQuery, resolvedAgentId, selectedRun?.run_id, tl]);

  const patchCaseStatus = useCallback(async (caseKey: string, status: EvalCase["status"]) => {
    if (!resolvedAgentId) return;
    setPatchingCaseKey(caseKey);
    try {
      await requestJson<unknown>(
        evalsPath(resolvedAgentId, `/cases/${encodeURIComponent(caseKey)}`),
        {
          method: "PATCH",
          body: JSON.stringify({ status }),
        },
      );
      notify(tl("Eval case updated."), "success");
      await casesQuery.refetch();
    } catch (error) {
      notify(evalErrorMessage(error, tl("Could not update eval case.")), "error");
    } finally {
      setPatchingCaseKey(null);
    }
  }, [casesQuery, notify, resolvedAgentId, tl]);

  const synchronizeEvalStatus = useCallback((cardId: string) => {
    if (cardId === "suite-run" && cases.length > 0) {
      void runSuite();
      return;
    }
    if (cardId === "trajectory-export" && selectedRun) {
      void exportTrajectory();
      return;
    }
    void refreshAll();
  }, [cases.length, exportTrajectory, refreshAll, runSuite, selectedRun]);

  if (agents.length === 0) {
    return (
      <PageEmptyState
        icon={FlaskConical}
        title={tl("No agents available")}
        description={tl("Create an agent before running Phase 5 evals.")}
      />
    );
  }

  if (blockingError && errorMessage) {
    return (
      <ErrorState
        title={tl("Evals unavailable")}
        description={errorMessage}
        onRetry={() => {
          void refreshAll();
        }}
      />
    );
  }

  if (showSkeleton) {
    return <EvaluationsPageSkeleton />;
  }

  return (
    <div className="min-w-0 space-y-4">
      <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
        <div className="w-full md:w-[220px] md:flex-none">
          <AgentSwitcher
            activeBotId={resolvedAgentId}
            onAgentChange={setActiveAgentId}
            showAll={false}
            showCreate={false}
            variant="field"
            className="agent-switcher--compact"
          />
        </div>
        <div className="w-full md:min-w-[220px] md:flex-1">
          <PageSearchField
            value={search}
            onChange={setSearch}
            placeholder={tl("Search eval cases")}
          />
        </div>
        <SoftTabs
          items={[
            { id: "cases", label: tl("Cases") },
            { id: "runs", label: tl("Runs") },
            { id: "release", label: tl("Release") },
          ]}
          value={view}
          onChange={(id) => setView(id as EvaluationsView)}
          ariaLabel={tl("Evaluation views")}
        />
        <div className="flex flex-wrap items-center gap-2 md:ml-auto">
          <button
            type="button"
            className="button-shell button-shell--secondary button-shell--sm gap-2 px-3"
            onClick={() => {
              void refreshAll();
            }}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            {tl("Refresh")}
          </button>
          <button
            type="button"
            className="button-shell button-shell--primary button-shell--sm min-w-28 gap-2 px-3"
            disabled={runningSuite || cases.length === 0}
            aria-label={runningSuite ? tl("Starting") : undefined}
            aria-busy={runningSuite || undefined}
            onClick={() => {
              void runSuite();
            }}
          >
            {runningSuite ? (
              <InlineSpinner className="h-3.5 w-3.5" />
            ) : (
              <>
                <FlaskConical className="h-3.5 w-3.5" />
                {tl("Run suite")}
              </>
            )}
          </button>
          <button
            type="button"
            className="button-shell button-shell--secondary button-shell--sm min-w-36 gap-2 px-3"
            disabled={exportingTrajectory || !selectedRun}
            aria-label={exportingTrajectory ? tl("Exporting") : undefined}
            aria-busy={exportingTrajectory || undefined}
            onClick={() => {
              void exportTrajectory();
            }}
          >
            {exportingTrajectory ? (
              <InlineSpinner className="h-3.5 w-3.5" />
            ) : (
              <>
                <Download className="h-3.5 w-3.5" />
                {tl("Export trajectory")}
              </>
            )}
          </button>
        </div>
      </div>

      <PageMetricStrip>
        <PageMetricStripItem label={tl("Cases")} value={<MetricNumber value={cases.length} />} />
        <PageMetricStripItem label={tl("Ready")} value={<MetricNumber value={readyCases.length} />} tone="success" />
        <PageMetricStripItem
          label={tl("Latest score")}
          value={formatPercent(latestScore)}
          tone={latestScore == null ? "neutral" : latestScore >= 0.8 ? "success" : "danger"}
        />
        <PageMetricStripItem
          label={tl("Release quality")}
          value={releaseQuality?.status ?? "unknown"}
          tone={
            releaseQuality?.status === "passing" || releaseQuality?.status === "passed"
              ? "success"
              : releaseQuality?.status === "failing" || releaseQuality?.status === "failed"
                ? "danger"
                : "warning"
          }
        />
      </PageMetricStrip>

      {view === "cases" ? (
        <CasesPanel
          cases={filteredCases}
          selectedCase={selectedCase}
          statusCards={evalStatusCards}
          patchingCaseKey={patchingCaseKey}
          onSelectCase={(caseKey) => setSelectedCaseKey(caseKey)}
          onPatchStatus={patchCaseStatus}
          onSynchronizeStatus={synchronizeEvalStatus}
        />
      ) : view === "runs" ? (
        <RunsPanel
          runs={runs}
          selectedRun={selectedRun}
          statusCards={evalStatusCards}
          onSelectRun={(runId) => setSelectedRunId(runId)}
          onSynchronizeStatus={synchronizeEvalStatus}
        />
      ) : (
        <ReleasePanel
          releaseQuality={releaseQuality}
          selectedRun={selectedRun}
          trajectoryExport={trajectoryExport}
          statusCards={evalStatusCards}
          onSynchronizeStatus={synchronizeEvalStatus}
        />
      )}
    </div>
  );
}

function SkeletonBlock({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} />;
}

function EvaluationsPageSkeleton() {
  return (
    <div
      className="min-w-0 space-y-4"
      aria-hidden="true"
      data-testid="evaluations-page-skeleton"
    >
      <div
        className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center"
        data-testid="evaluations-skeleton-toolbar"
      >
        <div className="w-full md:w-[220px] md:flex-none">
          <SkeletonBlock className="h-9 w-full rounded-[var(--radius-input)]" />
        </div>
        <div className="w-full md:min-w-[220px] md:flex-1">
          <SkeletonBlock className="h-9 w-full rounded-[var(--radius-input)]" />
        </div>
        <div className="flex h-9 w-full items-center gap-1 rounded-[var(--radius-pill)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] p-0.5 sm:w-[228px]">
          {Array.from({ length: 3 }).map((_, index) => (
            <SkeletonBlock
              key={index}
              className="h-8 flex-1 rounded-[var(--radius-pill)]"
            />
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2 md:ml-auto">
          <SkeletonBlock className="h-8 w-24 rounded-[var(--radius-panel-sm)]" />
          <SkeletonBlock className="h-8 w-28 rounded-[var(--radius-panel-sm)]" />
          <SkeletonBlock className="h-8 w-36 rounded-[var(--radius-panel-sm)]" />
        </div>
      </div>

      <PageMetricStrip>
        {["w-12", "w-10", "w-20", "w-24"].map((width, index) => (
          <div
            key={index}
            className="metric-strip__item"
            data-testid="evaluations-skeleton-metric"
          >
            <SkeletonBlock className="h-3 w-20 rounded" />
            <SkeletonBlock className={cn("mt-2 h-6 rounded", width)} />
          </div>
        ))}
      </PageMetricStrip>

      <div
        className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.8fr)]"
        data-testid="evaluations-skeleton-cases-layout"
      >
        <section className="app-section min-w-0">
          <SkeletonSectionHeader
            eyebrowWidth="w-24"
            titleWidth="w-32"
            descriptionWidth="w-72"
          />
          <PageDataTableShell className="mt-3">
            <table className="min-w-full text-left text-[0.8125rem]">
              <thead className="border-y border-[var(--divider-hair)]">
                <tr>
                  {["w-10", "w-12", "w-12", "w-14"].map((width, index) => (
                    <th key={index} className="px-3 py-2">
                      <SkeletonBlock className={cn("h-3 rounded", width)} />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--divider-hair)]">
                {Array.from({ length: 5 }).map((_, index) => (
                  <tr key={index}>
                    <td className="max-w-[420px] px-3 py-3">
                      <SkeletonBlock className="h-4 w-[min(280px,80%)] rounded" />
                      <SkeletonBlock className="mt-2 h-3 w-[min(220px,65%)] rounded" />
                    </td>
                    <td className="px-3 py-3">
                      <SkeletonBlock className="h-7 w-24 rounded-[var(--radius-chip)]" />
                    </td>
                    <td className="px-3 py-3">
                      <SkeletonBlock className="h-3 w-12 rounded" />
                    </td>
                    <td className="px-3 py-3">
                      <SkeletonBlock className="h-3 w-16 rounded" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </PageDataTableShell>
        </section>

        <section className="app-section min-w-0">
          <SkeletonSectionHeader eyebrowWidth="w-20" titleWidth="w-32" />
          <div className="mt-3 space-y-4">
            <div>
              <SkeletonBlock className="h-4 w-52 rounded" />
              <SkeletonBlock className="mt-2 h-3 w-36 rounded" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              {Array.from({ length: 4 }).map((_, index) => (
                <div
                  key={index}
                  className="min-w-0 rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 py-2.5"
                >
                  <SkeletonBlock className="h-3 w-16 rounded" />
                  <SkeletonBlock className="mt-2 h-4 w-20 rounded" />
                </div>
              ))}
            </div>
            <SkeletonCodePreview />
            <SkeletonCodePreview />
            <div className="flex flex-wrap gap-2">
              <SkeletonBlock className="h-8 w-28 rounded-[var(--radius-panel-sm)]" />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function SkeletonSectionHeader({
  eyebrowWidth,
  titleWidth,
  descriptionWidth,
}: {
  eyebrowWidth: string;
  titleWidth: string;
  descriptionWidth?: string;
}) {
  return (
    <div className="app-section__header gap-1">
      <div className="min-w-0">
        <SkeletonBlock className={cn("h-3 rounded", eyebrowWidth)} />
        <SkeletonBlock className={cn("mt-2 h-5 rounded", titleWidth)} />
        {descriptionWidth ? (
          <SkeletonBlock className={cn("mt-2 h-3 rounded", descriptionWidth)} />
        ) : null}
      </div>
    </div>
  );
}

function SkeletonCodePreview() {
  return (
    <div className="rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)]">
      <div className="border-b border-[var(--divider-hair)] px-3 py-2">
        <SkeletonBlock className="h-3 w-16 rounded" />
      </div>
      <div className="space-y-2 px-3 py-3">
        <SkeletonBlock className="h-3 w-full rounded" />
        <SkeletonBlock className="h-3 w-4/5 rounded" />
        <SkeletonBlock className="h-3 w-2/3 rounded" />
      </div>
    </div>
  );
}

function CasesPanel({
  cases,
  selectedCase,
  statusCards,
  patchingCaseKey,
  onSelectCase,
  onPatchStatus,
  onSynchronizeStatus,
}: {
  cases: EvalCase[];
  selectedCase: EvalCase | null;
  statusCards: StatusCard[];
  patchingCaseKey: string | null;
  onSelectCase: (caseKey: string) => void;
  onPatchStatus: (caseKey: string, status: EvalCase["status"]) => void;
  onSynchronizeStatus: (cardId: string) => void;
}) {
  const { tl } = useAppI18n();
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.8fr)]">
      <section className="app-section min-w-0">
        <PageSectionHeader
          compact
          eyebrow="eval_case.v1"
          title={tl("Eval cases")}
          description={tl("Cases created from real runs or seeded knowledge evals.")}
        />
        <PageDataTableShell className="mt-3">
          <table className="min-w-full text-left text-[0.8125rem]">
            <thead className="border-y border-[var(--divider-hair)] text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
              <tr>
                <th className="px-3 py-2 font-medium">{tl("Case")}</th>
                <th className="px-3 py-2 font-medium">{tl("Status")}</th>
                <th className="px-3 py-2 font-medium">{tl("Source")}</th>
                <th className="px-3 py-2 font-medium">{tl("Updated")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--divider-hair)]">
              {cases.map((item) => (
                <tr
                  key={item.case_key}
                  className={cn(
                    "cursor-pointer transition-colors hover:bg-[var(--hover-tint)]",
                    selectedCase?.case_key === item.case_key && "bg-[var(--panel-soft)]",
                  )}
                  onClick={() => onSelectCase(item.case_key)}
                >
                  <td className="max-w-[420px] px-3 py-3">
                    <div className="truncate font-medium text-[var(--text-primary)]">{item.title}</div>
                    <div className="truncate font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                      {item.case_key}
                    </div>
                  </td>
                  <td className="px-3 py-3"><StatusLabel status={item.status} /></td>
                  <td className="px-3 py-3 text-[var(--text-secondary)]">{item.source}</td>
                  <td className="px-3 py-3 text-[var(--text-tertiary)]">
                    {formatRelativeTime(item.updated_at ?? item.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </PageDataTableShell>
        {cases.length === 0 ? (
          <PageEmptyState
            icon={Archive}
            title={tl("No eval cases")}
            description={tl("Create one from an execution detail once the backend publishes eval_case.v1.")}
          />
        ) : null}
      </section>

      <aside className="min-w-0 space-y-4">
        <AnimatedCardStatusList
          title={tl("Eval readiness")}
          cards={statusCards}
          sort="attention-first"
          synchronizeLabel={tl("Sync")}
          onSynchronize={onSynchronizeStatus}
        />
        <section className="app-section min-w-0">
          <PageSectionHeader compact eyebrow="case detail" title={tl("Selected case")} />
          {selectedCase ? (
            <div className="mt-3 space-y-4">
              <div>
                <p className="m-0 text-[0.875rem] font-medium text-[var(--text-primary)]">{selectedCase.title}</p>
                <p className="m-0 mt-1 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                  {selectedCase.case_key}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3 text-[0.8125rem]">
                <DetailDatum label={tl("Task")} value={selectedCase.source_task_id ?? "-"} />
                <DetailDatum label={tl("Kind")} value={selectedCase.task_kind} />
                <DetailDatum label={tl("Sources")} value={selectedCase.expected_sources.length} />
                <DetailDatum label={tl("Policies")} value={selectedCase.policy_expectations.length} />
              </div>
              <CodePreview title={tl("Input")} value={selectedCase.input_preview || "-"} />
              <CodePreview title={tl("Expected")} value={selectedCase.expected_output_preview || "-"} />
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="button-shell button-shell--secondary button-shell--sm px-3"
                  disabled={patchingCaseKey === selectedCase.case_key}
                  onClick={() => onPatchStatus(selectedCase.case_key, selectedCase.status === "ready" ? "draft" : "ready")}
                >
                  {patchingCaseKey === selectedCase.case_key
                    ? tl("Saving")
                    : selectedCase.status === "ready"
                      ? tl("Move to draft")
                      : tl("Mark ready")}
                </button>
              </div>
            </div>
          ) : (
            <PageEmptyState icon={Archive} title={tl("Select an eval case")} />
          )}
        </section>
      </aside>
    </div>
  );
}

function RunsPanel({
  runs,
  selectedRun,
  statusCards,
  onSelectRun,
  onSynchronizeStatus,
}: {
  runs: EvalRun[];
  selectedRun: EvalRun | null;
  statusCards: StatusCard[];
  onSelectRun: (runId: string) => void;
  onSynchronizeStatus: (cardId: string) => void;
}) {
  const { tl } = useAppI18n();
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.8fr)]">
      <section className="app-section min-w-0">
        <PageSectionHeader
          compact
          eyebrow="eval_run.v1"
          title={tl("Eval runs")}
          description={tl("Offline replay suites and deterministic smoke runs.")}
        />
        <div className="mt-3 divide-y divide-[var(--divider-hair)]">
          {runs.map((run) => (
            <button
              key={run.run_id}
              type="button"
              onClick={() => onSelectRun(run.run_id)}
              className={cn(
                "grid w-full grid-cols-[1fr_auto] gap-3 px-3 py-3 text-left transition-colors hover:bg-[var(--hover-tint)]",
                selectedRun?.run_id === run.run_id && "bg-[var(--panel-soft)]",
              )}
            >
              <span className="min-w-0">
                <span className="block truncate text-[0.875rem] font-medium text-[var(--text-primary)]">
                  {run.suite_name || run.strategy}
                </span>
                <span className="block truncate font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                  {run.run_id}
                </span>
              </span>
              <span className="flex flex-col items-end gap-1">
                <StatusLabel status={run.status} />
                <span className="text-[0.75rem] text-[var(--text-tertiary)]">
                  {formatRelativeTime(run.completed_at ?? run.created_at ?? run.started_at)}
                </span>
              </span>
            </button>
          ))}
        </div>
        {runs.length === 0 ? (
          <PageEmptyState
            icon={FlaskConical}
            title={tl("No eval runs")}
            description={tl("Run a deterministic suite after cases are available.")}
          />
        ) : null}
      </section>

      <aside className="min-w-0 space-y-4">
        <AnimatedCardStatusList
          title={tl("Eval run health")}
          cards={statusCards}
          sort="attention-first"
          synchronizeLabel={tl("Sync")}
          onSynchronize={onSynchronizeStatus}
        />
        <section className="app-section min-w-0">
          <PageSectionHeader compact eyebrow="failure drilldown" title={tl("Run detail")} />
          {selectedRun ? (
            <div className="mt-3 space-y-4">
              <div className="grid grid-cols-3 gap-3">
                <DetailDatum label={tl("Score")} value={formatPercent(selectedRun.summary.score)} />
                <DetailDatum label={tl("Passed")} value={selectedRun.summary.passed} />
                <DetailDatum label={tl("Failed")} value={selectedRun.summary.failed} />
              </div>
              <div className="divide-y divide-[var(--divider-hair)] rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)]">
                {selectedRun.cases.map((result) => (
                  <div key={result.case_key} className="grid grid-cols-[1fr_auto] gap-3 px-3 py-2.5">
                    <div className="min-w-0">
                      <p className="m-0 truncate text-[0.8125rem] text-[var(--text-primary)]">
                        {result.title || result.case_key}
                      </p>
                      <p className="m-0 truncate text-[0.75rem] text-[var(--text-tertiary)]">
                        {result.message || result.failure_category || "No failure detail"}
                      </p>
                    </div>
                    <StatusLabel status={result.status} />
                  </div>
                ))}
              </div>
              <FailureList failures={selectedRun.top_failures} />
            </div>
          ) : (
            <PageEmptyState icon={GitCompareArrows} title={tl("Select an eval run")} />
          )}
        </section>
      </aside>
    </div>
  );
}

function ReleasePanel({
  releaseQuality,
  selectedRun,
  trajectoryExport,
  statusCards,
  onSynchronizeStatus,
}: {
  releaseQuality: ReleaseQuality | null;
  selectedRun: EvalRun | null;
  trajectoryExport: TrajectoryExport | null;
  statusCards: StatusCard[];
  onSynchronizeStatus: (cardId: string) => void;
}) {
  const { tl } = useAppI18n();
  const exportPayload = trajectoryExport ?? releaseQuality?.latest_trajectory_export ?? null;
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.8fr)]">
      <section className="app-section min-w-0">
        <PageSectionHeader
          compact
          eyebrow="release_quality.v1"
          title={tl("Release gates")}
          description={tl("Release quality claims require deterministic eval and smoke gates.")}
          meta={releaseQuality ? <StatusLabel status={releaseQuality.status} /> : null}
        />
        <div className="mt-3 divide-y divide-[var(--divider-hair)]">
          {(releaseQuality?.gates ?? []).map((gate) => (
            <div key={gate.id} className="grid grid-cols-[auto_1fr_auto] items-start gap-3 px-3 py-3">
              <ShieldCheck className="mt-1 h-4 w-4 text-[var(--text-tertiary)]" />
              <div className="min-w-0">
                <p className="m-0 text-[0.875rem] font-medium text-[var(--text-primary)]">{gate.title}</p>
                <p className="m-0 mt-1 text-[0.75rem] leading-5 text-[var(--text-tertiary)]">{gate.summary}</p>
              </div>
              <StatusLabel status={gate.status} />
            </div>
          ))}
        </div>
        {!releaseQuality || releaseQuality.gates.length === 0 ? (
          <PageEmptyState
            icon={TriangleAlert}
            title={tl("No release quality status")}
            description={tl("The backend has not published release_quality.v1 yet.")}
          />
        ) : null}
      </section>

      <aside className="min-w-0 space-y-4">
        <AnimatedCardStatusList
          title={tl("Release readiness")}
          cards={statusCards}
          sort="attention-first"
          synchronizeLabel={tl("Sync")}
          onSynchronize={onSynchronizeStatus}
        />
        <section className="app-section min-w-0">
          <PageSectionHeader compact eyebrow="trajectory_export.v1" title={tl("Trajectory export")} />
          <div className="mt-3 space-y-4">
            {exportPayload ? (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <DetailDatum label={tl("Status")} value={<StatusLabel status={exportPayload.status} />} />
                  <DetailDatum label={tl("Lines")} value={exportPayload.line_count} />
                  <DetailDatum label={tl("Redactions")} value={exportPayload.redactions?.count ?? 0} />
                  <DetailDatum label={tl("Replay")} value={exportPayload.replay_mode} />
                </div>
                <InlineAlert tone={exportPayload.redaction_applied ? "success" : "danger"}>
                  {exportPayload.redaction_applied
                    ? tl("Export is redacted and provider calls are disabled.")
                    : tl("Export is not marked redacted. Do not use for handoff.")}
                </InlineAlert>
                {exportPayload.download_url ? (
                  <a href={exportPayload.download_url} className="button-shell button-shell--secondary button-shell--sm inline-flex px-3">
                    {tl("Download JSONL")}
                  </a>
                ) : null}
              </>
            ) : (
              <PageEmptyState
                icon={Download}
                title={tl("No trajectory export")}
                description={selectedRun ? tl("Export the selected run to produce a redacted JSONL bundle.") : tl("Run a suite before exporting.")}
              />
            )}
            <FailureList failures={releaseQuality?.top_failures ?? []} />
          </div>
        </section>
      </aside>
    </div>
  );
}

function DetailDatum({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0 rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 py-2.5">
      <p className="m-0 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
        {label}
      </p>
      <p className="m-0 mt-1 truncate text-[0.8125rem] text-[var(--text-primary)]">{value}</p>
    </div>
  );
}

function CodePreview({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)]">
      <div className="border-b border-[var(--divider-hair)] px-3 py-2 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
        {title}
      </div>
      <pre className="m-0 max-h-48 overflow-auto whitespace-pre-wrap break-words px-3 py-3 text-[0.75rem] leading-5 text-[var(--text-secondary)]">
        {value}
      </pre>
    </div>
  );
}

function FailureList({ failures }: { failures: EvalRun["top_failures"] }) {
  const { tl } = useAppI18n();
  if (failures.length === 0) {
    return (
      <InlineAlert tone="success">
        {tl("No top failures reported.")}
      </InlineAlert>
    );
  }
  return (
    <div className="space-y-2">
      <p className="m-0 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
        {tl("Top failures")}
      </p>
      {failures.map((failure) => (
        <div
          key={`${failure.kind}:${failure.name}`}
          className="grid grid-cols-[auto_1fr_auto] items-start gap-3 rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 py-2.5"
        >
          <StatusDot tone={statusTone(failure.severity)} />
          <div className="min-w-0">
            <p className="m-0 truncate text-[0.8125rem] text-[var(--text-primary)]">{failure.name}</p>
            <p className="m-0 mt-0.5 text-[0.75rem] text-[var(--text-tertiary)]">
              {failure.kind}{failure.message ? ` · ${failure.message}` : ""}
            </p>
          </div>
          <span className="font-mono text-[0.75rem] text-[var(--text-secondary)]">{failure.count}</span>
        </div>
      ))}
    </div>
  );
}
