"use client";

import { keepPreviousData, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { type FormEvent, useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/async-feedback";
import { useControlPlaneQuery } from "@/hooks/use-app-query";
import { useSquadThreadEvents } from "@/hooks/use-squad-thread-events";
import {
  fetchControlPlaneDashboardJson,
  mutateControlPlaneDashboardJson,
} from "@/lib/control-plane-dashboard";
import { queryKeys } from "@/lib/query/keys";
import {
  formatRelativeTimestamp,
  type SquadThreadOverviewResponse,
} from "@/lib/squads";
import { cn } from "@/lib/utils";

const TASK_STATUS_TONE: Record<string, string> = {
  pending: "bg-[var(--tone-neutral-bg)] text-[var(--tone-neutral-text)]",
  claimed: "bg-[var(--tone-info-bg)] text-[var(--tone-info-text)]",
  in_progress: "bg-[var(--tone-info-bg)] text-[var(--tone-info-text)]",
  blocked: "bg-[var(--tone-warning-bg)] text-[var(--tone-warning-text)]",
  done: "bg-[var(--tone-success-bg)] text-[var(--tone-success-text)]",
  failed: "bg-[var(--tone-danger-bg)] text-[var(--tone-danger-text)]",
  cancelled: "bg-[var(--tone-neutral-bg)] text-[var(--tone-neutral-text)]",
  escalated: "bg-[var(--tone-warning-bg)] text-[var(--tone-warning-text)]",
};

const THREAD_STATUS_TONE: Record<string, string> = {
  open: "bg-[var(--tone-success-bg)] text-[var(--tone-success-text)]",
  paused: "bg-[var(--tone-warning-bg)] text-[var(--tone-warning-text)]",
  completed: "bg-[var(--tone-info-bg)] text-[var(--tone-info-text)]",
  archived: "bg-[var(--tone-neutral-bg)] text-[var(--tone-neutral-text)]",
};

const MESSAGE_TYPE_LABEL: Record<string, string> = {
  user_input: "user",
  agent_text: "agent",
  task_request: "task req",
  task_result: "task res",
  status_update: "status",
  escalation: "escalation",
  system_event: "system",
};

function StatusBadge({ status, tones }: { status: string; tones: Record<string, string> }) {
  const tone = tones[status] ?? "bg-[var(--tone-neutral-bg)] text-[var(--tone-neutral-text)]";
  return (
    <span
      className={cn(
        "shrink-0 rounded-[var(--radius-chip)] px-2 py-0.5 text-[11px] uppercase tracking-[0.08em]",
        tone,
      )}
      data-status={status}
    >
      {status.replace("_", " ")}
    </span>
  );
}

type TaskRow = SquadThreadOverviewResponse["activeTasks"][number];

type TaskActionContext = {
  threadId: string;
  actingAs: string;
  onError: (message: string) => void;
};

function TaskRowActions({
  task,
  context,
}: {
  task: TaskRow;
  context: TaskActionContext;
}) {
  const queryClient = useQueryClient();
  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.squadThread(context.threadId) });

  const claim = useMutation({
    mutationFn: () =>
      mutateControlPlaneDashboardJson(`/squads/tasks/${task.id}/claim`, {
        body: { agent_id: context.actingAs },
        fallbackError: "Failed to claim task.",
      }),
    onSuccess: () => invalidate(),
    onError: (err) => context.onError(err instanceof Error ? err.message : "Failed to claim task."),
  });
  const complete = useMutation({
    mutationFn: () =>
      mutateControlPlaneDashboardJson(`/squads/tasks/${task.id}/complete`, {
        body: { agent_id: context.actingAs },
        fallbackError: "Failed to complete task.",
      }),
    onSuccess: () => invalidate(),
    onError: (err) =>
      context.onError(err instanceof Error ? err.message : "Failed to complete task."),
  });
  const escalate = useMutation({
    mutationFn: (reason: string) =>
      mutateControlPlaneDashboardJson(`/squads/tasks/${task.id}/escalate`, {
        body: { agent_id: context.actingAs, reason },
        fallbackError: "Failed to escalate task.",
      }),
    onSuccess: () => invalidate(),
    onError: (err) =>
      context.onError(err instanceof Error ? err.message : "Failed to escalate task."),
  });

  const disabled = !context.actingAs.trim();
  const showClaim = task.status === "pending";
  const showComplete = task.status === "claimed" || task.status === "in_progress";
  const showEscalate =
    task.status === "claimed" ||
    task.status === "in_progress" ||
    task.status === "blocked";

  return (
    <div className="flex flex-wrap items-center gap-2">
      {showClaim ? (
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={disabled || claim.isPending}
          onClick={() => claim.mutate()}
          data-testid="task-action-claim"
          data-task-id={task.id}
        >
          Claim
        </Button>
      ) : null}
      {showComplete ? (
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={disabled || complete.isPending}
          onClick={() => complete.mutate()}
          data-testid="task-action-complete"
          data-task-id={task.id}
        >
          Complete
        </Button>
      ) : null}
      {showEscalate ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled || escalate.isPending}
          onClick={() => {
            const reason = window.prompt("Reason for escalation?");
            if (reason && reason.trim()) {
              escalate.mutate(reason.trim());
            }
          }}
          data-testid="task-action-escalate"
          data-task-id={task.id}
        >
          Escalate
        </Button>
      ) : null}
    </div>
  );
}

