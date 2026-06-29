"use client";

import { useCallback, useMemo, useState, type ReactNode } from "react";
import { keepPreviousData } from "@tanstack/react-query";
import { translate } from "@/lib/i18n";
import {
  Archive,
  CheckCircle2,
  Download,
  FlaskConical,
  GitCompareArrows,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  TriangleAlert,
  XCircle,
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
import { SoftTabs } from "@/components/ui/soft-tabs";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useAppI18n } from "@/hooks/use-app-i18n";
import { useMinDurationFlag } from "@/hooks/use-min-duration-flag";
import { useStableQueryData } from "@/hooks/use-stable-query-data";
import { useToast, type ToastType } from "@/hooks/use-toast";
import { useUrlSyncedSearch } from "@/hooks/use-url-synced-search";
import {
  evalErrorMessage,
  getRunGraphReleaseGate,
  getRunGraphReleaseWarnings,
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
import {
  formatProposalJson,
  parseImprovementProposal,
  parseImprovementProposals,
  type ImprovementProposal,
  type ImprovementProposalAction,
} from "@/lib/contracts/improvement-proposals";
import {
  parseQualityCockpit,
  type QualityCockpit,
  type QualityCockpitFailure,
} from "@/lib/contracts/quality-cockpit";
import { requestJson } from "@/lib/http-client";
import { cn, formatRelativeTime } from "@/lib/utils";

type EvaluationsView = "cases" | "runs" | "release" | "quality" | "proposals";

function evalsPath(agentId: string, suffix: string) {
  return `/api/control-plane/agents/${encodeURIComponent(agentId)}/evals${suffix}`;
}

function proposalsPath(agentId: string, suffix = "") {
  return `/api/control-plane/agents/${encodeURIComponent(agentId)}/improvement-proposals${suffix}`;
}

function qualityCockpitPath(agentId: string) {
  return `/api/control-plane/dashboard/quality/agents/${encodeURIComponent(agentId)}`;
}

function formatPercent(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "-";
  return `${Math.round(value * 100)}%`;
}

function statusTone(status: string | null | undefined): StatusDotTone {
  if (
    status === "passing" ||
    status === "passed" ||
    status === "ready" ||
    status === "completed" ||
    status === "approved" ||
    status === "applied"
  ) {
    return "success";
  }
  if (status === "running" || status === "queued" || status === "info" || status === "validating") return "info";
  if (status === "degraded" || status === "blocked" || status === "warning" || status === "draft" || status === "pending_review" || status === "rolled_back") return "warning";
  if (
    status === "failed" ||
    status === "failing" ||
    status === "denied" ||
    status === "error" ||
    status === "critical" ||
    status === "rejected"
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
  const { t } = useAppI18n();
  const { showToast } = useToast();
  const { agents } = useAgentCatalog();
  const [activeAgentId, setActiveAgentId] = useState<string | undefined>(initialAgentId);
  const [view, setView] = useState<EvaluationsView>("cases");
  const searchState = useUrlSyncedSearch({ debounceMs: 180 });
  const search = searchState.value;
  const setSearch = searchState.setValue;
  const [selectedCaseKey, setSelectedCaseKey] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [trajectoryExport, setTrajectoryExport] = useState<TrajectoryExport | null>(null);
  const [runningSuite, setRunningSuite] = useState(false);
  const [exportingTrajectory, setExportingTrajectory] = useState(false);
  const [patchingCaseKey, setPatchingCaseKey] = useState<string | null>(null);
  const [proposalActionKey, setProposalActionKey] = useState<string | null>(null);
  const debouncedSearch = searchState.debouncedValue;
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

  const proposalsQuery = useControlPlaneQuery<ImprovementProposal[]>({
    tier: "live",
    enabled: Boolean(resolvedAgentId),
    queryKey: ["evals", resolvedAgentId, "improvement-proposals"],
    refetchInterval: 45_000,
    placeholderData: keepPreviousData,
    notifyOnChangeProps: ["data", "error"],
    queryFn: async ({ signal }) => {
      const raw = await requestJson<unknown>(
        `${proposalsPath(resolvedAgentId!)}?limit=80`,
        { signal },
      );
      return parseImprovementProposals(raw);
    },
  });

  const qualityQuery = useControlPlaneQuery<QualityCockpit | null>({
    tier: "live",
    enabled: Boolean(resolvedAgentId),
    queryKey: ["evals", resolvedAgentId, "quality-cockpit"],
    refetchInterval: 60_000,
    placeholderData: keepPreviousData,
    notifyOnChangeProps: ["data", "error"],
    queryFn: async ({ signal }) => {
      const raw = await requestJson<unknown>(qualityCockpitPath(resolvedAgentId!), { signal });
      return parseQualityCockpit(raw);
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
  const stableProposals = useStableQueryData({
    data: proposalsQuery.data,
    resetKey: ["evals", resolvedAgentId, "improvement-proposals"],
    isPending: proposalsQuery.isPending,
    isFetching: proposalsQuery.isFetching,
    error: proposalsQuery.error,
  });
  const stableQuality = useStableQueryData({
    data: qualityQuery.data,
    resetKey: ["evals", resolvedAgentId, "quality-cockpit"],
    isPending: qualityQuery.isPending,
    isFetching: qualityQuery.isFetching,
    error: qualityQuery.error,
  });

  const cases = useMemo(() => stableCases.data ?? [], [stableCases.data]);
  const runs = useMemo(() => stableRuns.data ?? [], [stableRuns.data]);
  const proposals = useMemo(() => stableProposals.data ?? [], [stableProposals.data]);
  const releaseQuality = stableRelease.data ?? null;
  const qualityCockpit = stableQuality.data ?? null;
  const selectedCase = useMemo(
    () => cases.find((item) => item.case_key === selectedCaseKey) ?? cases[0] ?? null,
    [cases, selectedCaseKey],
  );
  const selectedRun = useMemo(
    () => runs.find((item) => item.run_id === selectedRunId) ?? runs[0] ?? releaseQuality?.latest_eval_run ?? null,
    [releaseQuality?.latest_eval_run, runs, selectedRunId],
  );
  const selectedProposal = useMemo(
    () => proposals.find((item) => item.proposal_id === selectedProposalId) ?? proposals[0] ?? null,
    [proposals, selectedProposalId],
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

  const filteredProposals = useMemo(() => {
    const query = debouncedSearch.toLowerCase();
    if (!query) return proposals;
    return proposals.filter((item) =>
      `${item.proposal_id} ${item.summary} ${item.status} ${item.proposal_type} ${item.source_ref}`
        .toLowerCase()
        .includes(query),
    );
  }, [debouncedSearch, proposals]);

  const readyCases = useMemo(
    () => cases.filter((item) => item.status === "ready" || item.status === "active"),
    [cases],
  );
  const latestRun = runs[0] ?? releaseQuality?.latest_eval_run ?? null;
  const latestScore = latestRun?.summary.score ?? null;

  const openProposals = proposals.filter((item) =>
    ["draft", "pending_review", "approved", "validating"].includes(item.status),
  );

  const initialLoading =
    stableCases.initialLoading ||
    stableRuns.initialLoading ||
    stableRelease.initialLoading ||
    stableProposals.initialLoading ||
    stableQuality.initialLoading;
  const showSkeleton = useMinDurationFlag(Boolean(resolvedAgentId) && initialLoading, 300);
  const blockingError =
    stableCases.showBlockingError ||
    stableRuns.showBlockingError ||
    stableRelease.showBlockingError ||
    stableProposals.showBlockingError ||
    stableQuality.showBlockingError;
  const errorMessage =
    casesQuery.error?.message ??
    runsQuery.error?.message ??
    releaseQuery.error?.message ??
    proposalsQuery.error?.message ??
    qualityQuery.error?.message ??
    null;

  const refreshAll = useCallback(async () => {
    await Promise.all([
      casesQuery.refetch(),
      runsQuery.refetch(),
      releaseQuery.refetch(),
      proposalsQuery.refetch(),
      qualityQuery.refetch(),
    ]);
  }, [casesQuery, proposalsQuery, qualityQuery, releaseQuery, runsQuery]);

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
      notify(t("generated.evaluations.offline_eval_suite_started_009e31b6"), "success");
      await refreshAll();
    } catch (error) {
      notify(evalErrorMessage(error, t("generated.evaluations.could_not_run_eval_suite_52f60a86")), "error");
    } finally {
      setRunningSuite(false);
    }
  }, [cases, notify, readyCases, refreshAll, resolvedAgentId, t]);

  const exportTrajectory = useCallback(async () => {
    if (!resolvedAgentId) return;
    const runId = selectedRun?.run_id ?? latestRun?.run_id;
    if (!runId) {
      notify(t("generated.evaluations.run_an_eval_suite_before_exporting_a_traject_c407c356"), "warning");
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
      notify(t("generated.evaluations.redacted_trajectory_export_requested_cfff82b8"), "success");
      await releaseQuery.refetch();
    } catch (error) {
      notify(evalErrorMessage(error, t("generated.evaluations.could_not_export_trajectory_ae225267")), "error");
    } finally {
      setExportingTrajectory(false);
    }
  }, [latestRun?.run_id, notify, releaseQuery, resolvedAgentId, selectedRun?.run_id, t]);

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
      notify(t("generated.evaluations.eval_case_updated_78adefa2"), "success");
      await casesQuery.refetch();
    } catch (error) {
      notify(evalErrorMessage(error, t("generated.evaluations.could_not_update_eval_case_e6b2bf8c")), "error");
    } finally {
      setPatchingCaseKey(null);
    }
  }, [casesQuery, notify, resolvedAgentId, t]);

  const runProposalAction = useCallback(async (proposalId: string, action: ImprovementProposalAction) => {
    if (!resolvedAgentId) return;
    const actionKey = `${proposalId}:${action}`;
    setProposalActionKey(actionKey);
    try {
      const raw = await requestJson<unknown>(
        proposalsPath(resolvedAgentId, `/${encodeURIComponent(proposalId)}/${action}`),
        {
          method: "POST",
          body: "{}",
        },
      );
      const proposal = parseImprovementProposal(raw);
      if (proposal) setSelectedProposalId(proposal.proposal_id);
      notify(t("generated.evaluations.proposal_action_queued_9d6ce481"), "success");
      await Promise.all([proposalsQuery.refetch(), releaseQuery.refetch(), runsQuery.refetch()]);
    } catch (error) {
      notify(evalErrorMessage(error, t("generated.evaluations.could_not_update_proposal_76adb884")), "error");
    } finally {
      setProposalActionKey(null);
    }
  }, [notify, proposalsQuery, releaseQuery, resolvedAgentId, runsQuery, t]);

  if (agents.length === 0) {
    return (
      <PageEmptyState
        icon={FlaskConical}
        title={t("generated.evaluations.no_agents_available_bbc391f6")}
        description={t("generated.evaluations.create_an_agent_before_running_phase_5_evals_09737c38")}
      />
    );
  }

  if (blockingError && errorMessage) {
    return (
      <ErrorState
        title={t("generated.evaluations.evals_unavailable_b6c7ab3e")}
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
            placeholder={t("generated.evaluations.search_eval_cases_b88be68c")}
            loading={searchState.isSearching}
            loadingLabel={t("generated.evaluations.searching_eval_cases_3e5ef736")}
            clearLabel={t("generated.evaluations.clear_search_ebb97b7a")}
          />
        </div>
        <SoftTabs
          items={[
            { id: "cases", label: t("generated.evaluations.cases_45d07d37") },
            { id: "runs", label: t("generated.evaluations.runs_a8746e85") },
            { id: "release", label: t("generated.evaluations.release_01070fe2") },
            { id: "quality", label: t("generated.evaluations.quality_645b718e") },
            { id: "proposals", label: t("generated.evaluations.proposals_faf72fc1") },
          ]}
          value={view}
          onChange={(id) => setView(id as EvaluationsView)}
          ariaLabel={t("generated.evaluations.evaluation_views_fe081899")}
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
            {t("generated.evaluations.refresh_4175f12b")}
          </button>
          <button
            type="button"
            className="button-shell button-shell--primary button-shell--sm min-w-28 gap-2 px-3"
            disabled={runningSuite || cases.length === 0}
            aria-label={runningSuite ? t("generated.evaluations.starting_e63caddb") : undefined}
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
                {t("generated.evaluations.run_suite_510d59e6")}
              </>
            )}
          </button>
          <button
            type="button"
            className="button-shell button-shell--secondary button-shell--sm min-w-36 gap-2 px-3"
            disabled={exportingTrajectory || !selectedRun}
            aria-label={exportingTrajectory ? t("generated.evaluations.exporting_895a5bd0") : undefined}
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
                {t("generated.evaluations.export_trajectory_6814890f")}
              </>
            )}
          </button>
        </div>
      </div>

      <PageMetricStrip>
        <PageMetricStripItem label={t("generated.evaluations.cases_45d07d37")} value={<MetricNumber value={cases.length} />} />
        <PageMetricStripItem label={t("generated.evaluations.ready_3337a711")} value={<MetricNumber value={readyCases.length} />} tone="success" />
        <PageMetricStripItem
          label={t("generated.evaluations.latest_score_6da61148")}
          value={formatPercent(latestScore)}
          tone={latestScore == null ? "neutral" : latestScore >= 0.8 ? "success" : "danger"}
        />
        <PageMetricStripItem
          label={t("generated.evaluations.quality_cockpit_53316e3b")}
          value={qualityCockpit?.status ?? "unknown"}
          tone={
            qualityCockpit?.status === "healthy"
              ? "success"
              : qualityCockpit?.status === "degraded" || qualityCockpit?.status === "failing"
                ? "danger"
                : "warning"
          }
        />
        <PageMetricStripItem
          label={t("generated.evaluations.release_quality_c32fd992")}
          value={releaseQuality?.status ?? "unknown"}
          tone={
            releaseQuality?.status === "passing" || releaseQuality?.status === "passed"
              ? "success"
              : releaseQuality?.status === "failing" || releaseQuality?.status === "failed"
                ? "danger"
                : "warning"
          }
        />
        <PageMetricStripItem
          label={t("generated.evaluations.proposals_faf72fc1")}
          value={<MetricNumber value={openProposals.length} />}
          tone={openProposals.length > 0 ? "warning" : "success"}
        />
      </PageMetricStrip>

      {view === "cases" ? (
        <CasesPanel
          cases={filteredCases}
          selectedCase={selectedCase}
          patchingCaseKey={patchingCaseKey}
          onSelectCase={(caseKey) => setSelectedCaseKey(caseKey)}
          onPatchStatus={patchCaseStatus}
        />
      ) : view === "runs" ? (
        <RunsPanel
          runs={runs}
          selectedRun={selectedRun}
          onSelectRun={(runId) => setSelectedRunId(runId)}
        />
      ) : view === "release" ? (
        <ReleasePanel
          releaseQuality={releaseQuality}
          selectedRun={selectedRun}
          trajectoryExport={trajectoryExport}
        />
      ) : view === "quality" ? (
        <QualityCockpitPanel cockpit={qualityCockpit} />
      ) : (
        <ProposalsPanel
          proposals={filteredProposals}
          selectedProposal={selectedProposal}
          busyAction={proposalActionKey}
          onSelectProposal={(proposalId) => setSelectedProposalId(proposalId)}
          onAction={runProposalAction}
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
        {["w-12", "w-10", "w-20", "w-24", "w-28", "w-12"].map((width, index) => (
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

function EvalSidePanel({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="w-full" aria-label={title}>
      <div className="rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel)] p-4 shadow-none">
        <header className="mb-4 min-w-0">
          {eyebrow ? (
            <p className="m-0 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
              {eyebrow}
            </p>
          ) : null}
          <h2 className="m-0 truncate text-[0.9375rem] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
            {title}
          </h2>
          {description ? (
            <p className="m-0 mt-1 text-[0.75rem] leading-5 text-[var(--text-tertiary)]">
              {description}
            </p>
          ) : null}
        </header>

        <div className="space-y-2.5">{children}</div>
      </div>
    </section>
  );
}

function CasesPanel({
  cases,
  selectedCase,
  patchingCaseKey,
  onSelectCase,
  onPatchStatus,
}: {
  cases: EvalCase[];
  selectedCase: EvalCase | null;
  patchingCaseKey: string | null;
  onSelectCase: (caseKey: string) => void;
  onPatchStatus: (caseKey: string, status: EvalCase["status"]) => void;
}) {
  const { t } = useAppI18n();
  const readyCasesCount = cases.filter((item) => item.status === "ready").length;
  const readinessTone: StatusDotTone =
    cases.length === 0 ? "neutral" : readyCasesCount > 0 ? "success" : "warning";

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.8fr)]">
      <section className="app-section min-w-0">
        <PageSectionHeader
          compact
          eyebrow={translate("generated.evaluations.eval_case_v1_a911dbe2")}
          title={t("generated.evaluations.eval_cases_a4cd41b5")}
          description={t("generated.evaluations.cases_created_from_real_runs_or_seeded_knowl_c6c20c4b")}
        />
        <PageDataTableShell className="mt-3">
          <table className="min-w-full text-left text-[0.8125rem]">
            <thead className="border-y border-[var(--divider-hair)] text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
              <tr>
                <th className="px-3 py-2 font-medium">{t("generated.evaluations.case_8ce99888")}</th>
                <th className="px-3 py-2 font-medium">{t("generated.evaluations.status_c67b6f40")}</th>
                <th className="px-3 py-2 font-medium">{t("generated.evaluations.source_82e5b165")}</th>
                <th className="px-3 py-2 font-medium">{t("generated.evaluations.updated_3ba7f5bb")}</th>
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
            title={t("generated.evaluations.no_eval_cases_487c8e40")}
            description={t("generated.evaluations.create_one_from_an_execution_detail_once_the_646d5fae")}
          />
        ) : null}
      </section>

      <aside className="min-w-0">
        <EvalSidePanel
          eyebrow={translate("generated.evaluations.eval_case_v1_a911dbe2")}
          title={t("generated.evaluations.case_readiness_79987c93")}
          description={t("generated.evaluations.readiness_gates_and_the_selected_case_live_i_a9fa6ca2")}
        >
          <PanelSignal
            tone={readinessTone}
            label={`${readyCasesCount}/${cases.length} cases ready`}
            meta={cases.length === 0 ? t("generated.evaluations.no_cases_1869f95b") : t("generated.evaluations.ready_3337a711")}
          />
          <PanelMicroHeader eyebrow={translate("generated.evaluations.case_detail_ad05e8d7")} title={t("generated.evaluations.selected_case_24229489")} />
          {selectedCase ? (
            <div className="mt-3 space-y-4">
              <div>
                <p className="m-0 text-[0.875rem] font-medium text-[var(--text-primary)]">{selectedCase.title}</p>
                <p className="m-0 mt-1 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                  {selectedCase.case_key}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3 text-[0.8125rem]">
                <DetailDatum label={t("generated.evaluations.task_bed6a478")} value={selectedCase.source_task_id ?? "-"} />
                <DetailDatum label={t("generated.evaluations.kind_4a871c86")} value={selectedCase.task_kind} />
                <DetailDatum label={t("generated.evaluations.sources_af3976f4")} value={selectedCase.expected_sources.length} />
                <DetailDatum label={t("generated.evaluations.policies_215167d8")} value={selectedCase.policy_expectations.length} />
              </div>
              <CodePreview title={t("generated.evaluations.input_9e07f63e")} value={selectedCase.input_preview || "-"} />
              <CodePreview title={t("generated.evaluations.expected_3e41d8aa")} value={selectedCase.expected_output_preview || "-"} />
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="button-shell button-shell--secondary button-shell--sm px-3"
                  disabled={patchingCaseKey === selectedCase.case_key}
                  onClick={() => onPatchStatus(selectedCase.case_key, selectedCase.status === "ready" ? "draft" : "ready")}
                >
                  {patchingCaseKey === selectedCase.case_key
                    ? t("generated.evaluations.saving_56e2bc01")
                    : selectedCase.status === "ready"
                      ? t("generated.evaluations.move_to_draft_cf6f7d4a")
                      : t("generated.evaluations.mark_ready_40d79fdd")}
                </button>
              </div>
            </div>
          ) : (
            <PageEmptyState icon={Archive} title={t("generated.evaluations.select_an_eval_case_1b0da981")} />
          )}
        </EvalSidePanel>
      </aside>
    </div>
  );
}

