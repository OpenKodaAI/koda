"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  GitBranch,
  PlayCircle,
} from "lucide-react";
import { StatusDot, type StatusDotTone } from "@/components/ui/status-dot";
import type { ChildRunRecord, ContextGovernancePayload } from "@/lib/contracts/phase3-runtime";
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
  runtimeHref,
  variant = "panel",
}: RunGraphPanelsProps) {
  const replayPlan = replay ?? graph?.replay ?? null;
  const action = runtimeHref ? (
    <Link href={runtimeHref} className="button-pill inline-flex">
      Runtime
    </Link>
  ) : null;

  if (!graph) {
    return (
      <PanelShell title="RunGraph unavailable" eyebrow="run_graph.v1" tone="neutral" action={action} variant={variant}>
        <EmptyState
          title="No RunGraph snapshot"
          description="This task has not published a run_graph.v1 payload yet."
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
      eyebrow="run_graph.v1"
      tone={stateTone(graph.status)}
      action={action}
      variant={variant}
    >
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricLine label="State" value={graph.status} />
        <MetricLine label="Nodes" value={String(graph.nodes.length)} />
        <MetricLine label="Policy" value={String(policyCount)} />
        <MetricLine label="Tools" value={String(toolCount)} />
        <MetricLine label="Replay" value={replayPlan?.availability ?? "unavailable"} />
        <MetricLine label="Redactions" value={String(redactionCount)} />
        <MetricLine label="Started" value={formatDateTime(graph.started_at)} />
        <MetricLine label="Completed" value={formatDateTime(graph.completed_at)} />
      </dl>
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
      <PanelShell title="Graph viewer unavailable" eyebrow="nodes" tone="neutral" variant={variant}>
        <EmptyState
          title="No node tree"
          description="The viewer is waiting for backend RunGraph nodes."
        />
      </PanelShell>
    );
  }

  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  const nodes = sortNodes(graph.nodes);

  return (
    <PanelShell title="Run tree" eyebrow={`${nodes.length} nodes`} tone={stateTone(graph.status)} variant={variant}>
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
      <PanelShell title="Replay unavailable" eyebrow="run_replay.v1" tone="neutral" variant={variant}>
        <EmptyState
          title="No offline replay"
          description="The replay contract is not present for this task."
        />
      </PanelShell>
    );
  }

  return (
    <PanelShell
      title={`Offline replay ${replay.availability}`}
      eyebrow="run_replay.v1"
      tone={availabilityTone(replay.availability)}
      variant={variant}
      action={<PlayCircle className="h-4 w-4 text-[var(--text-tertiary)]" strokeWidth={1.75} />}
    >
      {replay.missing_dependencies.length > 0 ? (
        <div className="mb-3 rounded-[var(--radius-panel-sm)] border border-[var(--tone-warning-border)] bg-[var(--tone-warning-bg)] px-3 py-2 text-[0.75rem] text-[var(--tone-warning-text)]">
          Missing: {replay.missing_dependencies.join(", ")}
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
      <PanelShell title="No child runs" eyebrow="child_run.v1" tone="neutral" variant={variant}>
        <EmptyState
          title="No delegated work"
          description="This execution has not launched any ephemeral Delegate Task child runs."
        />
      </PanelShell>
    );
  }

  return (
    <PanelShell
      title="Delegate Task children"
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
                    Open
                  </Link>
                ) : null}
                {canInterrupt ? (
                  <button
                    type="button"
                    className="button-pill"
                    disabled={busyAction === `${actionKey}interrupt`}
                    onClick={() => onAction?.(childRun, "interrupt")}
                  >
                    Interrupt
                  </button>
                ) : null}
                {canCancel ? (
                  <button
                    type="button"
                    className="button-pill"
                    disabled={busyAction === `${actionKey}cancel`}
                    onClick={() => onAction?.(childRun, "cancel")}
                  >
                    Cancel
                  </button>
                ) : null}
              </div>
            </article>
          );
        })}
      </div>
    </PanelShell>
  );
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
      <PanelShell title="Context governance unavailable" eyebrow="context_governance.v1" tone="neutral" variant={variant}>
        <EmptyState
          title="No governed context"
          description="This execution has not published context block governance yet."
        />
      </PanelShell>
    );
  }

  const summary = context.summary;
  const contextBlockVisual = getRunGraphNodeVisual("context_block");
  const ContextBlockIcon = contextBlockVisual.icon;
  return (
    <PanelShell
      title="Context governance"
      eyebrow="context_governance.v1"
      tone={summary.review_required_count > 0 ? "warning" : "success"}
      variant={variant}
    >
      <dl className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricLine label="Blocks" value={String(summary.block_count)} />
        <MetricLine label="Included" value={String(summary.included_count)} />
        <MetricLine label="Dropped" value={String(summary.dropped_count)} />
        <MetricLine label="Review" value={String(summary.review_required_count)} />
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
                  {block.category} · {block.source} · risk {block.risk}
                  {block.drop_reason ? ` · ${block.drop_reason}` : ""}
                </span>
              </div>
            </div>
            <span className="whitespace-nowrap font-mono text-[0.6875rem] text-[var(--text-quaternary)]">
              {block.token_estimate} tok
            </span>
          </article>
        ))}
      </div>
    </PanelShell>
  );
}
