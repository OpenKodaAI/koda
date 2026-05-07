"use client";

import { keepPreviousData } from "@tanstack/react-query";
import { Users2 } from "lucide-react";
import Link from "next/link";

import { ErrorState } from "@/components/ui/async-feedback";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { fetchControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";
import {
  formatRelativeTimestamp,
  type SquadOverviewItem,
  type SquadOverviewResponse,
} from "@/lib/squads";
import { cn } from "@/lib/utils";

function SquadCard({ squad }: { squad: SquadOverviewItem }) {
  const tasksOpen =
    squad.taskCounts.pending +
    squad.taskCounts.claimed +
    squad.taskCounts.in_progress +
    squad.taskCounts.blocked;
  const lastActive = formatRelativeTimestamp(squad.lastActiveAt);
  return (
    <Link
      href={`/squads/${squad.squadId}`}
      data-testid="squad-card"
      className="group relative flex flex-col gap-3 rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel)] p-4 transition-colors hover:border-[var(--border-strong)]"
    >
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-[15px] font-medium text-[var(--text-primary)]">{squad.squadId}</h3>
          <p className="mt-0.5 truncate text-[12px] text-[var(--text-tertiary)]">
            workspace · {squad.workspaceId ?? "—"}
          </p>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-[var(--radius-chip)] px-2 py-0.5 text-[11px] uppercase tracking-[0.08em]",
            squad.coordinatorAgentId
              ? "bg-[var(--tone-info-bg)] text-[var(--tone-info-text)]"
              : "bg-[var(--tone-neutral-bg)] text-[var(--tone-neutral-text)]",
          )}
        >
          {squad.coordinatorAgentId ? `coord · ${squad.coordinatorAgentId}` : "no coordinator"}
        </span>
      </header>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-[13px]">
        <div>
          <dt className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-quaternary)]">Members</dt>
          <dd className="mt-0.5 text-[var(--text-primary)]">{squad.memberCount}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-quaternary)]">Last active</dt>
          <dd className="mt-0.5 font-mono text-[var(--text-secondary)]">{lastActive}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-quaternary)]">Threads</dt>
          <dd className="mt-0.5 text-[var(--text-primary)]">
            <span className="text-[var(--text-primary)]">{squad.threadCounts.open}</span>
            <span className="text-[var(--text-tertiary)]"> open · </span>
            <span className="text-[var(--text-tertiary)]">{squad.threadCounts.paused} paused · </span>
            <span className="text-[var(--text-tertiary)]">{squad.threadCounts.completed} done</span>
          </dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-quaternary)]">Tasks</dt>
          <dd className="mt-0.5 text-[var(--text-primary)]">
            <span>{tasksOpen}</span>
            <span className="text-[var(--text-tertiary)]"> active · </span>
            <span className="text-[var(--text-tertiary)]">{squad.taskCounts.done} done</span>
          </dd>
        </div>
      </dl>
      <footer className="flex items-center justify-between border-t border-[color:var(--divider-hair)] pt-2 text-[12px]">
        <span className="text-[var(--text-tertiary)]">Cost</span>
        <span className="font-mono text-[var(--text-secondary)]">${squad.totalCostUsd}</span>
      </footer>
    </Link>
  );
}

export default function SquadsPageClient() {
  const query = useControlPlaneQuery<SquadOverviewResponse>({
    queryKey: queryKeys.dashboard.squadsOverview(null),
    queryFn: ({ signal }) =>
      fetchControlPlaneDashboardJson<SquadOverviewResponse>("/squads/overview", {
        signal,
        fallbackError: "Failed to load squads.",
      }),
    notifyOnChangeProps: ["data", "error"],
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
  });

  if (query.isError) {
    return (
      <div className="min-w-0 space-y-4" data-testid="squads-route">
        <ErrorState
          title="Couldn't load squads"
          description={query.error?.message ?? "Try refreshing the page."}
          onRetry={() => {
            void query.refetch();
          }}
        />
      </div>
    );
  }

  const data = query.data;
  const items = data?.items ?? [];

  return (
    <div className="min-w-0 space-y-4" data-testid="squads-route">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-[22px] font-medium tracking-[-0.02em] text-[var(--text-primary)]">Squads</h1>
          <p className="mt-1 text-[13px] text-[var(--text-tertiary)]">
            Active squad threads, members and task progress across your workspaces.
          </p>
        </div>
      </header>

      {data && !data.available ? (
        <div
          data-testid="squads-empty-postgres"
          className="rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel)] p-6 text-[13px] text-[var(--text-tertiary)]"
        >
          Squads are stored in Postgres. Configure <code className="font-mono">POSTGRES_URL</code> to enable
          this dashboard.
        </div>
      ) : items.length === 0 ? (
        <div
          data-testid="squads-empty"
          className="flex items-center gap-3 rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel)] p-6 text-[13px] text-[var(--text-tertiary)]"
        >
          <Users2 className="icon-md" strokeWidth={1.75} aria-hidden />
          <span>No active squads yet — create one with <code className="font-mono">/squad_bind</code>.</span>
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {items.map((squad) => (
            <SquadCard key={squad.squadId} squad={squad} />
          ))}
        </div>
      )}
    </div>
  );
}