function RunsPanel({
  runs,
  selectedRun,
  onSelectRun,
}: {
  runs: EvalRun[];
  selectedRun: EvalRun | null;
  onSelectRun: (runId: string) => void;
}) {
  const { t } = useAppI18n();
  const latestRun = runs[0] ?? null;
  const latestRunHasFailures = (latestRun?.summary.failed ?? 0) > 0;
  const activeRun = runs.some((run) => run.status === "running" || run.status === "queued");
  const failureGroups = selectedRun?.top_failures.length ?? latestRun?.top_failures.length ?? 0;

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.8fr)]">
      <section className="app-section min-w-0">
        <PageSectionHeader
          compact
          eyebrow={translate("generated.evaluations.eval_run_v1_f87b8363")}
          title={t("generated.evaluations.eval_runs_e2f92e28")}
          description={t("generated.evaluations.offline_replay_suites_and_deterministic_smok_63946169")}
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
            title={t("generated.evaluations.no_eval_runs_08079a11")}
            description={t("generated.evaluations.run_a_deterministic_suite_after_cases_are_av_5f429526")}
          />
        ) : null}
      </section>

      <aside className="min-w-0">
        <EvalSidePanel
          eyebrow={translate("generated.evaluations.eval_run_v1_f87b8363")}
          title={t("generated.evaluations.suite_health_73a8e729")}
          description={t("generated.evaluations.run_score_case_failures_and_failure_groups_s_c75cd7a6")}
        >
          <PanelSignal
            tone={activeRun ? "info" : latestRun && !latestRunHasFailures ? "success" : "warning"}
            label={latestRun ? `Latest suite ${latestRun.status}` : t("generated.evaluations.no_deterministic_suite_yet_66af87bc")}
            meta={latestRun ? formatRelativeTime(latestRun.completed_at ?? latestRun.created_at ?? latestRun.started_at) : t("generated.evaluations.pending_aaa3cef7")}
          />
          <PanelSignal
            tone={failureGroups > 0 ? "warning" : "success"}
            label={`${failureGroups} top failure groups`}
            meta={failureGroups > 0 ? t("generated.evaluations.review_29bacef9") : t("generated.evaluations.clear_c95a38e2")}
          />
          <PanelMicroHeader eyebrow={translate("generated.evaluations.failure_drilldown_3301bd6c")} title={t("generated.evaluations.run_detail_5d1e8070")} />
          {selectedRun ? (
            <div className="mt-3 space-y-4">
              <div className="grid grid-cols-3 gap-3">
                <DetailDatum label={t("generated.evaluations.score_76f831dc")} value={formatPercent(selectedRun.summary.score)} />
                <DetailDatum label={t("generated.evaluations.passed_85248b88")} value={selectedRun.summary.passed} />
                <DetailDatum label={t("generated.evaluations.failed_633787d7")} value={selectedRun.summary.failed} />
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
            <PageEmptyState icon={GitCompareArrows} title={t("generated.evaluations.select_an_eval_run_bc36e252")} />
          )}
        </EvalSidePanel>
      </aside>
    </div>
  );
}