function ThreadComposer({
  threadId,
  actingAs,
  onActingAsChange,
  onError,
}: {
  threadId: string;
  actingAs: string;
  onActingAsChange: (value: string) => void;
  onError: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const [content, setContent] = useState("");
  const post = useMutation({
    mutationFn: (payload: { content: string; from_agent: string }) =>
      mutateControlPlaneDashboardJson<{ messageId: number }>(
        `/squads/threads/${threadId}/messages`,
        {
          body: payload,
          fallbackError: "Failed to post message.",
        },
      ),
    onSuccess: () => {
      setContent("");
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.squadThread(threadId) });
    },
    onError: (err) => onError(err instanceof Error ? err.message : "Failed to post message."),
  });

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = content.trim();
    if (!trimmed) return;
    const sender = actingAs.trim() || "operator";
    post.mutate({ content: trimmed, from_agent: sender });
  };

  return (
    <form
      onSubmit={handleSubmit}
      data-testid="thread-composer"
      className="flex flex-col gap-2 rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel)] p-3"
    >
      <label className="flex flex-col gap-1 text-[12px] text-[var(--text-tertiary)]">
        Acting as
        <input
          type="text"
          value={actingAs}
          onChange={(event) => onActingAsChange(event.target.value)}
          placeholder="agent_id (e.g. PM, FE)"
          className="h-9 rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 text-[14px] text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none"
          data-testid="thread-acting-as"
        />
      </label>
      <textarea
        value={content}
        onChange={(event) => setContent(event.target.value)}
        placeholder="Post a message to this thread…"
        rows={3}
        className="rounded-[var(--radius-input)] border border-[var(--border-subtle)] bg-[var(--panel-soft)] px-3 py-2 text-[14px] text-[var(--text-primary)] focus:border-[var(--accent)] focus:outline-none"
        data-testid="thread-composer-textarea"
      />
      <div className="flex items-center justify-between gap-2 text-[12px] text-[var(--text-tertiary)]">
        <span>
          Posts as <span className="font-mono text-[var(--text-secondary)]">{actingAs.trim() || "operator"}</span>
          {" "}— audit-only (no Telegram delivery from web).
        </span>
        <Button
          type="submit"
          variant="accent"
          size="sm"
          disabled={!content.trim() || post.isPending}
          data-testid="thread-composer-submit"
        >
          {post.isPending ? "Posting…" : "Post"}
        </Button>
      </div>
    </form>
  );
}

