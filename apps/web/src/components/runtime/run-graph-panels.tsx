"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { translate } from "@/lib/i18n";
import {
  AlertTriangle,
  GitBranch,
  GitPullRequestArrow,
  Route,
  PlayCircle,
} from "lucide-react";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import {
  getRunGraphReleaseGate,
  getRunGraphReleaseWarnings,
  type ReleaseQuality,
} from "@/lib/contracts/evals";
import type { ChildRunRecord, ContextGovernancePayload } from "@/lib/contracts/phase3-runtime";
import {
  parseHandoffEvent,
  parseRouteExplanation,
  type HandoffEvent,
  type RouteExplanation,
} from "@/lib/contracts/handoffs";
import type {
  ReplayAvailability,
  RunGraphNode,
  RunGraphSnapshot,
  RunReplayPlan,
} from "@/lib/contracts/run-graph";
import { getSemanticIconStyle, getSemanticStyle } from "@/lib/theme-semantic";
import { getRunGraphNodeVisual } from "@/lib/runtime-visual-taxonomy";
import { cn, formatDateTime, formatDuration } from "@/lib/utils";

type Phase2PanelVariant = "panel" | "inline";

type RunGraphPanelsProps = {
  graph: RunGraphSnapshot | null;
  replay: RunReplayPlan | null;
  releaseQuality?: ReleaseQuality | null;
  runtimeHref?: string;
  variant?: Phase2PanelVariant;
};

function stateTone(status: string | null | undefined): StatusDotTone {
  if (status === "completed") return "success";
  if (status === "running") return "info";
  if (status === "retrying") return "retry";
  if (status === "queued" || status === "stalled" || status === "degraded") return "warning";
  if (status === "failed") return "danger";
  return "neutral";
}

function availabilityTone(availability: ReplayAvailability | null | undefined): StatusDotTone {
  if (availability === "available") return "success";
  if (availability === "degraded") return "warning";
  return "neutral";
}

function getNodeDepth(node: RunGraphNode, byId: Map<string, RunGraphNode>) {
  let depth = 0;
  let parentId = node.parent_id ?? null;
  const seen = new Set<string>([node.id]);
  while (parentId && byId.has(parentId) && !seen.has(parentId)) {
    depth += 1;
    seen.add(parentId);
    parentId = byId.get(parentId)?.parent_id ?? null;
  }
  return Math.min(depth, 6);
}

function sortNodes(nodes: RunGraphNode[]) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  return [...nodes].sort((left, right) => {
    const leftDepth = getNodeDepth(left, byId);
    const rightDepth = getNodeDepth(right, byId);
    if (leftDepth !== rightDepth) return leftDepth - rightDepth;
    return left.id.localeCompare(right.id);
  });
}

function localRunGraphWarnings(graph: RunGraphSnapshot | null) {
  if (!graph || graph.status !== "completed") return [];
  const nodeTypes = new Set(graph.nodes.map((node) => node.type));
  const warnings: string[] = [];
  if (!nodeTypes.has("model_call")) warnings.push("Missing model_call node.");
  if (![...nodeTypes].some((type) => type.startsWith("tool_"))) warnings.push("Missing tool request/result nodes.");
  if (!nodeTypes.has("policy_gate")) warnings.push("Missing policy_gate node.");
  return warnings;
}