function ProposalsPanel({
  proposals,
  selectedProposal,
  busyAction,
  onSelectProposal,
  onAction,
}: {
  proposals: ImprovementProposal[];
  selectedProposal: ImprovementProposal | null;
  busyAction: string | null;
  onSelectProposal: (proposalId: string) => void;
  onAction: (proposalId: string, action: ImprovementProposalAction) => void;
}) {
  const { t } = useAppI18n();
  const activeCount = proposals.filter((item) =>
    ["draft", "pending_review", "approved", "validating"].includes(item.status),
  ).length;
  const blockedCount = proposals.filter((item) =>
    ["failed", "rejected"].includes(item.status),
  ).length;

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.8fr)]">
      <section className="app-section min-w-0">
        <PageSectionHeader
          compact
          eyebrow={translate("generated.evaluations.improvement_proposal_v1_2bb34a73")}
          title={t("generated.evaluations.proposal_queue_40f418ba")}
          description={t("generated.evaluations.approval_first_changes_from_failed_runs_eval_59140030")}
        />
        <div className="mt-3 divide-y divide-[var(--divider-hair)]">
          {proposals.map((proposal) => (
            <button
              key={proposal.proposal_id}
              type="button"
              onClick={() => onSelectProposal(proposal.proposal_id)}
              className={cn(
                "grid w-full grid-cols-[1fr_auto] gap-3 px-3 py-3 text-left transition-colors hover:bg-[var(--hover-tint)]",
                selectedProposal?.proposal_id === proposal.proposal_id && "bg-[var(--panel-soft)]",
              )}
            >
              <span className="min-w-0">
                <span className="block truncate text-[0.875rem] font-medium text-[var(--text-primary)]">
                  {proposal.summary}
                </span>
                <span className="mt-1 flex min-w-0 flex-wrap items-center gap-1.5 text-[0.72rem] text-[var(--text-tertiary)]">
                  <span className="truncate font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                    {proposal.proposal_id}
                  </span>
                  <span>{proposal.proposal_type}</span>
                  <span>{proposal.source_kind}</span>
                </span>
              </span>
              <span className="flex flex-col items-end gap-1">
                <StatusLabel status={proposal.status} />
                <span className="text-[0.75rem] text-[var(--text-tertiary)]">
                  {formatRelativeTime(proposal.updated_at ?? proposal.created_at)}
                </span>
              </span>
            </button>
          ))}
        </div>
        {proposals.length === 0 ? (
          <PageEmptyState
            icon={Archive}
            title={t("generated.evaluations.no_proposals_b53da670")}
            description={t("generated.evaluations.failed_evals_and_corrections_will_appear_her_7d87a38e")}
          />
        ) : null}
      </section>

      <aside className="min-w-0">
        <EvalSidePanel
          eyebrow={translate("generated.evaluations.improvement_proposal_v1_2bb34a73")}
          title={t("generated.evaluations.proposal_review_fec2ddd7")}
          description={t("generated.evaluations.validate_apply_or_roll_back_approved_operati_5b37b9ab")}
        >
          <PanelSignal
            tone={activeCount > 0 ? "warning" : "success"}
            label={`${activeCount} open proposals`}
            meta={activeCount > 0 ? t("generated.evaluations.review_29bacef9") : t("generated.evaluations.clear_c95a38e2")}
          />
          <PanelSignal
            tone={blockedCount > 0 ? "danger" : "success"}
            label={`${blockedCount} blocked proposals`}
            meta={blockedCount > 0 ? t("generated.evaluations.needs_decision_d1493830") : t("generated.evaluations.clear_c95a38e2")}
          />
          <PanelMicroHeader eyebrow={translate("generated.evaluations.proposal_detail_a58414e0")} title={t("generated.evaluations.selected_proposal_8842118b")} />
          {selectedProposal ? (
            <div className="mt-3 space-y-4">
              <div>
                <p className="m-0 text-[0.875rem] font-medium text-[var(--text-primary)]">
                  {selectedProposal.summary}
                </p>
                <p className="m-0 mt-1 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                  {selectedProposal.proposal_id}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <DetailDatum label={t("generated.evaluations.type_d6e3764e")} value={selectedProposal.proposal_type} />
                <DetailDatum label={t("generated.evaluations.risk_d2badad1")} value={selectedProposal.risk_class} />
                <DetailDatum label={t("generated.evaluations.source_82e5b165")} value={selectedProposal.source_kind} />
                <DetailDatum label={t("generated.evaluations.rungraph_cd439b16")} value={selectedProposal.run_graph_node_ids.length} />
              </div>
              <CodePreview title={t("generated.evaluations.diff_8f2139f5")} value={formatProposalJson(selectedProposal.diff_preview)} />
              <CodePreview title={t("generated.evaluations.validation_c81a896a")} value={formatProposalJson(selectedProposal.validation_plan)} />
              <CodePreview title={t("generated.evaluations.rollback_aa498d17")} value={formatProposalJson(selectedProposal.rollback_plan)} />
              <ProposalActions
                proposal={selectedProposal}
                busyAction={busyAction}
                onAction={onAction}
              />
            </div>
          ) : (
            <PageEmptyState icon={Archive} title={t("generated.evaluations.select_a_proposal_c7b9c369")} />
          )}
        </EvalSidePanel>
      </aside>
    </div>
  );
}