export default function SquadThreadPageClient({ threadId }: { threadId: string }) {
  const [actingAs, setActingAs] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const query = useControlPlaneQuery<SquadThreadOverviewResponse>({
    queryKey: queryKeys.dashboard.squadThread(threadId),
    queryFn: ({ signal }) =>
      fetchControlPlaneDashboardJson<SquadThreadOverviewResponse>(`/squads/threads/${threadId}`, {
        signal,
        fallbackError: "Failed to load squad thread.",
      }),
    notifyOnChangeProps: ["data", "error"],
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
  });

  const onLiveEvent = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.squadThread(threadId) });
  }, [queryClient, threadId]);
  const liveStatus = useSquadThreadEvents({ threadId, onEvent: onLiveEvent });

  if (query.isError) {
    return (
      <div className="min-w-0 space-y-4" data-testid="squad-thread-route">
        <ErrorState
          title="Couldn't load thread"
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
        data-testid="squad-thread-route"
      >
        Loading thread…
      </div>
    );
  }

  const { thread, participants, recentMessages, activeTasks } = data;
  const lastUpdate = formatRelativeTimestamp(thread.updatedAt);
  const taskContext: TaskActionContext = {
    threadId,
    actingAs,
    onError: setActionError,
  };

  return (
    <div className="min-w-0 space-y-5" data-testid="squad-thread-route">
      <header className="flex flex-col gap-2">
        <div className="flex items-center gap-2 text-[12px] text-[var(--text-tertiary)]">
          <Link href="/squads" className="hover:text-[var(--text-secondary)]">
            Squads
          </Link>
          <span>/</span>
          <Link
            href={`/squads/${thread.squadId}`}
            className="font-mono text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            {thread.squadId}
          </Link>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-[22px] font-medium tracking-[-0.02em] text-[var(--text-primary)]">
              {thread.title || "(untitled thread)"}
            </h1>
            <p className="mt-1 text-[12px] text-[var(--text-tertiary)]">
              workspace · <span className="font-mono">{thread.workspaceId}</span>
              <span className="mx-2">·</span>
              updated <span className="font-mono">{lastUpdate}</span>
              {thread.coordinatorAgentId ? (
                <>
                  <span className="mx-2">·</span>
                  coordinator · <span className="font-mono">{thread.coordinatorAgentId}</span>
                </>
              ) : null}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span
              data-testid="thread-live-indicator"
              data-status={liveStatus}
              className={cn(
                "flex items-center gap-1.5 text-[11px] uppercase tracking-[0.08em]",
                liveStatus === "open"
                  ? "text-[var(--tone-success-text)]"
                  : "text-[var(--text-quaternary)]",
              )}
              title={`SSE connection · ${liveStatus}`}
            >
              <span
                className={cn(
                  "size-1.5 rounded-full",
                  liveStatus === "open"
                    ? "bg-[var(--tone-success-dot)] animate-pulse"
                    : "bg-[var(--text-quaternary)]",
                )}
                aria-hidden
              />
              {liveStatus === "open" ? "live" : liveStatus}
            </span>
            <StatusBadge status={thread.status} tones={THREAD_STATUS_TONE} />
          </div>
        </div>
      </header>

      {actionError ? (
        <div
          data-testid="thread-action-error"
          role="alert"
          className="rounded-[var(--radius-panel)] border border-[var(--tone-danger-border)] bg-[var(--tone-danger-bg)] px-3 py-2 text-[13px] text-[var(--tone-danger-text)]"
        >
          {actionError}
          <button
            type="button"
            className="ml-3 underline-offset-2 hover:underline"
            onClick={() => setActionError(null)}
          >
            dismiss
          </button>
        </div>
      ) : null}

      <section data-testid="participants-strip">
        <h2 className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-quaternary)]">
          Participants ({participants.length})
        </h2>
        <ul className="mt-2 flex flex-wrap gap-2">
          {participants.length === 0 ? (
            <li className="text-[12px] text-[var(--text-tertiary)]">no participants yet</li>
          ) : (
            participants.map((p) => (
              <li
                key={p.agentId}
                className="flex items-center gap-1.5 rounded-[var(--radius-chip)] border border-[var(--border-subtle)] bg-[var(--panel)] px-2 py-1 text-[12px]"
              >
                <span className="font-mono text-[var(--text-primary)]">{p.agentId}</span>
                <span className="text-[var(--text-quaternary)]">·</span>
                <span className="text-[var(--text-tertiary)]">{p.role}</span>
              </li>
            ))
          )}
        </ul>
      </section>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(280px,0.9fr)]">
        <section data-testid="message-timeline" className="space-y-2">
          <h2 className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-quaternary)]">
            Recent messages ({recentMessages.length})
          </h2>
          {recentMessages.length === 0 ? (
            <p className="text-[12px] text-[var(--text-tertiary)]">no messages in this thread yet</p>
          ) : (
            <ul className="rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel)]">
              {recentMessages.map((msg) => {
                const sender = msg.from ?? "?";
                const label = MESSAGE_TYPE_LABEL[msg.type] ?? msg.type;
                const ts = formatRelativeTimestamp(msg.createdAt);
                return (
                  <li
                    key={msg.id}
                    data-testid="message-row"
                    className="flex flex-col gap-1 border-b border-[color:var(--divider-hair)] px-4 py-2 last:border-b-0"
                  >
                    <div className="flex items-center justify-between gap-2 text-[12px]">
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="font-mono text-[var(--text-secondary)]">{sender}</span>
                        <span className="rounded-[var(--radius-chip)] bg-[var(--panel-strong)] px-1.5 py-0.5 text-[11px] uppercase tracking-[0.08em] text-[var(--text-tertiary)]">
                          {label}
                        </span>
                      </div>
                      <span className="font-mono text-[11px] text-[var(--text-quaternary)]">{ts}</span>
                    </div>
                    <p className="text-[13px] text-[var(--text-primary)]">{msg.content}</p>
                  </li>
                );
              })}
            </ul>
          )}
          <ThreadComposer
            threadId={threadId}
            actingAs={actingAs}
            onActingAsChange={setActingAs}
            onError={setActionError}
          />
        </section>

        <aside data-testid="task-panel" className="space-y-4">
          <section>
            <h2 className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-quaternary)]">
              Active tasks ({activeTasks.length})
            </h2>
            {activeTasks.length === 0 ? (
              <p className="mt-2 text-[12px] text-[var(--text-tertiary)]">no active tasks</p>
            ) : (
              <ul className="mt-2 rounded-[var(--radius-panel)] border border-[var(--border-subtle)] bg-[var(--panel)]">
                {activeTasks.map((task) => (
                  <li
                    key={task.id}
                    data-testid="task-row"
                    className="flex flex-col gap-2 border-b border-[color:var(--divider-hair)] px-4 py-2 last:border-b-0"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-[13px] text-[var(--text-primary)]">{task.title}</span>
                      <StatusBadge status={task.status} tones={TASK_STATUS_TONE} />
                    </div>
                    <p className="text-[12px] text-[var(--text-tertiary)]">
                      <span className="font-mono">{task.id.slice(0, 8)}…</span>
                      <span className="mx-2">·</span>
                      assignee ·{" "}
                      <span className="font-mono">{task.assignedAgentId ?? "unassigned"}</span>
                    </p>
                    <TaskRowActions task={task} context={taskContext} />
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h2 className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-quaternary)]">
              Counts
            </h2>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 text-[13px]">
              <div>
                <dt className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-quaternary)]">
                  Open
                </dt>
                <dd className="mt-0.5 text-[var(--text-primary)]">{data.openTaskCount}</dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-quaternary)]">
                  Done
                </dt>
                <dd className="mt-0.5 text-[var(--text-primary)]">{data.doneTaskCount}</dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-quaternary)]">
                  Cost
                </dt>
                <dd className="mt-0.5 font-mono text-[var(--text-secondary)]">
                  ${thread.costUsdAccum}
                </dd>
              </div>
              <div>
                <dt className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-quaternary)]">
                  Telegram
                </dt>
                <dd className="mt-0.5 font-mono text-[var(--text-secondary)]">
                  {thread.telegramChatId !== null ? thread.telegramChatId : "—"}
                  {thread.telegramMessageThreadId !== null
                    ? ` · t${thread.telegramMessageThreadId}`
                    : ""}
                </dd>
              </div>
            </dl>
          </section>
        </aside>
      </div>
    </div>
  );
}
