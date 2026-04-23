"use client";

import { memo, useMemo } from "react";
import { AgentGlyph } from "@/components/dashboard/agent-glyph";
import type { AgentDisplay } from "@/lib/agent-constants";
import type { AgentStats, Task } from "@/lib/types";
import { truncateText } from "@/lib/utils";
import { cn } from "@/lib/utils";

export type ExecutionHistoryStatus =
  | "completed"
  | "failed"
  | "running"
  | "retrying"
  | "queued";

export interface ExecutionHistoryEntry {
  agent: AgentDisplay;
  stats?: AgentStats;
}

export interface ExecutionHistoryStrings {
  empty: string;
  noMessage: string;
  status: Record<ExecutionHistoryStatus, string>;
}

interface ExecutionHistoryProps {
  entries: ExecutionHistoryEntry[];
  strings: ExecutionHistoryStrings;
  limit?: number;
  onSelectAgent?: (agentId: string) => void;
  className?: string;
}

const STATUS_RANK: Record<ExecutionHistoryStatus, number> = {
  running: 0,
  retrying: 1,
  queued: 2,
  completed: 3,
  failed: 3,
};

const STATUS_TONE: Record<ExecutionHistoryStatus, string> = {
  completed: "var(--tone-success-dot)",
  failed: "var(--tone-danger-dot)",
  running: "var(--tone-info-dot)",
  retrying: "var(--tone-warning-dot)",
  queued: "var(--tone-warning-dot)",
};

interface Row {
  agent: AgentDisplay;
  task: Task;
  status: ExecutionHistoryStatus;
  sortValue: number;
}

function formatCompactRelative(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  const diffMs = Date.now() - date.getTime();
  if (Number.isNaN(diffMs) || diffMs < 0) return null;
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
}

function resolveTaskStatus(task: Task): ExecutionHistoryStatus {
  switch (task.status) {
    case "completed":
    case "failed":
    case "running":
    case "retrying":
    case "queued":
      return task.status;
    default:
      return "completed";
  }
}

function taskTimestamp(task: Task): number {
  const source = task.completed_at ?? task.started_at ?? task.created_at;
  if (!source) return 0;
  const t = new Date(source).getTime();
  return Number.isNaN(t) ? 0 : t;
}

function ExecutionHistoryComponent({
  entries,
  strings,
  limit = 10,
  onSelectAgent,
  className,
}: ExecutionHistoryProps) {
  const rows = useMemo<Row[]>(() => {
    const all: Row[] = [];
    for (const entry of entries) {
      const tasks = entry.stats?.recentTasks ?? [];
      for (const task of tasks) {
        all.push({
          agent: entry.agent,
          task,
          status: resolveTaskStatus(task),
          sortValue: taskTimestamp(task),
        });
      }
    }
    all.sort((a, b) => {
      if (b.sortValue !== a.sortValue) return b.sortValue - a.sortValue;
      return STATUS_RANK[a.status] - STATUS_RANK[b.status];
    });
    return all.slice(0, limit);
  }, [entries, limit]);

  if (rows.length === 0) {
    return (
      <p className={cn("m-0 text-[var(--font-size-sm)] text-[var(--text-tertiary)]", className)}>
        {strings.empty}
      </p>
    );
  }

  return (
    <ul
      className={cn("flex w-full flex-col", className)}
      role="list"
      aria-label="Execution history"
    >
      {rows.map(({ agent, task, status }, index) => {
        const query = truncateText(task.query_text?.trim() || strings.noMessage, 96);
        const timestamp = formatCompactRelative(
          task.completed_at ?? task.started_at ?? task.created_at,
        );

        return (
          <li key={`${agent.id}-${task.id}`}>
            <button
              type="button"
              onClick={() => onSelectAgent?.(agent.id)}
              className={cn(
                "grid w-full items-center gap-5 px-3 py-3.5 text-left outline-none",
                "grid-cols-[200px_minmax(0,1fr)_auto]",
                "transition-colors duration-[120ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
                "hover:bg-[var(--hover-tint)]",
                "focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--canvas)] rounded-[var(--radius-panel-sm)]",
                index > 0 && "border-t border-[color:var(--divider-hair)]",
              )}
            >
              {/* Column 1: agent identity */}
              <div className="flex min-w-0 items-center gap-3">
                <AgentGlyph
                  agentId={agent.id}
                  color={agent.color}
                  variant="list"
                  shape="swatch"
                  className="h-6 w-6 shrink-0"
                />
                <span className="truncate text-[var(--font-size-sm)] font-medium text-[var(--text-primary)]">
                  {agent.label}
                </span>
              </div>

              {/* Column 2: query preview */}
              <p className="m-0 min-w-0 truncate text-[var(--font-size-sm)] text-[var(--text-secondary)]">
                {query}
              </p>

              {/* Column 3: status + timestamp stacked */}
              <div className="flex shrink-0 flex-col items-end gap-0.5 text-right">
                <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-[0.75rem] font-medium text-[var(--text-secondary)]">
                  <span
                    className="inline-block h-1.5 w-1.5 rounded-full"
                    style={{ background: STATUS_TONE[status] }}
                    aria-hidden="true"
                  />
                  {strings.status[status]}
                </span>
                <span
                  className={cn(
                    "whitespace-nowrap text-[10.5px] tabular-nums text-[var(--text-quaternary)]",
                    !timestamp && "invisible",
                  )}
                  aria-hidden={!timestamp}
                >
                  {timestamp ?? "—"}
                </span>
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function arePropsEqual(prev: ExecutionHistoryProps, next: ExecutionHistoryProps): boolean {
  if (prev.className !== next.className) return false;
  if (prev.limit !== next.limit) return false;
  if (prev.onSelectAgent !== next.onSelectAgent) return false;
  if (prev.strings !== next.strings) return false;
  if (prev.entries.length !== next.entries.length) return false;
  for (let i = 0; i < prev.entries.length; i += 1) {
    const a = prev.entries[i]!;
    const b = next.entries[i]!;
    if (a.agent.id !== b.agent.id) return false;
    const aTasks = a.stats?.recentTasks ?? [];
    const bTasks = b.stats?.recentTasks ?? [];
    if (aTasks.length !== bTasks.length) return false;
    for (let j = 0; j < aTasks.length; j += 1) {
      if (aTasks[j]!.id !== bTasks[j]!.id) return false;
      if (aTasks[j]!.status !== bTasks[j]!.status) return false;
    }
  }
  return true;
}

export const ExecutionHistory = memo(ExecutionHistoryComponent, arePropsEqual);