function ReleasePanel({
  releaseQuality,
  selectedRun,
  trajectoryExport,
}: {
  releaseQuality: ReleaseQuality | null;
  selectedRun: EvalRun | null;
  trajectoryExport: TrajectoryExport | null;
}) {
  const { t } = useAppI18n();
  const exportPayload = trajectoryExport ?? releaseQuality?.latest_trajectory_export ?? null;
  const releaseStatus = releaseQuality?.status ?? "unknown";
  const releaseIsPassing = releaseStatus === "passing" || releaseStatus === "passed";
  const exportIsReady = Boolean(exportPayload?.redaction_applied);
  const runGraphGate = getRunGraphReleaseGate(releaseQuality);
  const runGraphWarnings = getRunGraphReleaseWarnings(releaseQuality);

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.8fr)]">
      <section className="app-section min-w-0">
        <PageSectionHeader
          compact
          eyebrow={translate("generated.evaluations.release_quality_v1_fa3e6fe9")}
          title={t("generated.evaluations.release_gates_5348da7e")}
          description={t("generated.evaluations.release_quality_claims_require_deterministic_80707b71")}
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
            title={t("generated.evaluations.no_release_quality_status_c442d815")}
            description={t("generated.evaluations.the_backend_has_not_published_release_qualit_5c8803c3")}
          />
        ) : null}
      </section>

      <aside className="min-w-0">
        <EvalSidePanel
          title={t("generated.evaluations.release_readiness_374c4b7a")}
          eyebrow={translate("generated.evaluations.release_quality_v1_fa3e6fe9")}
          description={t("generated.evaluations.release_gates_export_safety_and_failure_evid_eec3fb39")}
        >
          <PanelSignal
            tone={releaseQuality ? (releaseIsPassing ? "success" : "warning") : "neutral"}
            label={releaseQuality ? `Release quality ${releaseStatus}` : t("generated.evaluations.release_quality_unpublished_90a7ad94")}
            meta={releaseQuality ? `${releaseQuality.gates.length} gates` : t("generated.evaluations.pending_aaa3cef7")}
          />
          <PanelSignal
            tone={runGraphGate ? statusTone(runGraphGate.status) : "neutral"}
            label={runGraphGate ? `RunGraph ${runGraphGate.status}` : t("generated.evaluations.rungraph_gate_unpublished_7128c1b1")}
            meta={runGraphWarnings.length > 0 ? `${runGraphWarnings.length} warnings` : t("generated.evaluations.clear_c95a38e2")}
          />
          <PanelSignal
            tone={exportPayload ? (exportIsReady ? "success" : "danger") : "warning"}
            label={exportIsReady ? t("generated.evaluations.trajectory_export_redacted_de9126c2") : t("generated.evaluations.trajectory_export_missing_06c9f5ac")}
            meta={exportPayload?.format ?? "jsonl"}
          />
          {runGraphWarnings.length > 0 ? (
            <InlineAlert tone="warning">
              {runGraphWarnings[0]}
            </InlineAlert>
          ) : null}
          <ReleaseBlockerList releaseQuality={releaseQuality} />
          <PanelMicroHeader eyebrow={translate("generated.evaluations.trajectory_export_v1_8012c341")} title={t("generated.evaluations.trajectory_export_7f06822f")} />
          <div className="mt-3 space-y-4">
            {exportPayload ? (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <DetailDatum label={t("generated.evaluations.status_c67b6f40")} value={<StatusLabel status={exportPayload.status} />} />
                  <DetailDatum label={t("generated.evaluations.lines_ee22c113")} value={exportPayload.line_count} />
                  <DetailDatum label={t("generated.evaluations.redactions_1ce88ce9")} value={exportPayload.redactions?.count ?? 0} />
                  <DetailDatum label={t("generated.evaluations.replay_3171283d")} value={exportPayload.replay_mode} />
                </div>
                <InlineAlert tone={exportPayload.redaction_applied ? "success" : "danger"}>
                  {exportPayload.redaction_applied
                    ? t("generated.evaluations.export_is_redacted_and_provider_calls_are_di_12a9a370")
                    : t("generated.evaluations.export_is_not_marked_redacted_do_not_use_for_2d3e8674")}
                </InlineAlert>
                {exportPayload.download_url ? (
                  <a href={exportPayload.download_url} className="button-shell button-shell--secondary button-shell--sm inline-flex px-3">
                    {t("generated.evaluations.download_jsonl_819119f6")}
                  </a>
                ) : null}
              </>
            ) : (
              <PageEmptyState
                icon={Download}
                title={t("generated.evaluations.no_trajectory_export_3c99061a")}
                description={selectedRun ? t("generated.evaluations.export_the_selected_run_to_produce_a_redacte_87594113") : t("generated.evaluations.run_a_suite_before_exporting_d9e9ced2")}
              />
            )}
            <FailureList failures={releaseQuality?.top_failures ?? []} />
          </div>
        </EvalSidePanel>
      </aside>
    </div>
  );
}