function PanelShell({
  title,
  eyebrow,
  tone,
  action,
  children,
  variant = "panel",
}: {
  title: string;
  eyebrow: string;
  tone: StatusDotTone;
  action?: ReactNode;
  children: ReactNode;
  variant?: Phase2PanelVariant;
}) {
  return (
    <section
      className={cn(
        "border border-[var(--border-subtle)] bg-[var(--panel-soft)]",
        variant === "panel" ? "rounded-[var(--radius-panel-sm)] p-4" : "rounded-[var(--radius-panel-sm)] p-3",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="m-0 font-mono text-[0.625rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
            {eyebrow}
          </p>
          <h3 className="m-0 mt-1 flex min-w-0 items-center gap-2 text-[0.875rem] font-medium text-[var(--text-primary)]">
            <StatusDot tone={tone} />
            <span className="truncate">{title}</span>
          </h3>
        </div>
        {action}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex min-h-[120px] flex-col items-center justify-center gap-2 py-5 text-center">
      <AlertTriangle className="h-4 w-4 text-[var(--text-quaternary)]" strokeWidth={1.75} />
      <p className="m-0 text-[0.8125rem] font-medium text-[var(--text-secondary)]">{title}</p>
      <p className="m-0 max-w-md text-[0.75rem] leading-5 text-[var(--text-tertiary)]">
        {description}
      </p>
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}

function MetricLine({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="break-words font-mono text-[0.625rem] uppercase leading-4 tracking-[var(--tracking-mono)] text-[var(--text-quaternary)]">
        {label}
      </dt>
      <dd className="m-0 mt-1 break-words text-[0.8125rem] leading-5 text-[var(--text-primary)]">{value}</dd>
    </div>
  );
}

export function RunGraphSummaryPanel({
  graph,
  replay,
  releaseQuality,
  runtimeHref,
  variant = "panel",
}: RunGraphPanelsProps) {
  const replayPlan = replay ?? graph?.replay ?? null;
  const releaseGate = getRunGraphReleaseGate(releaseQuality);
  const releaseWarnings = getRunGraphReleaseWarnings(releaseQuality);
  const completenessWarnings = releaseWarnings.length > 0 ? releaseWarnings : localRunGraphWarnings(graph);
  const action = runtimeHref ? (
    <Link href={runtimeHref} className="button-pill inline-flex">
      {translate("generated.runtime.runtime_a166f9f1")}</Link>
  ) : null;

  if (!graph) {
    return (
      <PanelShell title={translate("generated.runtime.rungraph_unavailable_73aad30a")} eyebrow={translate("generated.runtime.run_graph_v1_959dc7f6")} tone="neutral" action={action} variant={variant}>
        <EmptyState
          title={translate("generated.runtime.no_rungraph_snapshot_0185522d")}
          description={translate("generated.runtime.this_task_has_not_published_a_run_graph_v1_p_ca6c7198")}
        />
      </PanelShell>
    );
  }

  const redactionCount = graph.redactions?.count ?? 0;
  const toolCount = graph.nodes.filter((node) => node.type.startsWith("tool_")).length;
  const policyCount = graph.nodes.filter((node) => node.type === "policy_gate").length;

  return (
    <PanelShell
      title={graph.summary || "RunGraph snapshot"}
      eyebrow={translate("generated.runtime.run_graph_v1_959dc7f6")}
      tone={stateTone(graph.status)}
      action={action}
      variant={variant}
    >
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricLine label={translate("generated.runtime.state_883bd1af")} value={graph.status} />
        <MetricLine label={translate("generated.runtime.nodes_3eedde7b")} value={String(graph.nodes.length)} />
        <MetricLine label={translate("generated.runtime.policy_f02fb051")} value={String(policyCount)} />
        <MetricLine label={translate("generated.runtime.tools_568d94f9")} value={String(toolCount)} />
        <MetricLine label={translate("generated.runtime.replay_389974c3")} value={replayPlan?.availability ?? "unavailable"} />
        <MetricLine label={translate("generated.runtime.redactions_b0f7d55f")} value={String(redactionCount)} />
        <MetricLine label={translate("generated.runtime.completeness_5a9b4552")} value={releaseGate?.status ?? (completenessWarnings.length > 0 ? "warning" : "clear")} />
        <MetricLine label={translate("generated.runtime.started_242d0279")} value={formatDateTime(graph.started_at)} />
        <MetricLine label={translate("generated.runtime.completed_9779880c")} value={formatDateTime(graph.completed_at)} />
      </dl>
      {completenessWarnings.length > 0 ? (
        <div className="mt-3 rounded-[var(--radius-panel-sm)] border border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)] px-3 py-2 text-[0.75rem] text-[var(--tone-warning-text)]">
          {translate("generated.runtime.rungraph_completeness_b6e2a52c")} {completenessWarnings[0]}
        </div>
      ) : null}
      {graph.error ? (
        <div className="mt-3 rounded-[var(--radius-panel-sm)] border border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] px-3 py-2 text-[0.75rem] text-[var(--tone-danger-text)]">
          {graph.error.message}
        </div>
      ) : null}
    </PanelShell>
  );
}

export function RunGraphViewer({
  graph,
  variant = "panel",
}: {
  graph: RunGraphSnapshot | null;
  variant?: Phase2PanelVariant;
}) {
  if (!graph) {
    return (
      <PanelShell title={translate("generated.runtime.graph_viewer_unavailable_0769b3a7")} eyebrow={translate("generated.runtime.nodes_8ab776e1")} tone="neutral" variant={variant}>
        <EmptyState
          title={translate("generated.runtime.no_node_tree_dd61680f")}
          description={translate("generated.runtime.the_viewer_is_waiting_for_backend_rungraph_n_734b644c")}
        />
      </PanelShell>
    );
  }

  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  const nodes = sortNodes(graph.nodes);

  return (
    <PanelShell title={translate("generated.runtime.run_tree_4494db26")} eyebrow={`${nodes.length} nodes`} tone={stateTone(graph.status)} variant={variant}>
      <div className="divide-y divide-[var(--divider-hair)]">
        {nodes.map((node) => {
          const visual = getRunGraphNodeVisual(node.type);
          const Icon = visual.icon;
          const depth = getNodeDepth(node, byId);
          return (
            <article
              key={node.id}
              className="grid grid-cols-[auto_1fr_auto] items-start gap-3 py-2.5"
              data-node-visual={visual.key}
            >
              <div
                className="mt-0.5 flex items-center gap-2"
                style={{ paddingLeft: `${depth * 14}px` }}
              >
                <span
                  className="inline-flex h-6 w-6 items-center justify-center rounded-md border"
                  style={getSemanticIconStyle(visual.tone)}
                  aria-label={`${visual.label} node`}
                  title={visual.label}
                >
                  <Icon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                </span>
                <StatusDot tone={stateTone(node.status)} />
              </div>
              <div className="min-w-0">
                <p className="m-0 truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
                  {node.label}
                </p>
                <div className="m-0 mt-1 flex min-w-0 flex-wrap items-center gap-1.5 text-[0.72rem] text-[var(--text-tertiary)]">
                  <span
                    className="inline-flex rounded-md border px-1.5 py-0.5 font-mono text-[0.625rem] uppercase tracking-[0.08em]"
                    style={getSemanticStyle(visual.tone)}
                  >
                    {visual.label}
                  </span>
                  {node.summary ? <span className="min-w-0 truncate">{node.summary}</span> : null}
                </div>
              </div>
              <span className="whitespace-nowrap font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                {formatDuration(node.duration_ms ?? null)}
              </span>
            </article>
          );
        })}
      </div>
    </PanelShell>
  );
}

export function RunReplayPanel({
  replay,
  variant = "panel",
}: {
  replay: RunReplayPlan | null;
  variant?: Phase2PanelVariant;
}) {
  if (!replay) {
    return (
      <PanelShell title={translate("generated.runtime.replay_unavailable_f8d89875")} eyebrow={translate("generated.runtime.run_replay_v1_51536198")} tone="neutral" variant={variant}>
        <EmptyState
          title={translate("generated.runtime.no_offline_replay_e8266d09")}
          description={translate("generated.runtime.the_replay_contract_is_not_present_for_this__233d50ab")}
        />
      </PanelShell>
    );
  }

  return (
    <PanelShell
      title={`Offline replay ${replay.availability}`}
      eyebrow={translate("generated.runtime.run_replay_v1_51536198")}
      tone={availabilityTone(replay.availability)}
      variant={variant}
      action={<PlayCircle className="h-4 w-4 text-[var(--text-tertiary)]" strokeWidth={1.75} />}
    >
      {replay.missing_dependencies.length > 0 ? (
        <div className="mb-3 rounded-[var(--radius-panel-sm)] border border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)] px-3 py-2 text-[0.75rem] text-[var(--tone-warning-text)]">
          {translate("generated.runtime.missing_4fc6280c")}{replay.missing_dependencies.join(", ")}
        </div>
      ) : null}
      <div className="divide-y divide-[var(--divider-hair)]">
        {replay.steps.map((step, index) => {
          const visual = getRunGraphNodeVisual(step.type);
          return (
            <article
              key={`${step.node_id}-${index}`}
              className="grid grid-cols-[auto_1fr_auto] items-start gap-3 py-2.5"
              data-replay-visual={visual.key}
            >
              <span
                className="inline-flex h-6 min-w-6 items-center justify-center rounded-md border px-1.5 font-mono text-[0.625rem]"
                style={getSemanticIconStyle(visual.tone)}
                title={visual.label}
              >
                {(index + 1).toString().padStart(2, "0")}
              </span>
              <div className="min-w-0">
                <p className="m-0 truncate text-[0.8125rem] text-[var(--text-primary)]">{step.label}</p>
                <div className="m-0 mt-1 flex min-w-0 flex-wrap items-center gap-1.5 text-[0.72rem] text-[var(--text-tertiary)]">
                  <span
                    className="inline-flex rounded-md border px-1.5 py-0.5 font-mono text-[0.625rem] uppercase tracking-[0.08em]"
                    style={getSemanticStyle(visual.tone)}
                  >
                    {visual.label}
                  </span>
                  {step.notes ? <span className="min-w-0 truncate">{step.notes}</span> : null}
                </div>
              </div>
              <span className="inline-flex items-center gap-1.5 font-mono text-[0.6875rem] text-[var(--text-tertiary)]">
                <StatusDot tone={stateTone(step.status)} />
                {step.redacted ? "redacted" : step.status}
              </span>
            </article>
          );
        })}
      </div>
    </PanelShell>
  );
}

export function RouteExplanationPanel({
  graph,
  variant = "panel",
}: {
  graph: RunGraphSnapshot | null;
  variant?: Phase2PanelVariant;
}) {
  const routes = extractRouteExplanations(graph);
  if (!routes.length) {
    return (
      <PanelShell title={translate("generated.runtime.route_explanation_unavailable_6e152016")} eyebrow={translate("generated.runtime.route_explanation_v1_b7e37ca1")} tone="neutral" variant={variant}>
        <EmptyState
          title={translate("generated.runtime.no_route_evidence_34e1c7c4")}
          description={translate("generated.runtime.the_backend_has_not_published_route_explanat_9e329e30")}
        />
      </PanelShell>
    );
  }
  const latest = routes[0]!;
  return (
    <PanelShell
      title={latest.clarification_required ? "Clarification required" : "Route explanation"}
      eyebrow={translate("generated.runtime.route_explanation_v1_b7e37ca1")}
      tone={latest.clarification_required ? "warning" : "info"}
      variant={variant}
      action={<Route className="h-4 w-4 text-[var(--text-tertiary)]" strokeWidth={1.75} />}
    >
      <dl className="mb-3 grid grid-cols-2 gap-3">
        <MetricLine label={translate("generated.runtime.selected_d4192feb")} value={latest.selected_agent_ids.join(", ") || "-"} />
        <MetricLine label={translate("generated.runtime.excluded_1ea94dc2")} value={latest.excluded_agent_ids.join(", ") || "-"} />
        <MetricLine label={translate("generated.runtime.confidence_5ff0e1a0")} value={latest.confidence == null ? "-" : latest.confidence.toFixed(2)} />
        <MetricLine label={translate("generated.runtime.rungraph_6cd35326")} value={latest.run_graph_node_id ?? "-"} />
        <MetricLine label={translate("generated.runtime.tools_568d94f9")} value={latest.required_tools.join(", ") || "-"} />
        <MetricLine label={translate("generated.runtime.skills_3e0b892b")} value={latest.required_skills.join(", ") || "-"} />
      </dl>
      {latest.summary ? (
        <p className="m-0 mb-3 text-[0.75rem] leading-5 text-[var(--text-secondary)]">{latest.summary}</p>
      ) : null}
      <div className="divide-y divide-[var(--divider-hair)]">
        {latest.candidates.slice(0, 8).map((candidate) => (
          <article key={candidate.agent_id} className="grid grid-cols-[1fr_auto] gap-3 py-2.5">
            <div className="min-w-0">
              <p className="m-0 truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
                {candidate.agent_id}
              </p>
              <p className="m-0 mt-1 truncate text-[0.72rem] text-[var(--text-tertiary)]">
                {candidate.reason || candidate.exclusion_reason || candidate.status}
              </p>
            </div>
            <span className="inline-flex items-center gap-1.5 font-mono text-[0.6875rem] text-[var(--text-secondary)]">
              <StatusDot tone={candidate.status === "excluded" ? "warning" : "success"} />
              {candidate.score == null ? candidate.status : candidate.score.toFixed(2)}
            </span>
          </article>
        ))}
      </div>
    </PanelShell>
  );
}

export function HandoffTimelinePanel({
  graph,
  variant = "panel",
}: {
  graph: RunGraphSnapshot | null;
  variant?: Phase2PanelVariant;
}) {
  const handoffs = extractHandoffEvents(graph);
  if (!handoffs.length) {
    return (
      <PanelShell title={translate("generated.runtime.no_handoff_timeline_34fca768")} eyebrow={translate("generated.runtime.handoff_event_v1_912428f3")} tone="neutral" variant={variant}>
        <EmptyState
          title={translate("generated.runtime.no_visible_handoffs_71641857")}
          description={translate("generated.runtime.this_squad_room_has_not_published_transcript_32bb96a9")}
        />
      </PanelShell>
    );
  }
  const blocked = handoffs.some((item) => item.status === "requested" || item.status === "accepted");
  return (
    <PanelShell
      title={translate("generated.runtime.handoff_timeline_343d40bb")}
      eyebrow={`${handoffs.length} handoffs`}
      tone={blocked ? "warning" : "info"}
      variant={variant}
      action={<GitPullRequestArrow className="h-4 w-4 text-[var(--text-tertiary)]" strokeWidth={1.75} />}
    >
      <div className="divide-y divide-[var(--divider-hair)]">
        {handoffs.map((handoff) => (
          <article key={handoff.handoff_id} className="grid grid-cols-[auto_1fr_auto] items-start gap-3 py-3">
            <StatusDot tone={handoffTone(handoff.status)} />
            <div className="min-w-0">
              <p className="m-0 truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
                {handoff.source_agent_id}
                {" -> "}
                {handoff.destination_agent_ids.join(", ")}
              </p>
              <p className="m-0 mt-1 text-[0.72rem] leading-5 text-[var(--text-tertiary)]">
                {handoff.reason}
              </p>
              <p className="m-0 mt-1 truncate font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
                {handoff.handoff_kind} {translate("generated.runtime.criteria_88fbfeb1")}{handoff.return_criteria.length} {translate("generated.runtime.node_a1dcba8d")}{handoff.run_graph_node_id}
              </p>
              {handoff.deadline ? (
                <p className="m-0 mt-1 text-[0.6875rem] text-[var(--text-quaternary)]">
                  {translate("generated.runtime.deadline_640c7864")}{formatDateTime(handoff.deadline)}
                </p>
              ) : null}
            </div>
            <span className="font-mono text-[0.6875rem] uppercase tracking-[var(--tracking-mono)] text-[var(--text-secondary)]">
              {handoff.status}
            </span>
          </article>
        ))}
      </div>
    </PanelShell>
  );
}

export function ChildRunsPanel({
  agentId,
  childRuns,
  onAction,
  busyAction,
  variant = "panel",
}: {
  agentId: string;
  childRuns: ChildRunRecord[];
  onAction?: (childRun: ChildRunRecord, action: "cancel" | "interrupt") => void;
  busyAction?: string | null;
  variant?: Phase2PanelVariant;
}) {
  if (!childRuns.length) {
    return (
      <PanelShell title={translate("generated.runtime.no_child_runs_ae79100b")} eyebrow={translate("generated.runtime.child_run_v1_3329ee22")} tone="neutral" variant={variant}>
        <EmptyState
          title={translate("generated.runtime.no_delegated_work_29c909d3")}
          description={translate("generated.runtime.this_execution_has_not_launched_any_ephemera_4d1784be")}
        />
      </PanelShell>
    );
  }

  return (
    <PanelShell
      title={translate("generated.runtime.delegate_task_children_8bcefabf")}
      eyebrow={`${childRuns.length} child runs`}
      tone={childRuns.some((run) => run.status === "failed") ? "danger" : "info"}
      variant={variant}
    >
      <div className="divide-y divide-[var(--divider-hair)]">
        {childRuns.map((childRun) => {
          const childTaskId = childRun.child_task_id ?? null;
          const actionKey = `${childRun.child_run_id}:`;
          const canCancel = Boolean(onAction) && childRun.available_actions.includes("cancel") && childTaskId != null;
          const canInterrupt = Boolean(onAction) && childRun.available_actions.includes("interrupt") && childTaskId != null;
          return (
            <article
              key={childRun.child_run_id}
              className="grid grid-cols-[auto_1fr_auto] items-start gap-3 py-3"
            >
              <div className="mt-0.5 flex items-center gap-2">
                <GitBranch className="h-3.5 w-3.5 text-[var(--text-tertiary)]" strokeWidth={1.75} />
                <StatusDot tone={stateTone(childRun.status)} />
              </div>
              <div className="min-w-0">
                <p className="m-0 truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
                  {childRun.summary || childRun.child_run_id}
                </p>
                <p className="m-0 mt-0.5 truncate text-[0.72rem] text-[var(--text-tertiary)]">
                  {childRun.status} · {childRun.toolset}
                  {childTaskId ? ` · task #${childTaskId}` : ""}
                  {childRun.cost_usd != null ? ` · $${childRun.cost_usd.toFixed(4)}` : ""}
                </p>
                {childRun.error ? (
                  <p className="m-0 mt-1 text-[0.72rem] text-[var(--tone-danger-text)]">
                    {childRun.error.message}
                  </p>
                ) : null}
              </div>
              <div className="flex flex-wrap justify-end gap-2">
                {childTaskId ? (
                  <Link
                    href={`/runtime/${agentId}/tasks/${childTaskId}`}
                    className="button-pill inline-flex"
                  >
                    {translate("generated.runtime.open_9edc44db")}</Link>
                ) : null}
                {canInterrupt ? (
                  <button
                    type="button"
                    className="button-pill"
                    disabled={busyAction === `${actionKey}interrupt`}
                    onClick={() => onAction?.(childRun, "interrupt")}
                  >
                    {translate("generated.runtime.interrupt_e3ecf10e")}</button>
                ) : null}
                {canCancel ? (
                  <button
                    type="button"
                    className="button-pill"
                    disabled={busyAction === `${actionKey}cancel`}
                    onClick={() => onAction?.(childRun, "cancel")}
                  >
                    {translate("generated.runtime.cancel_b3fd37d1")}</button>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </PanelShell>
  );
}

function extractRouteExplanations(graph: RunGraphSnapshot | null): RouteExplanation[] {
  if (!graph) return [];
  const routes: RouteExplanation[] = [];
  for (const node of graph.nodes) {
    const raw = node as RunGraphNode & { payload?: unknown };
    const metadata = node.metadata ?? {};
    const candidates = [metadata.route_explanation, raw.payload, metadata].filter(Boolean);
    for (const candidate of candidates) {
      const route = parseRouteExplanation(candidate);
      if (route) {
        routes.push({ ...route, run_graph_node_id: route.run_graph_node_id ?? node.id });
        break;
      }
    }
  }
  return routes;
}

function extractHandoffEvents(graph: RunGraphSnapshot | null): HandoffEvent[] {
  if (!graph) return [];
  const handoffs: HandoffEvent[] = [];
  for (const node of graph.nodes) {
    const raw = node as RunGraphNode & { payload?: unknown };
    const metadata = node.metadata ?? {};
    const candidates = [metadata.handoff_event, raw.payload, metadata].filter(Boolean);
    for (const candidate of candidates) {
      const handoff = parseHandoffEvent(candidate);
      if (handoff) {
        handoffs.push({ ...handoff, run_graph_node_id: handoff.run_graph_node_id || node.id });
        break;
      }
    }
  }
  return handoffs;
}

function handoffTone(status: string): StatusDotTone {
  if (status === "returned") return "success";
  if (status === "declined" || status === "timed_out" || status === "failed") return "danger";
  if (status === "requested" || status === "accepted") return "warning";
  return "neutral";
}

export function ContextGovernancePanel({
  context,
  variant = "panel",
}: {
  context: ContextGovernancePayload | null;
  variant?: Phase2PanelVariant;
}) {
  if (!context) {
    return (
      <PanelShell title={translate("generated.runtime.context_governance_unavailable_f71180f2")} eyebrow={translate("generated.runtime.context_governance_v1_d632d159")} tone="neutral" variant={variant}>
        <EmptyState
          title={translate("generated.runtime.no_governed_context_bc50971f")}
          description={translate("generated.runtime.this_execution_has_not_published_context_blo_94da27ef")}
        />
      </PanelShell>
    );
  }

  const summary = context.summary;
  const contextBlockVisual = getRunGraphNodeVisual("context_block");
  const ContextBlockIcon = contextBlockVisual.icon;
  return (
    <PanelShell
      title={translate("generated.runtime.context_governance_87b85b10")}
      eyebrow={translate("generated.runtime.context_governance_v1_d632d159")}
      tone={summary.review_required_count > 0 ? "warning" : "success"}
      variant={variant}
    >
      <dl className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricLine label={translate("generated.runtime.blocks_427e5954")} value={String(summary.block_count)} />
        <MetricLine label={translate("generated.runtime.included_3e644ff2")} value={String(summary.included_count)} />
        <MetricLine label={translate("generated.runtime.dropped_402c1da3")} value={String(summary.dropped_count)} />
        <MetricLine label={translate("generated.runtime.review_3ba5a36d")} value={String(summary.review_required_count)} />
      </dl>
      <div className="max-h-[360px] overflow-auto divide-y divide-[var(--divider-hair)]">
        {context.blocks.map((block) => (
          <article key={block.block_id} className="grid grid-cols-[auto_1fr_auto] items-start gap-3 py-2.5">
            <span
              className="inline-flex h-6 w-6 items-center justify-center rounded-md border"
              style={getSemanticIconStyle(block.status === "included" ? "success" : block.status === "review_required" ? "warning" : "neutral")}
              title={block.category}
            >
              <ContextBlockIcon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <p className="m-0 truncate text-[0.8125rem] font-medium text-[var(--text-primary)]">
                {block.block_id}
              </p>
              <div className="m-0 mt-1 flex min-w-0 flex-wrap items-center gap-1.5 text-[0.72rem] text-[var(--text-tertiary)]">
                <span
                  className="inline-flex rounded-md border px-1.5 py-0.5 font-mono text-[0.625rem] uppercase tracking-[0.08em]"
                  style={getSemanticStyle(block.status === "included" ? "success" : block.status === "review_required" ? "warning" : "neutral")}
                >
                  {block.status}
                </span>
                <span className="truncate">
                  {block.category} · {block.source} {translate("generated.runtime.risk_8b06ff02")}{block.risk}
                  {block.drop_reason ? ` · ${block.drop_reason}` : ""}
                </span>
              </div>
              {block.category === "memory" ? (
                <MemoryContextProvenance provenance={block.provenance} />
              ) : null}
            </div>
            <span className="whitespace-nowrap font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
              {block.token_estimate} {translate("generated.runtime.tok_9a0e5809")}</span>
          </article>
        ))}
      </div>
    </PanelShell>
  );
}

function MemoryContextProvenance({ provenance }: { provenance: Record<string, unknown> }) {
  const selectedCount = typeof provenance.selected_count === "number" ? provenance.selected_count : 0;
  const droppedCount = typeof provenance.dropped_count === "number" ? provenance.dropped_count : 0;
  const conflictCount = typeof provenance.conflict_count === "number" ? provenance.conflict_count : 0;
  const trustScore = typeof provenance.trust_score === "number" ? provenance.trust_score : null;
  const droppedReasons =
    provenance.dropped_reasons && typeof provenance.dropped_reasons === "object"
      ? Object.entries(provenance.dropped_reasons as Record<string, unknown>)
          .map(([reason, count]) => `${reason}:${String(count)}`)
          .join(" · ")
      : "";
  const explanations = Array.isArray(provenance.explanations) ? provenance.explanations.slice(0, 3) : [];

  return (
    <div className="mt-2 space-y-1 text-[0.7rem] text-[var(--text-tertiary)]">
      <div className="flex flex-wrap items-center gap-1.5">
        <span>{translate("generated.runtime.selected_6ea4a98a")} {selectedCount}</span>
        <span>{translate("generated.runtime.dropped_a48c358b")} {droppedCount}</span>
        <span>{translate("generated.runtime.conflict_e7d60738")} {conflictCount}</span>
        {trustScore !== null ? <span>{translate("generated.runtime.trust_4309e9ac")} {trustScore.toFixed(2)}</span> : null}
      </div>
      {droppedReasons ? <p className="m-0 break-words">{translate("generated.runtime.dropped_44b4bcb0")} {droppedReasons}</p> : null}
      {explanations.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {explanations.map((item, index) => {
            const explanation = item && typeof item === "object" ? (item as Record<string, unknown>) : {};
            const memoryId = String(explanation.memory_id ?? `memory-${index + 1}`);
            const layer = String(explanation.layer ?? "memory");
            const sensitivity = String(explanation.sensitivity ?? "normal");
            return (
              <span
                key={`${memoryId}-${index}`}
                className="inline-flex rounded-md border border-[var(--divider-hair)] px-1.5 py-0.5"
              >
                {memoryId} · {layer} · {sensitivity}
              </span>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
