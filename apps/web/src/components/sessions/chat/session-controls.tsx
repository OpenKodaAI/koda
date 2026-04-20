"use client";

import { useState } from "react";
import { Pause, Play, Square } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { queryKeys } from "@/lib/query/keys";

type Action = "cancel" | "pause" | "resume";

interface SessionControlsProps {
  agentId: string | null | undefined;
  sessionId: string | null | undefined;
  /** Active execution running/retrying — enables pause/cancel. */
  active?: boolean;
  /** Execution currently paused — enables resume. */
  paused?: boolean;
}

async function runAction(
  agentId: string,
  sessionId: string,
  action: Action,
): Promise<void> {
  const response = await fetch(
    `/api/runtime/agents/${encodeURIComponent(agentId)}/sessions/${encodeURIComponent(sessionId)}/actions/${action}`,
    {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
    },
  );
  if (!response.ok) {
    let text = "";
    try {
      text = await response.text();
    } catch {
      /* noop */
    }
    throw new Error(text || `Unable to ${action} session (${response.status})`);
  }
}

export function SessionControls({
  agentId,
  sessionId,
  active = false,
  paused = false,
}: SessionControlsProps) {
  const queryClient = useQueryClient();
  const [pending, setPending] = useState<Action | null>(null);
  const [error, setError] = useState<string | null>(null);

  const disabled = !agentId || !sessionId;

  async function handle(action: Action) {
    if (!agentId || !sessionId) return;
    setPending(action);
    setError(null);
    try {
      await runAction(agentId, sessionId, action);
      void queryClient.invalidateQueries({
        queryKey: queryKeys.dashboard.sessionDetail(agentId, sessionId),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : `Unable to ${action}`);
    } finally {
      setPending(null);
    }
  }

  if (!active && !paused) return null;

  return (
    <div className="flex items-center gap-1">
      {active && !paused ? (
        <button
          type="button"
          onClick={() => handle("pause")}
          disabled={disabled || pending !== null}
          title="Pause execution"
          className={cn(
            "inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] px-2 text-[0.75rem] text-[var(--text-secondary)]",
            "transition-colors hover:border-[color:var(--border-strong)] hover:text-[var(--text-primary)] disabled:opacity-50",
          )}
        >
          <Pause strokeWidth={1.75} className="icon-xs" />
          Pause
        </button>
      ) : null}
      {paused ? (
        <button
          type="button"
          onClick={() => handle("resume")}
          disabled={disabled || pending !== null}
          title="Resume execution"
          className={cn(
            "inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-panel-sm)] border border-[color:var(--border-subtle)] bg-[var(--panel-soft)] px-2 text-[0.75rem] text-[var(--text-secondary)]",
            "transition-colors hover:border-[color:var(--border-strong)] hover:text-[var(--text-primary)] disabled:opacity-50",
          )}
        >
          <Play strokeWidth={1.75} className="icon-xs" />
          Resume
        </button>
      ) : null}
      {active ? (
        <button
          type="button"
          onClick={() => handle("cancel")}
          disabled={disabled || pending !== null}
          title="Stop execution"
          className={cn(
            "inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-panel-sm)] border border-[color:var(--tone-danger-border)] bg-transparent px-2 text-[0.75rem] text-[var(--tone-danger-text)]",
            "transition-colors hover:bg-[var(--tone-danger-bg)] disabled:opacity-50",
          )}
        >
          <Square strokeWidth={1.75} className="icon-xs" />
          Stop
        </button>
      ) : null}
      {error ? (
        <span className="truncate text-[0.6875rem] text-[var(--tone-danger-text)]" title={error}>
          {error}
        </span>
      ) : null}
    </div>
  );
}