function ReleaseBlockerList({ releaseQuality }: { releaseQuality: ReleaseQuality | null }) {
  const { t } = useAppI18n();
  const blockers = (releaseQuality?.gates ?? []).filter((gate) => gate.status !== "passed" && gate.status !== "passing");
  if (!releaseQuality) {
    return null;
  }
  if (blockers.length === 0) {
    return (
      <InlineAlert tone="success">
        {t("generated.evaluations.no_critical_release_blockers_c8b61221")}
      </InlineAlert>
    );
  }
  return (
    <div className="space-y-2">
      <PanelMicroHeader eyebrow={translate("generated.evaluations.release_blocker_v1_dd299a0f")} title={t("generated.evaluations.release_blockers_210dbf1d")} />
      <div className="divide-y divide-[var(--divider-hair)] rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)]">
        {blockers.map((gate) => (
          <div key={gate.id} className="grid grid-cols-[1fr_auto] gap-3 px-3 py-2.5">
            <div className="min-w-0">
              <p className="m-0 truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
                {gate.title}
              </p>
              <p className="m-0 mt-1 text-[0.72rem] leading-5 text-[var(--text-tertiary)]">
                {gate.summary || t("generated.evaluations.gate_is_not_passing_b60a50ea")}
              </p>
            </div>
            <StatusLabel status={gate.status} />
          </div>
        ))}
      </div>
    </div>
  );
}

