"use client";

import { keepPreviousData } from "@tanstack/react-query";
import Link from "next/link";

import { ErrorState } from "@/components/ui/async-feedback";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { fetchControlPlaneDashboardJson } from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";
import {
  formatRelativeTimestamp,
  type SquadActivityResponse,
  type SquadThreadSummary,
  type SquadThreadsResponse,
} from "@/lib/squads";
import { cn } from "@/lib/utils";

const THREAD_STATUS_TONE: Record<string, string> = {
  open: "bg-[var(--tone-success-bg)] text-[var(--tone-success-text)]",
  paused: "bg-[var(--tone-warning-bg)] text-[var(--tone-warning-text)]",
  completed: "bg-[var(--tone-info-bg)] text-[var(--tone-info-text)]",
  archived: "bg-[var(--tone-neutral-bg)] text-[var(--tone-neutral-text)]",
};

function ThreadRow({ thread }: { thread: SquadThreadSummary }) {
  const updated = formatRelativeTimestamp(thread.updatedAt);
  const tone =
    THREAD_STATUS_TONE[thread.status] ?? "bg-[var(--tone-neutral-bg)] text-[var(--tone-neutral-text)]";
  return (
    <li
      data-testid="squad-thread-row"
      className="border-b border-[color:var(--divider-hair)] last:border-b-0"
    >
      <Link
        href={`/squads/threads/${thread.id}`}
        className="flex flex-wrap items-center gap-3 px-4 py-3 hover:bg-[var(--hover-tint)]"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-[14px] text-[var(--text-primary)]">
              {thread.title || "(untitled thread)"}
            </span>
            <span
              className={cn(
                "shrink-0 rounded-[var(--radius-chip)] px-2 py-0.5 text-[11px] uppercase tracking-[0.08em]",
                tone,
              )}
            >
              {thread.status}
            </span>
          </div>
          <p className="mt-0.5 text-[12px] text-[var(--text-tertiary)]">
            <span className="font-mono">{thread.id.slice(0, 8)}…</span>
            <span className="mx-2">·</span>
            workspace · <span className="font-mono">{thread.workspaceId}</span>
            {thread.coordinatorAgentId ? (
              <>
                <span className="mx-2">·</span>
                coordinator · <span className="font-mono">{thread.coordinatorAgentId}</span>
              </>
            ) : null}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1 text-[12px]">
          <span className="font-mono text-[var(--text-secondary)]">{updated}</span>
          <span className="font-mono text-[var(--text-tertiary)]">${thread.costUsdAccum}</span>
        </div>
      </Link>
    </li>
  );
}

