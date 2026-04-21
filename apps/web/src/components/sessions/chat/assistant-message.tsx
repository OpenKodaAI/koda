"use client";

import { SessionRichText } from "@/components/sessions/session-rich-text";
import { ReasoningBlock } from "@/components/sessions/chat/reasoning-block";
import { ToolCallCard } from "@/components/sessions/chat/tool-call-card";
import { ApprovalPrompt } from "@/components/sessions/chat/approval-prompt";
import { formatDuration } from "@/lib/utils";
import type { ExecutionSummary } from "@/lib/types";

interface AssistantMessageProps {
  text: string;
  linkedExecution?: ExecutionSummary | null;
  extraExecutions?: ExecutionSummary[];
  onOpenExecution?: (taskId: number) => void;
  agentId?: string | null;
  sessionId?: string | null;
}

function collectReasoningLines(execution: ExecutionSummary | null | undefined): string[] {
  if (!execution) return [];
  const maybeReasoning = (execution as { reasoning_summary?: unknown }).reasoning_summary;
  if (Array.isArray(maybeReasoning)) {
    const lines = (maybeReasoning as unknown[]).filter(
      (line): line is string => typeof line === "string" && line.trim().length > 0,
    );
    if (lines.length > 0) return lines;
  }
  const gateReasons = execution.answer_gate_reasons ?? [];
  if (gateReasons.length > 0) return gateReasons;
  return [];
}

export function AssistantMessage({
  text,
  linkedExecution,
  extraExecutions = [],
  onOpenExecution,
  agentId,
  sessionId,
}: AssistantMessageProps) {
  const reasoning = collectReasoningLines(linkedExecution);
  const hasReasoning = reasoning.length > 0;
  const durationLabel =
    linkedExecution?.duration_ms && linkedExecution.duration_ms > 0
      ? formatDuration(linkedExecution.duration_ms)
      : null;
  const streaming =
    linkedExecution?.status === "running" || linkedExecution?.status === "retrying";

  const pendingApprovalId = linkedExecution?.pending_approval_id ?? null;
  const approvalReasons = linkedExecution?.answer_gate_reasons ?? [];

  return (
    <div className="flex flex-col gap-3">
      {hasReasoning || streaming ? (
        <ReasoningBlock streaming={streaming} durationLabel={durationLabel}>
          {hasReasoning ? (
            <ul className="m-0 list-disc space-y-1 pl-4">
              {reasoning.map((line, index) => (
                <li key={index}>{line}</li>
              ))}
            </ul>
          ) : (
            <p className="m-0">…</p>
          )}
        </ReasoningBlock>
      ) : null}

      {text.trim() ? (
        <div className="text-[var(--font-size-md)] leading-[1.6] text-[var(--text-primary)]">
          <SessionRichText content={text} variant="assistant" />
        </div>
      ) : null}

      {linkedExecution ? (
        <ToolCallCard execution={linkedExecution} onOpenDetails={onOpenExecution} />
      ) : null}

      {pendingApprovalId && agentId && sessionId ? (
        <ApprovalPrompt
          agentId={agentId}
          sessionId={sessionId}
          approvalId={pendingApprovalId}
          toolName={linkedExecution?.query_text ?? null}
          reasons={approvalReasons}
        />
      ) : null}

      {extraExecutions.length > 0 ? (
        <div className="flex flex-col">
          {extraExecutions.map((execution) => (
            <ToolCallCard
              key={execution.task_id}
              execution={execution}
              onOpenDetails={onOpenExecution}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