function QualityCockpitPanel({ cockpit }: { cockpit: QualityCockpit | null }) {
  const { t } = useAppI18n();
  if (!cockpit) {
    return (
      <PageEmptyState
        icon={TriangleAlert}
        title={t("generated.evaluations.no_quality_cockpit_7a7e44ad")}
        description={t("generated.evaluations.the_backend_has_not_published_quality_cockpi_c36b34e2")}
      />
    );
  }
  const groups = cockpit.groups;
  const costRows = groups.flatMap((group) =>
    group.items.map((item) => ({
      id: `${item.entity_type}:${item.entity_id}`,
      label: item.label,
      type: item.entity_type,
      cost: item.metrics.cost_usd ?? 0,
      quality: item.metrics.success_rate ?? item.metrics.eval_score ?? null,
      failures: item.failures.length,
    })),
  );
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(360px,0.8fr)]">
      <section className="app-section min-w-0">
        <PageSectionHeader
          compact
          eyebrow={translate("generated.evaluations.quality_cockpit_v1_89fa4b17")}
          title={t("generated.evaluations.quality_cockpit_53316e3b")}
          description={t("generated.evaluations.agent_squad_tool_skill_model_and_route_quali_1dfa39fa")}
          meta={<StatusLabel status={cockpit.status} />}
        />
        <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {groups.map((group) => (
            <div
              key={group.entity_type}
              className="rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] p-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="m-0 text-[0.875rem] font-medium text-[var(--text-primary)]">{group.label}</p>
                  <p className="m-0 mt-1 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                    {group.entity_type}
                  </p>
                </div>
                <StatusLabel status={group.status} />
              </div>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <DetailDatum label={t("generated.evaluations.success_5a1c83cc")} value={formatPercent(group.metrics.success_rate)} />
                <DetailDatum label={t("generated.evaluations.failures_77d29b6e")} value={group.metrics.failure_count} />
                <DetailDatum label={t("generated.evaluations.runs_a8746e85")} value={group.metrics.run_count} />
                <DetailDatum label={t("generated.evaluations.timeout_d6e787af")} value={formatPercent(group.metrics.timeout_rate)} />
              </div>
            </div>
          ))}
        </div>
        {groups.length === 0 ? (
          <PageEmptyState
            icon={Archive}
            title={t("generated.evaluations.no_quality_groups_53b1ace5")}
            description={t("generated.evaluations.quality_evidence_exists_only_after_evals_rou_e6013f76")}
          />
        ) : null}
      </section>

      <aside className="min-w-0">
        <EvalSidePanel
          eyebrow={translate("generated.evaluations.quality_cockpit_v1_89fa4b17")}
          title={t("generated.evaluations.failure_and_trend_evidence_37aa5b11")}
          description={t("generated.evaluations.top_failures_cost_vs_quality_route_history_a_9ad6e154")}
        >
          <PanelSignal
            tone={cockpit.top_failures.length > 0 ? "warning" : "success"}
            label={`${cockpit.top_failures.length} top failures`}
            meta={cockpit.top_failures.length > 0 ? t("generated.evaluations.review_29bacef9") : t("generated.evaluations.clear_c95a38e2")}
          />
          <PanelSignal
            tone={cockpit.release_blockers.length > 0 ? "danger" : "success"}
            label={`${cockpit.release_blockers.length} release blockers`}
            meta={cockpit.release_blockers.length > 0 ? t("generated.evaluations.blocked_921d4615") : t("generated.evaluations.clear_c95a38e2")}
          />
          <PanelMicroHeader eyebrow={translate("generated.evaluations.top_failures_172e528f")} title={t("generated.evaluations.failures_77d29b6e")} />
          <QualityFailureCards failures={cockpit.top_failures} />
          <PanelMicroHeader eyebrow={translate("generated.evaluations.cost_vs_quality_48a1314a")} title={t("generated.evaluations.cost_vs_quality_43d375b1")} />
          <div className="space-y-2">
            {costRows.slice(0, 6).map((row) => (
              <div key={row.id} className="grid grid-cols-[1fr_auto] gap-3 rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] px-3 py-2">
                <div className="min-w-0">
                  <p className="m-0 truncate text-[0.8125rem] text-[var(--text-primary)]">{row.label}</p>
                  <p className="m-0 mt-1 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">{row.type}</p>
                </div>
                <span className="text-right font-mono text-[0.6875rem] text-[var(--text-secondary)]">
                  ${row.cost.toFixed(4)} · {formatPercent(row.quality)}
                </span>
              </div>
            ))}
            {costRows.length === 0 ? <PageEmptyState icon={Archive} title={t("generated.evaluations.no_cost_rows_e9c7a86c")} /> : null}
          </div>
          <PanelMicroHeader eyebrow={translate("generated.evaluations.route_outcome_v1_15749716")} title={t("generated.evaluations.route_quality_trend_b37ed7a4")} />
          <div className="space-y-2">
            {cockpit.route_quality_history.slice(0, 6).map((route) => (
              <div key={route.route_source} className="grid grid-cols-[1fr_auto] gap-3 rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] px-3 py-2">
                <div className="min-w-0">
                  <p className="m-0 text-[0.8125rem] text-[var(--text-primary)]">{route.route_source}</p>
                  <p className="m-0 mt-1 text-[0.6875rem] text-[var(--text-tertiary)]">
                    {route.outcome_count} {translate("generated.evaluations.outcomes_timeout_e0215141")}{formatPercent(route.timeout_rate)}
                  </p>
                </div>
                <span className="font-mono text-[0.6875rem] text-[var(--text-secondary)]">
                  {formatPercent(route.success_rate)}
                </span>
              </div>
            ))}
            {cockpit.route_quality_history.length === 0 ? (
              <PageEmptyState icon={Archive} title={t("generated.evaluations.no_route_quality_history_9f2a3dad")} />
            ) : null}
          </div>
        </EvalSidePanel>
      </aside>
    </div>
  );
}