export default function SquadDetailPageClient({ squadId }: { squadId: string }) {
  const query = useControlPlaneQuery<SquadThreadsResponse>({
    queryKey: queryKeys.dashboard.squadThreads(squadId, null),
    queryFn: ({ signal }) =>
      fetchControlPlaneDashboardJson<SquadThreadsResponse>(`/squads/${squadId}/threads`, {
        signal,
        fallbackError: "Failed to load squad threads.",
      }),
    notifyOnChangeProps: ["data", "error"],
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
  });

  const activity = useControlPlaneQuery<SquadActivityResponse>({
    queryKey: queryKeys.dashboard.squadActivity(squadId),
    queryFn: ({ signal }) =>
      fetchControlPlaneDashboardJson<SquadActivityResponse>(`/squads/${squadId}/activity`, {
        signal,
        fallbackError: "Failed to load squad activity.",
      }),
    notifyOnChangeProps: ["data", "error"],
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
  });

  if (query.isError) {
    return (
      <div className="min-w-0 space-y-4" data-testid="squad-detail-route">
        <ErrorState
          title="Couldn't load squad"
          description={query.error?.message ?? "Try refreshing the page."}
          onRetry={() => {
            void query.refetch();
          }}
        />
      </div>
    );
  }

  const data = query.data;
  if (!data) {
    return (
      <div
        className="min-w-0 space-y-4 text-[13px] text-[var(--text-tertiary)]"
        data-testid="squad-detail-route"
      >
        Loading squad…
      </div>
    );
  }

  const items = data.items;

  return (
    <div className="min-w-0 space-y-5" data-testid="squad-detail-route">
      <header className="flex flex-col gap-2">
        <div className="flex items-center gap-2 text-[12px] text-[var(--text-tertiary)]">
          <Link href="/squads" className="hover:text-[var(--text-secondary)]">
            Squads
          </Link>
          <span>/</span>
          <span className="font-mono text-[var(--text-secondary)]">{squadId}</span>
        </div>
        <div>
          <h1 className="text-[22px] font-medium tracking-[-0.02em] text-[var(--text-primary)]">
            {squadId}
          </h1>
          <p className="mt-1 text-[13px] text-[var(--text-tertiary)]">
            {data.count} thread(s) in this squad — click a row to open.
          </p>
        </div>
      </header>

      {!data.available ? (
        <div
          data-testid="squad-detail-empty-postgres"
          className="rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel)] p-6 text-[13px] text-[var(--text-tertiary)]"
        >
          Squads are stored in Postgres. Configure <code className="font-mono">POSTGRES_URL</code> to enable
          this dashboard.
        </div>
      ) : items.length === 0 ? (
        <div
          data-testid="squad-detail-empty"
          className="rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel)] p-6 text-[13px] text-[var(--text-tertiary)]"
        >
          No threads in <span className="font-mono">{squadId}</span> yet.
        </div>
      ) : (
        <ul className="rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel)]">
          {items.map((thread) => (
            <ThreadRow key={thread.id} thread={thread} />
          ))}
        </ul>
      )}

      <ActivityFeed activity={activity.data ?? null} squadId={squadId} />
    </div>
  );
}

function ActivityFeed({
  activity,
  squadId,
}: {
  activity: SquadActivityResponse | null;
  squadId: string;
}) {
  return (
    <section data-testid="squad-activity-feed" className="space-y-2">
      <h2 className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-quaternary)]">
        Recent activity {activity ? `(${activity.count})` : ""}
      </h2>
      {!activity ? (
        <p className="text-[12px] text-[var(--text-tertiary)]">Loading activity…</p>
      ) : !activity.available ? (
        <p
          data-testid="squad-activity-empty-postgres"
          className="text-[12px] text-[var(--text-tertiary)]"
        >
          Activity stream requires Postgres.
        </p>
      ) : activity.items.length === 0 ? (
        <p data-testid="squad-activity-empty" className="text-[12px] text-[var(--text-tertiary)]">
          No coordinator changes or system events yet.
        </p>
      ) : (
        <ul className="rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel)]">
          {activity.items.map((entry, index) => {
            const ts = formatRelativeTimestamp(entry.timestamp);
            const actor = entry.actor || "system";
            return (
              <li
                key={`${entry.timestamp ?? "?"}-${index}`}
                data-testid="squad-activity-row"
                data-event-type={entry.eventType}
                className="flex flex-col gap-1 border-b border-[color:var(--divider-hair)] px-4 py-2 text-[12px] last:border-b-0"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="font-mono text-[var(--text-secondary)]">{actor}</span>
                    <span className="rounded-[var(--radius-chip)] bg-[var(--panel-strong)] px-1.5 py-0.5 text-[11px] uppercase tracking-[0.08em] text-[var(--text-tertiary)]">
                      {entry.eventType}
                    </span>
                  </div>
                  <span className="font-mono text-[11px] text-[var(--text-quaternary)]">{ts}</span>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[var(--text-primary)]">{entry.summary}</span>
                  {entry.threadId ? (
                    <Link
                      href={`/squads/threads/${entry.threadId}`}
                      className="font-mono text-[11px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
                    >
                      thread {entry.threadId.slice(0, 8)}…
                    </Link>
                  ) : (
                    <span className="font-mono text-[11px] text-[var(--text-quaternary)]">
                      squad {squadId} (no thread)
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