function QualityFailureCards({ failures }: { failures: QualityCockpitFailure[] }) {
  const { t } = useAppI18n();
  if (failures.length === 0) {
    return <PageEmptyState icon={Archive} title={t("generated.evaluations.no_quality_failures_699d0dfb")} />;
  }
  return (
    <div className="space-y-2">
      {failures.slice(0, 6).map((failure) => (
        <div key={failure.failure_id} className="rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] px-3 py-2">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="m-0 truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">{failure.title}</p>
              <p className="m-0 mt-1 text-[0.72rem] leading-5 text-[var(--text-tertiary)]">{failure.summary}</p>
            </div>
            <StatusLabel status={failure.status} />
          </div>
          <p className="m-0 mt-1 font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
            {failure.failure_id} · {failure.risk_class} {translate("generated.evaluations.nodes_92d17592")}{failure.run_graph_node_ids.length}
          </p>
        </div>
      ))}
    </div>
  );
}

function ProposalActions({
  proposal,
  busyAction,
  onAction,
}: {
  proposal: ImprovementProposal;
  busyAction: string | null;
  onAction: (proposalId: string, action: ImprovementProposalAction) => void;
}) {
  const { t } = useAppI18n();
  const actions: Array<{
    action: ImprovementProposalAction;
    label: string;
    icon: typeof CheckCircle2;
    enabled: boolean;
  }> = [
    {
      action: "approve",
      label: t("generated.evaluations.approve_22e2b5a9"),
      icon: CheckCircle2,
      enabled: proposal.status === "pending_review" || proposal.status === "draft",
    },
    {
      action: "reject",
      label: t("generated.evaluations.reject_10c5f567"),
      icon: XCircle,
      enabled: proposal.status === "pending_review" || proposal.status === "draft",
    },
    {
      action: "validate",
      label: t("generated.evaluations.validate_bd735a4f"),
      icon: ShieldCheck,
      enabled: proposal.status === "approved",
    },
    {
      action: "apply",
      label: t("generated.evaluations.apply_56548d17"),
      icon: CheckCircle2,
      enabled: proposal.status === "approved" && proposalValidationPassed(proposal) && proposalHasRollbackPlan(proposal),
    },
    {
      action: "rollback",
      label: t("generated.evaluations.rollback_aa498d17"),
      icon: RotateCcw,
      enabled: proposal.status === "applied",
    },
  ];

  return (
    <div className="flex flex-wrap gap-2">
      {actions.map(({ action, label, icon: Icon, enabled }) => {
        const actionKey = `${proposal.proposal_id}:${action}`;
        const busy = busyAction === actionKey;
        return (
          <button
            key={action}
            type="button"
            className="button-shell button-shell--secondary button-shell--sm gap-2 px-3"
            disabled={!enabled || busyAction !== null}
            aria-label={busy ? t("generated.evaluations.submitting_1a1c6927") : label}
            aria-busy={busy || undefined}
            title={label}
            onClick={() => onAction(proposal.proposal_id, action)}
          >
            {busy ? <InlineSpinner className="h-3.5 w-3.5" /> : <Icon className="h-3.5 w-3.5" />}
            {label}
          </button>
        );
      })}
    </div>
  );
}

function proposalValidationPassed(proposal: ImprovementProposal) {
  const result = proposal.validation_result ?? {};
  const status = typeof result.status === "string" ? result.status.toLowerCase() : "";
  return status === "passed" || status === "pass" || result.passed === true || result.ok === true;
}

function proposalHasRollbackPlan(proposal: ImprovementProposal) {
  const plan = proposal.rollback_plan;
  return Boolean(plan && typeof plan === "object" && !Array.isArray(plan) && Object.keys(plan).length > 0);
}

function PanelSignal({
  tone,
  label,
  meta,
}: {
  tone: StatusDotTone;
  label: string;
  meta?: string;
}) {
  return (
    <div className="grid grid-cols-[auto_1fr_auto] items-center gap-2.5 rounded-[var(--radius-panel-sm)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 py-2.5">
      <StatusDot tone={tone} />
      <span className="min-w-0 truncate text-[0.8125rem] text-[var(--text-primary)]">{label}</span>
      {meta ? (
        <span className="truncate font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
          {meta}
        </span>
      ) : null}
    </div>
  );
}

function PanelMicroHeader({
  eyebrow,
  title,
}: {
  eyebrow: string;
  title: string;
}) {
  return (
    <div>
      <p className="m-0 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
        {eyebrow}
      </p>
      <p className="m-0 mt-1 text-[0.875rem] font-medium tracking-[var(--tracking-tight)] text-[var(--text-primary)]">
        {title}
      </p>
    </div>
  );
}

function DetailDatum({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0 border-l border-[var(--border-subtle)] py-1 pl-3">
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
  const { t } = useAppI18n();
  if (failures.length === 0) {
    return (
      <InlineAlert tone="success">
        {t("generated.evaluations.no_top_failures_reported_65357b16")}
      </InlineAlert>
    );
  }
  return (
    <div className="space-y-2">
      <p className="m-0 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
        {t("generated.evaluations.top_failures_3fd291c6")}
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
